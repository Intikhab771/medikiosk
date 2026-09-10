from engine.patient_state import PatientState
from src.summary.summary_generator import generate_summary


def test_summary_uses_patient_state() -> None:
    state = PatientState(session_id="demo-001", complaint="chest_pain")
    assert generate_summary(state)["chief_complaint"] == "chest_pain"
