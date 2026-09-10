"""
Core data models for the Adaptive Clinical Questioning Engine.

These models are thin, typed wrappers around the *existing* JSON schemas
in data/question_bank.json and data/clinical_parameters.json. Nothing here
redefines or extends that schema -- fields map 1:1 onto the JSON so the
JSON remains the single source of truth (per the architectural rule that
the engine must not invent clinical logic).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Stage(str, Enum):
    """The four question-bank stages, in the fixed order this prototype
    asks them (see ARCHITECTURE.md / README for why this order was chosen
    -- it is inferred from each group's `when_to_ask` text, since the
    schema does not encode stage order explicitly)."""

    OPENING = "opening"
    SHARED_SYMPTOM_HISTORY = "shared_symptom_history"
    COMPLAINT_SPECIFIC = "complaint_specific"
    HEALTH_BACKGROUND = "health_background"

    @classmethod
    def order(cls) -> list["Stage"]:
        return [cls.OPENING, cls.SHARED_SYMPTOM_HISTORY,
                cls.COMPLAINT_SPECIFIC, cls.HEALTH_BACKGROUND]


class EngineStatus(str, Enum):
    QUESTIONING = "questioning"
    COMPLETE = "complete"
    ESCALATION_REQUIRED = "escalation_required"


class CompletionStatus(str, Enum):
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    BLOCKED_BY_RED_FLAG = "blocked_by_red_flag"


@dataclass(frozen=True)
class RedFlagRule:
    """Mirrors the `red_flag` object attached to a complaint-specific
    question in the Question Bank. `None` on the source question means
    "this question carries no red-flag rule" and is represented by simply
    not constructing a RedFlagRule for that question."""

    is_red_flag: bool
    trigger_answers: tuple[str, ...]
    action: str
    rationale: str

    @staticmethod
    def from_json(raw: Optional[dict]) -> Optional["RedFlagRule"]:
        if not raw:
            return None
        return RedFlagRule(
            is_red_flag=bool(raw.get("is_red_flag", False)),
            trigger_answers=tuple(raw.get("trigger_answers", [])),
            action=raw.get("action", "unspecified"),
            rationale=raw.get("rationale", ""),
        )


@dataclass(frozen=True)
class Question:
    """A single question exactly as it appears in the Question Bank,
    plus the stage/group it belongs to (needed for ordering) and, for
    complaint-specific questions, its branch map."""

    id: str
    text: str
    parameter: str
    answer_type: str
    required: bool
    stage: Stage
    ask_when: Any
    applies_to: tuple[str, ...]
    group_id: str  # shared group id ("opening", etc.) or complaint_id
    options: tuple[str, ...] = ()
    item_fields: tuple[str, ...] = ()
    priority: Optional[int] = None  # only present on complaint-specific Qs
    branches: dict[str, str] = field(default_factory=dict)
    red_flag: Optional[RedFlagRule] = None
    rationale: str = ""
    clinical_review_status: str = ""

    @property
    def is_complaint_specific(self) -> bool:
        return self.stage is Stage.COMPLAINT_SPECIFIC


@dataclass(frozen=True)
class ClinicalParameter:
    """Mirrors an entry from clinical_parameters.json's shared_parameters
    or complaint_specific_parameters lists. Used as secondary reference
    data (validation ranges, high/routine priority) -- never as a
    replacement for what the Question Bank says is askable."""

    id: str
    label: str
    answer_type: str
    required: Any  # bool | "conditional" per the source schema
    priority: Optional[str] = None  # "high" | "routine" (clinical_parameters uses strings)
    validation: Optional[dict] = None
    options: tuple[str, ...] = ()
    applies_to: tuple[str, ...] = ()


@dataclass
class RedFlagHit:
    id: str
    severity: str
    reason: str
    action: str
    triggering_question_id: str
    triggering_answer: Any


@dataclass
class SelectionReason:
    """Explainability payload describing why a question was (or a
    candidate was not) selected."""

    priority: Optional[int]
    priority_source: str
    stage: str
    triggered_by: list[str]
    rule_evaluation: str
    rejected_candidates: list[dict] = field(default_factory=list)


@dataclass
class EngineResult:
    status: EngineStatus
    next_question: Optional[dict]
    reason: Optional[SelectionReason]
    red_flags: list[RedFlagHit]
    completion_status: CompletionStatus
    debug: Optional[dict] = None

    def to_dict(self, debug_mode: bool = False) -> dict:
        out = {
            "status": self.status.value,
            "next_question": self.next_question,
            "reason": None if self.reason is None else {
                "priority": self.reason.priority,
                "priority_source": self.reason.priority_source,
                "stage": self.reason.stage,
                "triggered_by": self.reason.triggered_by,
                "rule_evaluation": self.reason.rule_evaluation,
            },
            "red_flags": [
                {"id": rf.id, "severity": rf.severity, "reason": rf.reason,
                 "action": rf.action}
                for rf in self.red_flags
            ],
            "completion_status": self.completion_status.value,
        }
        if debug_mode and self.debug is not None:
            out["debug"] = self.debug
        return out
