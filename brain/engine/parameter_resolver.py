"""
Safe parameterized-question resolution.

The engineering brief asks for a mechanism to resolve question text like
"What is your {symptom}?" from patient/complaint context, without unsafe
string evaluation (no eval/exec, no arbitrary attribute access).

NOTE on the provided data: as of schema_version 0.1.0, no question in
question_bank.json actually contains a `{placeholder}` in its `text`
field -- every question is fully literal today. This module exists so
the mechanism is in place and safe *before* it's needed, per requirement
#7 of the brief. It is exercised by tests using a synthetic parameterized
question, and will activate automatically the day a real one is added to
the Question Bank -- no engine changes required.

Resolution rules:
    * Only `{parameter_id}` tokens are recognized (a restricted,
      non-nested mini-syntax -- not Python's full str.format
      mini-language, which would allow attribute/index access).
    * A token resolves from, in order: the patient's already-recorded
      answers (by parameter id), then the complaint id itself if the
      token is literally "complaint".
    * A token that cannot be resolved raises MissingParameterError
      rather than silently leaving "{token}" in patient-facing text or
      guessing a value.
"""
from __future__ import annotations

import re

from .errors import MissingParameterError
from .models import Question
from .patient_state import PatientState

_TOKEN_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def resolve_question_text(question: Question, patient_state: PatientState) -> str:
    tokens = _TOKEN_PATTERN.findall(question.text)
    if not tokens:
        return question.text  # the common case today: nothing to resolve

    resolved = question.text
    for token in tokens:
        value = _resolve_token(token, patient_state)
        if value is None:
            raise MissingParameterError(
                f"Question '{question.id}' references parameter "
                f"'{{{token}}}' which has no value in the current "
                f"PatientState (and is not 'complaint')."
            )
        resolved = resolved.replace(f"{{{token}}}", str(value))
    return resolved


def _resolve_token(token: str, patient_state: PatientState) -> str | None:
    if token == "complaint":
        return patient_state.complaint
    return patient_state.get_answer(token)
