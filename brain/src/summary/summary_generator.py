"""Generate a traceable, draft clinical history summary."""

from engine.patient_state import PatientState


def generate_summary(state: PatientState) -> dict[str, object]:
    """Return a structured draft based exclusively on patient state."""
    return {
        "session_id": state.session_id,
        "chief_concern": state.get_answer("chief_concern_verbatim"),
        # Backward-compatible name retained for existing callers.
        "chief_complaint": state.complaint,
        "complaint": state.complaint,
        "shared_symptom_history": {
            key: state.get_answer(key)
            for key in ("onset", "duration", "course", "severity_0_to_10", "location",
                        "modifying_factors", "similar_previous_episode")
            if key in state.answers
        },
        "complaint_specific_information": {
            key: value for key, value in state.answers.items()
            if key not in {
                "chief_concern_verbatim", "onset", "duration", "course", "severity_0_to_10",
                "location", "modifying_factors", "similar_previous_episode",
                "consent_to_history_intake", "additional_concerns", "additional_patient_notes",
                "allergies_and_reactions", "current_medications_and_supplements", "past_medical_history",
            }
        },
        "health_background": {
            key: state.get_answer(key)
            for key in ("allergies_and_reactions", "current_medications_and_supplements", "past_medical_history",
                        "additional_patient_notes")
            if key in state.answers
        },
        "red_flags": [flag.__dict__.copy() for flag in state.red_flags],
        "status": state.status.value,
        "completion_status": state.completion_status,
        "trace": list(state.question_history),
    }
