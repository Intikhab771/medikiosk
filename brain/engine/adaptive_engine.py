"""Deterministic adaptive clinical-questioning engine.

The engine selects only questions that exist in the Question Bank. It does
not diagnose, generate clinical questions, or use an LLM.
"""
from __future__ import annotations

from typing import Any, Optional

from .completion import is_complete
from .errors import (
    InvalidAnswerTypeError,
    InvalidBranchAnswerError,
    MissingQuestionReferenceError,
    UnknownComplaintError,
    QuestionNotActiveError,
)
from .loader import ClinicalParameters, QuestionBank
from .models import (
    CompletionStatus,
    EngineResult,
    EngineStatus,
    Question,
    SelectionReason,
    Stage,
)
from .patient_state import PatientState
from .red_flag_engine import check_question_for_red_flag, check_red_flags
from .rule_engine import EvaluationOutcome, RuleEngine

_STAGE_GROUP_KEY = {
    Stage.OPENING: "opening",
    Stage.SHARED_SYMPTOM_HISTORY: "shared_symptom_history",
    Stage.HEALTH_BACKGROUND: "health_background",
}


class AdaptiveEngine:
    def __init__(self, question_bank: QuestionBank, clinical_parameters: ClinicalParameters):
        self.qb = question_bank
        self.cp = clinical_parameters

    def get_next_question(self, patient_state: PatientState, debug: bool = False) -> EngineResult:
        # Never replace an unanswered question that is already on screen.
        if patient_state.current_question and not patient_state.has_answer(
            self.qb.get(patient_state.current_question).parameter
            if self.qb.get(patient_state.current_question) else ""
        ):
            q = self.qb.get(patient_state.current_question)
            if q is not None:
                return EngineResult(
                    status=EngineStatus.QUESTIONING,
                    next_question=self._question_public_view(q, patient_state),
                    reason=SelectionReason(
                        priority=self._priority_of(q)[0],
                        priority_source=self._priority_of(q)[1],
                        stage=q.stage.value,
                        triggered_by=[q.group_id],
                        rule_evaluation="current_question_pending_answer",
                    ),
                    red_flags=patient_state.red_flags,
                    completion_status=CompletionStatus.INCOMPLETE,
                    debug={"note": "Returning existing unanswered question."} if debug else None,
                )

        red_flag_summary = check_red_flags(patient_state, self.qb)
        if red_flag_summary["triggered"]:
            patient_state.status = EngineStatus.ESCALATION_REQUIRED
        if patient_state.is_escalated():
            return EngineResult(
                status=EngineStatus.ESCALATION_REQUIRED,
                next_question=None,
                reason=None,
                red_flags=patient_state.red_flags,
                completion_status=CompletionStatus.BLOCKED_BY_RED_FLAG,
                debug={"red_flag_summary": red_flag_summary} if debug else None,
            )

        completion = is_complete(patient_state, self)
        patient_state.completion_status = completion.status.value
        if completion.status is CompletionStatus.COMPLETE:
            patient_state.status = EngineStatus.COMPLETE
            return EngineResult(
                status=EngineStatus.COMPLETE,
                next_question=None,
                reason=None,
                red_flags=patient_state.red_flags,
                completion_status=CompletionStatus.COMPLETE,
                debug={"completion": completion.__dict__} if debug else None,
            )

        rejected_trace: list[dict] = []
        for stage in Stage.order():
            if stage is not Stage.OPENING and not self._prior_stages_exhausted(stage, patient_state):
                continue

            if stage in (Stage.SHARED_SYMPTOM_HISTORY, Stage.COMPLAINT_SPECIFIC):
                if patient_state.complaint is None:
                    return self._blocked_pending_complaint(patient_state, stage, debug)
                if not self.qb.has_complaint(patient_state.complaint):
                    raise UnknownComplaintError(
                        f"Unknown complaint '{patient_state.complaint}'. "
                        f"Expected one of: {self.qb.all_complaint_ids()}"
                    )

            candidates, rejected = self._candidates_for_stage(stage, patient_state)
            rejected_trace.extend(rejected)
            if not candidates:
                continue

            # Shared groups are already explicitly ordered in the Question
            # Bank. Preserve that order; do not let clinical priority cause
            # consent/chief-concern questions to reorder themselves.
            if stage is Stage.COMPLAINT_SPECIFIC:
                chosen, priority, priority_source = self._select_highest_priority(candidates)
            else:
                # If the Question Bank supplies explicit priorities for a
                # shared group, use them. Otherwise preserve source order.
                explicit = any(q.priority is not None for q in candidates)
                if explicit:
                    chosen, priority, priority_source = self._select_highest_priority(candidates)
                else:
                    chosen = candidates[0]
                    priority, priority_source = self._priority_of(chosen)

            patient_state.mark_question_asked(chosen.id)
            reason = SelectionReason(
                priority=priority,
                priority_source=priority_source,
                stage=stage.value,
                triggered_by=[chosen.group_id],
                rule_evaluation="applicable",
                rejected_candidates=rejected_trace,
            )
            return EngineResult(
                status=EngineStatus.QUESTIONING,
                next_question=self._question_public_view(chosen, patient_state),
                reason=reason,
                red_flags=patient_state.red_flags,
                completion_status=CompletionStatus.INCOMPLETE,
                debug={"all_candidates": [c.id for c in candidates]} if debug else None,
            )

        return EngineResult(
            status=EngineStatus.QUESTIONING,
            next_question=None,
            reason=SelectionReason(
                priority=None,
                priority_source="n/a",
                stage="n/a",
                triggered_by=[],
                rule_evaluation="no_candidates_found_but_not_complete",
                rejected_candidates=rejected_trace,
            ),
            red_flags=patient_state.red_flags,
            completion_status=CompletionStatus.INCOMPLETE,
            debug=None,
        )

    def is_question_applicable(self, question: Question, patient_state: PatientState) -> tuple[bool, str]:
        if patient_state.current_question == question.id and not patient_state.has_answer(question.parameter):
            return True, "currently active and awaiting answer"
        if patient_state.has_answer(question.parameter):
            return False, "already answered"
        if patient_state.has_asked(question.id):
            return False, "already asked"
        if question.is_complaint_specific and question.applies_to and (
            patient_state.complaint not in question.applies_to
        ):
            return False, f"does not apply to complaint '{patient_state.complaint}'"

        result = self._rule_engine_for(patient_state).evaluate_ask_when(question.ask_when)
        if result.outcome is EvaluationOutcome.TRUE:
            return True, result.detail
        if result.outcome is EvaluationOutcome.FALSE:
            return False, result.detail
        return True, "UNPARSEABLE ask_when defaulted to True: " + result.detail

    def _candidates_for_stage(self, stage: Stage, patient_state: PatientState) -> tuple[list[Question], list[dict]]:
        candidates: list[Question] = []
        rejected: list[dict] = []

        if stage is Stage.COMPLAINT_SPECIFIC:
            pointer_id = self.complaint_flow_pointer(patient_state)
            if pointer_id is None:
                return [], []
            q = self.qb.get(pointer_id)
            if q is None:
                raise MissingQuestionReferenceError(f"Complaint pointer references missing question '{pointer_id}'.")
            applicable, why = self.is_question_applicable(q, patient_state)
            if applicable:
                candidates.append(q)
            else:
                rejected.append({"id": q.id, "reason": why})
            return candidates, rejected

        group_key = _STAGE_GROUP_KEY[stage]
        for qid in self.qb.shared_group_order.get(group_key, []):
            q = self.qb.get(qid)
            if q is None:
                raise MissingQuestionReferenceError(f"Shared group references missing question '{qid}'.")
            applicable, why = self.is_question_applicable(q, patient_state)
            if applicable:
                candidates.append(q)
            else:
                rejected.append({"id": q.id, "reason": why})
        return candidates, rejected

    def stage_exhausted(self, stage: Stage, patient_state: PatientState) -> bool:
        candidates, _ = self._candidates_for_stage(stage, patient_state)
        return len(candidates) == 0

    def _prior_stages_exhausted(self, stage: Stage, patient_state: PatientState) -> bool:
        order = Stage.order()
        idx = order.index(stage)
        for earlier in order[:idx]:
            if earlier is Stage.COMPLAINT_SPECIFIC:
                if patient_state.complaint is None:
                    return False
                if self.complaint_flow_pointer(patient_state) is not None:
                    return False
            elif not self.stage_exhausted(earlier, patient_state):
                return False
        return True

    def complaint_flow_pointer(self, patient_state: PatientState) -> Optional[str]:
        complaint = patient_state.complaint
        if complaint is None:
            return None
        if not self.qb.has_complaint(complaint):
            raise UnknownComplaintError(f"Unknown complaint '{complaint}'.")

        current = self.qb.complaint_flow_root[complaint]
        visited: set[str] = set()
        while True:
            if current in visited:
                # Loader should make this impossible.
                raise RuntimeError(f"Circular complaint flow detected at '{current}'.")
            visited.add(current)
            answer = patient_state.get_answer_by_question_id(current)
            if answer is None:
                return current
            q = self.qb.get(current)
            if q is None:
                raise MissingQuestionReferenceError(f"Missing complaint question '{current}'.")
            next_id = self._resolve_branch(q, answer)
            if next_id == "END":
                return None
            current = next_id

    def _resolve_branch(self, question: Question, answer: Any) -> str:
        normalized_answer = self._normalize_branch_value(answer)
        normalized_branches = {
            self._normalize_branch_value(key): target
            for key, target in question.branches.items()
            if key != "default"
        }
        if normalized_answer in normalized_branches:
            return normalized_branches[normalized_answer]
        if "default" in question.branches:
            return question.branches["default"]
        raise InvalidBranchAnswerError(
            f"Question '{question.id}' received answer {answer!r}, but no matching branch exists."
        )

    @staticmethod
    def _normalize_branch_value(value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (list, tuple, set)):
            return "|".join(sorted(str(v).strip().lower() for v in value))
        return str(value).strip().lower()

    def _select_highest_priority(self, candidates: list[Question]) -> tuple[Question, int, str]:
        ranked = [(self._priority_of(q), i, q) for i, q in enumerate(candidates)]
        ranked.sort(key=lambda t: (t[0][0], t[1]))
        (priority, source), _, chosen = ranked[0]
        return chosen, priority, source

    def _priority_of(self, question: Question) -> tuple[int, str]:
        if question.priority is not None:
            return question.priority, "question_bank.priority"
        param = self.cp.get(question.parameter)
        if param is not None and param.priority == "high":
            return 2, "clinical_parameters.priority=high"
        if param is not None and param.priority == "routine":
            return 3, "clinical_parameters.priority=routine"
        return 3, "default (no priority info available)"

    def _rule_engine_for(self, patient_state: PatientState) -> RuleEngine:
        # Support both question-id and parameter-id references.
        def lookup(key: str) -> Any:
            value = patient_state.get_answer_by_question_id(key)
            if value is not None:
                return value
            return patient_state.get_answer(key)

        return RuleEngine(answer_lookup=lookup)

    def _question_public_view(self, question: Question, patient_state: PatientState) -> dict:
        from .parameter_resolver import resolve_question_text
        return {
            "id": question.id,
            "text": resolve_question_text(question, patient_state),
            "answer_type": question.answer_type,
            "options": list(question.options) or None,
            "item_fields": list(question.item_fields) or None,
            "required": question.required,
        }

    def submit_answer(self, patient_state: PatientState, question_id: str, value: Any) -> None:
        if patient_state.is_escalated():
            raise QuestionNotActiveError("The interview has been escalated; no further answers are accepted.")
        if patient_state.status is EngineStatus.COMPLETE:
            raise QuestionNotActiveError("The interview is complete; no further answers are accepted.")
        question = self.qb.get(question_id)
        if question is None:
            raise MissingQuestionReferenceError(f"Unknown question id '{question_id}'.")
        if patient_state.current_question != question_id:
            raise QuestionNotActiveError(
                f"Question '{question_id}' is not the active question. "
                f"Active question: {patient_state.current_question!r}."
            )

        self._validate_answer(question, value)
        patient_state.update_answer(question_id, question.parameter, value)

        hit = check_question_for_red_flag(question, value)
        if hit is not None:
            patient_state.add_red_flag(hit)

    def _validate_answer(self, question: Question, value: Any) -> None:
        if value is None:
            raise InvalidAnswerTypeError(f"Question '{question.id}' cannot receive null as an answer.")

        answer_type = question.answer_type
        options = list(question.options)
        normalized_options = {str(o).strip().lower() for o in options}

        if answer_type == "free_text":
            if not isinstance(value, str):
                raise InvalidAnswerTypeError(f"Question '{question.id}' expects free_text (string).")
            return

        if answer_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidAnswerTypeError(f"Question '{question.id}' expects an integer.")
            self._validate_numeric_range(question, value)
            return

        if answer_type == "scale":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise InvalidAnswerTypeError(f"Question '{question.id}' expects a numeric scale value.")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise InvalidAnswerTypeError(f"Question '{question.id}' expects a numeric scale value.") from exc
            if options and str(value).strip().lower() not in normalized_options and str(int(number)) not in normalized_options:
                raise InvalidAnswerTypeError(f"Answer {value!r} is not an allowed scale value for '{question.id}'.")
            self._validate_numeric_range(question, number)
            return

        if answer_type in {"yes_no_unknown", "single_choice"}:
            if not isinstance(value, str):
                raise InvalidAnswerTypeError(f"Question '{question.id}' expects one text choice.")
            if options and value.strip().lower() not in normalized_options:
                raise InvalidAnswerTypeError(f"Answer {value!r} is not an allowed option for '{question.id}'.")
            return

        if answer_type == "multiple_choice":
            if not isinstance(value, (list, tuple, set)):
                raise InvalidAnswerTypeError(f"Question '{question.id}' expects a list of choices.")
            values = [str(v).strip().lower() for v in value]
            if options and any(v not in normalized_options for v in values):
                raise InvalidAnswerTypeError(f"One or more answers are not allowed for '{question.id}'.")
            if len(values) != len(set(values)):
                raise InvalidAnswerTypeError(f"Question '{question.id}' received duplicate choices.")
            return

        if answer_type == "structured_list":
            if not isinstance(value, list):
                raise InvalidAnswerTypeError(f"Question '{question.id}' expects a list of records.")
            if not all(isinstance(item, dict) for item in value):
                raise InvalidAnswerTypeError(f"Every item for '{question.id}' must be an object/dict.")
            required_fields = set(question.item_fields)
            for item in value:
                missing = required_fields - set(item.keys())
                if missing:
                    raise InvalidAnswerTypeError(
                        f"Item for '{question.id}' is missing fields: {sorted(missing)}"
                    )
            return

        raise InvalidAnswerTypeError(f"Unsupported answer_type '{answer_type}' for question '{question.id}'.")

    def _validate_numeric_range(self, question: Question, value: float) -> None:
        param = self.cp.get(question.parameter)
        validation = param.validation if param else None
        if not validation:
            return
        minimum = validation.get("minimum")
        maximum = validation.get("maximum")
        if minimum is not None and value < minimum:
            raise InvalidAnswerTypeError(f"Answer {value} is below the minimum {minimum} for '{question.id}'.")
        if maximum is not None and value > maximum:
            raise InvalidAnswerTypeError(f"Answer {value} is above the maximum {maximum} for '{question.id}'.")

    def _blocked_pending_complaint(self, patient_state: PatientState, stage: Stage, debug: bool) -> EngineResult:
        return EngineResult(
            status=EngineStatus.QUESTIONING,
            next_question=None,
            reason=SelectionReason(
                priority=None,
                priority_source="n/a",
                stage=stage.value,
                triggered_by=[],
                rule_evaluation="blocked_pending_complaint_selection",
            ),
            red_flags=patient_state.red_flags,
            completion_status=CompletionStatus.INCOMPLETE,
            debug={"note": "PatientState.complaint must be selected before this stage."} if debug else None,
        )
