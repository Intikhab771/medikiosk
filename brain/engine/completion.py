"""
Completion Engine.

Completion is derived purely from the Question Bank + the traversal state
already recorded on PatientState -- never from a fixed question count.

A "stage" (opening / shared_symptom_history / health_background) is
exhausted when every question in it that is currently applicable has
either been answered, or is the target of an ask_when condition that
evaluates to False (i.e., it was correctly ruled out, not skipped
arbitrarily).

The complaint-specific stage is exhausted when the branch-graph traversal
for the active complaint has reached the "END" sentinel.

See adaptive_engine.py for how these primitives are combined into
`get_next_question`; this module only answers "are we done?", not "what
question is next?".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import CompletionStatus, Stage

if TYPE_CHECKING:
    from .adaptive_engine import AdaptiveEngine
    from .patient_state import PatientState


@dataclass
class CompletionCheck:
    status: CompletionStatus
    stage_details: dict[str, bool]  # stage name -> exhausted?
    complaint_flow_reached_end: bool
    complaint_selected: bool


def is_complete(patient_state: "PatientState", engine: "AdaptiveEngine") -> CompletionCheck:
    if patient_state.is_escalated():
        return CompletionCheck(
            status=CompletionStatus.BLOCKED_BY_RED_FLAG,
            stage_details={},
            complaint_flow_reached_end=False,
            complaint_selected=patient_state.complaint is not None,
        )

    stage_details = {
        Stage.OPENING.value: engine.stage_exhausted(Stage.OPENING, patient_state),
        Stage.SHARED_SYMPTOM_HISTORY.value: engine.stage_exhausted(
            Stage.SHARED_SYMPTOM_HISTORY, patient_state
        ),
        Stage.HEALTH_BACKGROUND.value: engine.stage_exhausted(
            Stage.HEALTH_BACKGROUND, patient_state
        ),
    }

    complaint_selected = patient_state.complaint is not None
    complaint_flow_done = (
        complaint_selected
        and engine.complaint_flow_pointer(patient_state) is None
    )

    all_done = (
        stage_details[Stage.OPENING.value]
        and stage_details[Stage.SHARED_SYMPTOM_HISTORY.value]
        and complaint_selected
        and complaint_flow_done
        and stage_details[Stage.HEALTH_BACKGROUND.value]
    )

    return CompletionCheck(
        status=CompletionStatus.COMPLETE if all_done else CompletionStatus.INCOMPLETE,
        stage_details=stage_details,
        complaint_flow_reached_end=complaint_flow_done,
        complaint_selected=complaint_selected,
    )
