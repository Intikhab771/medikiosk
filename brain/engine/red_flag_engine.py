"""
Red Flag Engine.

Red flags are entirely data-driven: each complaint-specific question in
the Question Bank may carry a `red_flag` object of the form

    {
      "is_red_flag": true,
      "trigger_answers": ["Left arm", "Both arms", ...],
      "action": "urgent_triage",
      "rationale": "..."
    }

Whenever a question with such a rule is answered, we check whether the
recorded answer matches one of `trigger_answers`. This engine performs no
diagnosis and adds no clinical knowledge beyond what the Question Bank
already encodes -- it is a pure pattern match against declared rules.
"""
from __future__ import annotations

from typing import Any

from .loader import QuestionBank
from .models import Question, RedFlagHit

# The Question Bank's `action` values map onto a severity for the
# structured output. This mapping is intentionally coarse and generic
# (not complaint-specific), since only two action values exist in the
# schema today: "urgent_triage" and "priority_evaluation".
_ACTION_SEVERITY = {
    "urgent_triage": "high",
    "priority_evaluation": "medium",
}


def _answer_matches(answer: Any, trigger_answers: tuple[str, ...]) -> bool:
    """Case-insensitive match. Handles both single-value answers
    (yes_no_unknown, single_choice) and list-valued answers
    (multiple_choice) by checking for any overlap."""
    triggers_norm = {t.strip().lower() for t in trigger_answers}

    if isinstance(answer, (list, tuple, set)):
        return any(str(a).strip().lower() in triggers_norm for a in answer)

    if answer is None:
        return False

    return str(answer).strip().lower() in triggers_norm


def check_question_for_red_flag(question: Question, answer: Any) -> RedFlagHit | None:
    """Check a single just-answered question against its own red_flag
    rule (if any). Returns a RedFlagHit if triggered, else None."""
    rule = question.red_flag
    if rule is None or not rule.is_red_flag:
        return None

    if _answer_matches(answer, rule.trigger_answers):
        severity = _ACTION_SEVERITY.get(rule.action, "unspecified")
        return RedFlagHit(
            id=question.id,
            severity=severity,
            reason=rule.rationale,
            action=rule.action,
            triggering_question_id=question.id,
            triggering_answer=answer,
        )
    return None


def check_red_flags(patient_state, question_bank: QuestionBank) -> dict:
    """Re-evaluate every answered question against its red_flag rule.
    This is safe to call at any point (idempotent) and does not depend on
    call order -- useful both for the "check red flags first" step of
    get_next_question and for standalone auditing/tests.

    Returns the structured dict shape requested by the spec:
        {"triggered": bool, "flags": [{"id", "severity", "reason"}, ...]}
    """
    flags: list[dict] = []
    for question_id, answer in patient_state.answers_by_question_id.items():
        question = question_bank.get(question_id)
        if question is None:
            continue
        hit = check_question_for_red_flag(question, answer)
        if hit is not None:
            # Synchronize the persisted state as well as the returned audit
            # view. add_red_flag is idempotent, so reload/re-evaluation is safe.
            patient_state.add_red_flag(hit)
            flags.append({"id": hit.id, "severity": hit.severity, "reason": hit.reason})
    return {"triggered": len(flags) > 0, "flags": flags}
