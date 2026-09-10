"""Structured consultation state used by the deterministic engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .models import EngineStatus, RedFlagHit


@dataclass
class PatientState:
    session_id: str
    complaint: Optional[str] = None
    answers: dict[str, Any] = field(default_factory=dict)
    answers_by_question_id: dict[str, Any] = field(default_factory=dict)
    asked_questions: list[str] = field(default_factory=list)
    answered_parameters: set[str] = field(default_factory=set)
    current_question: Optional[str] = None
    question_history: list[dict] = field(default_factory=list)
    red_flags: list[RedFlagHit] = field(default_factory=list)
    status: EngineStatus = EngineStatus.QUESTIONING
    completion_status: str = "incomplete"

    def set_complaint(self, complaint_id: str) -> None:
        self.complaint = complaint_id

    def update_answer(self, question_id: str, parameter: str, value: Any) -> None:
        self.answers[parameter] = value
        self.answers_by_question_id[question_id] = value
        self.answered_parameters.add(parameter)
        self.question_history.append(
            {"question_id": question_id, "parameter": parameter, "answer": value}
        )
        if self.current_question == question_id:
            self.current_question = None

    def mark_question_asked(self, question_id: str) -> None:
        if question_id not in self.asked_questions:
            self.asked_questions.append(question_id)
        self.current_question = question_id

    def has_asked(self, question_id: str) -> bool:
        return question_id in self.asked_questions

    def has_answer(self, parameter: str) -> bool:
        return parameter in self.answered_parameters

    def get_answer(self, parameter: str) -> Any:
        return self.answers.get(parameter)

    def get_answer_by_question_id(self, question_id: str) -> Any:
        return self.answers_by_question_id.get(question_id)

    def add_red_flag(self, hit: RedFlagHit) -> None:
        # Keep the hit list idempotent if red flags are re-evaluated.
        if not any(
            existing.triggering_question_id == hit.triggering_question_id
            and existing.triggering_answer == hit.triggering_answer
            for existing in self.red_flags
        ):
            self.red_flags.append(hit)
        self.status = EngineStatus.ESCALATION_REQUIRED
        self.current_question = None

    def is_escalated(self) -> bool:
        return self.status is EngineStatus.ESCALATION_REQUIRED

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "complaint": self.complaint,
            "answers": self.answers,
            "answers_by_question_id": self.answers_by_question_id,
            "asked_questions": self.asked_questions,
            "answered_parameters": sorted(self.answered_parameters),
            "current_question": self.current_question,
            "question_history": self.question_history,
            "red_flags": [rf.__dict__ for rf in self.red_flags],
            "status": self.status.value,
            "completion_status": self.completion_status,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "PatientState":
        """Reconstruct state from the JSON-safe representation returned by to_dict."""
        if not isinstance(payload, dict) or not isinstance(payload.get("session_id"), str):
            raise ValueError("PatientState payload must contain a string session_id.")
        raw_flags = payload.get("red_flags", [])
        flags = [RedFlagHit(**flag) for flag in raw_flags]
        raw_status = payload.get("status", EngineStatus.QUESTIONING.value)
        try:
            status = EngineStatus(raw_status)
        except ValueError as exc:
            raise ValueError(f"Unknown PatientState status: {raw_status!r}") from exc
        state = cls(
            session_id=payload["session_id"],
            complaint=payload.get("complaint"),
            answers=dict(payload.get("answers", {})),
            answers_by_question_id=dict(payload.get("answers_by_question_id", {})),
            asked_questions=list(payload.get("asked_questions", [])),
            answered_parameters=set(payload.get("answered_parameters", [])),
            current_question=payload.get("current_question"),
            question_history=list(payload.get("question_history", [])),
            red_flags=flags,
            status=status,
            completion_status=payload.get("completion_status", "incomplete"),
        )
        return state
