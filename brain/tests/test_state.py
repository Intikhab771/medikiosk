from engine.patient_state import PatientState
from engine.models import EngineStatus, RedFlagHit


def test_state_updates_answers() -> None:
    state = PatientState(session_id="demo-001", complaint="chest_pain")

    state.update_answer(
        question_id="TEST_001",
        parameter="onset",
        value="2 hours ago",
    )

    assert state.answers["onset"] == "2 hours ago"
    assert state.answers_by_question_id["TEST_001"] == "2 hours ago"


def test_state_round_trip_preserves_red_flags_and_trace() -> None:
    state = PatientState(session_id="demo-002", complaint="chest_pain")
    state.mark_question_asked("CP_001a")
    state.update_answer("CP_001a", "symptom_radiation_location", ["Left arm"])
    state.add_red_flag(RedFlagHit("CP_001a", "high", "urgent", "urgent_triage", "CP_001a", ["Left arm"]))

    restored = PatientState.from_dict(state.to_dict())
    assert restored.to_dict() == state.to_dict()
    assert restored.status is EngineStatus.ESCALATION_REQUIRED
