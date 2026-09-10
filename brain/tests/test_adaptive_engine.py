from pathlib import Path

import pytest

from engine.adaptive_engine import AdaptiveEngine
from engine.errors import InvalidAnswerTypeError, QuestionNotActiveError
from engine.loader import load_clinical_parameters, load_question_bank
from engine.models import EngineStatus
from engine.patient_state import PatientState

ROOT = Path(__file__).resolve().parents[1]
QB = load_question_bank(ROOT / "data" / "question_bank.json")
CP = load_clinical_parameters(ROOT / "data" / "clinical_parameters.json")
ENGINE = AdaptiveEngine(QB, CP)


def test_opening_order_and_active_question_are_stable():
    state = PatientState(session_id="test", complaint="chest_pain")
    assert ENGINE.get_next_question(state).next_question["id"] == "CORE_001"
    assert ENGINE.get_next_question(state).next_question["id"] == "CORE_001"
    ENGINE.submit_answer(state, "CORE_001", "yes")
    assert ENGINE.get_next_question(state).next_question["id"] == "CORE_003"
    ENGINE.submit_answer(state, "CORE_003", "chest pain")
    assert ENGINE.get_next_question(state).next_question["id"] == "CORE_002"


def test_answer_for_non_active_question_is_rejected():
    state = PatientState(session_id="test", complaint="chest_pain")
    ENGINE.get_next_question(state)
    with pytest.raises(QuestionNotActiveError):
        ENGINE.submit_answer(state, "CORE_002", 20)


def test_invalid_choice_is_rejected_without_mutating_state():
    state = PatientState(session_id="test", complaint="chest_pain")
    ENGINE.get_next_question(state)
    with pytest.raises(InvalidAnswerTypeError):
        ENGINE.submit_answer(state, "CORE_001", "maybe")
    assert state.current_question == "CORE_001"
    assert not state.has_answer("consent_to_history_intake")


def test_integer_range_is_validated():
    state = PatientState(session_id="test", complaint="chest_pain")
    ENGINE.get_next_question(state)
    ENGINE.submit_answer(state, "CORE_001", "yes")
    ENGINE.get_next_question(state)
    ENGINE.submit_answer(state, "CORE_003", "chest pain")
    ENGINE.get_next_question(state)
    with pytest.raises(InvalidAnswerTypeError):
        ENGINE.submit_answer(state, "CORE_002", 131)


def _complete_shared_history(state):
    answers = {
        "CORE_001": "yes", "CORE_003": "chest pain", "CORE_002": 30,
        "CORE_004": "none", "CORE_005": "today", "CORE_006": "1 day",
        "CORE_007": "unchanged", "CORE_008": "5", "CORE_009": "chest",
        "CORE_010": "none", "CORE_011": "no",
    }
    for qid, value in answers.items():
        state.mark_question_asked(qid)
        state.update_answer(qid, QB.get(qid).parameter, value)
    state.current_question = None


def test_chest_pain_yes_branch():
    state = PatientState(session_id="test", complaint="chest_pain")
    _complete_shared_history(state)
    assert ENGINE.get_next_question(state).next_question["id"] == "CP_001"
    ENGINE.submit_answer(state, "CP_001", "YES")
    assert ENGINE.get_next_question(state).next_question["id"] == "CP_001a"


def test_chest_pain_no_branch():
    state = PatientState(session_id="test", complaint="chest_pain")
    _complete_shared_history(state)
    ENGINE.get_next_question(state)
    ENGINE.submit_answer(state, "CP_001", "NO")
    assert ENGINE.get_next_question(state).next_question["id"] == "CP_002"


def test_red_flag_stops_questioning():
    state = PatientState(session_id="test", complaint="chest_pain")
    _complete_shared_history(state)
    ENGINE.get_next_question(state)
    ENGINE.submit_answer(state, "CP_001", "yes")
    ENGINE.get_next_question(state)
    ENGINE.submit_answer(state, "CP_001a", ["Left arm"])
    result = ENGINE.get_next_question(state)
    assert result.status is EngineStatus.ESCALATION_REQUIRED
    assert result.next_question is None
    assert state.is_escalated()


def test_answer_after_escalation_is_rejected():
    state = PatientState(session_id="test", complaint="chest_pain")
    _complete_shared_history(state)
    ENGINE.get_next_question(state)
    ENGINE.submit_answer(state, "CP_001", "yes")
    ENGINE.get_next_question(state)
    ENGINE.submit_answer(state, "CP_001a", ["Left arm"])
    with pytest.raises(QuestionNotActiveError):
        ENGINE.submit_answer(state, "CP_002", "anything")


def test_parameterized_text_is_resolved():
    from engine.models import Question, Stage
    from engine.parameter_resolver import resolve_question_text
    state = PatientState(session_id="test", complaint="headache")
    state.answers["symptom"] = "headache"
    q = Question("X", "Where is your {symptom}?", "location", "free_text", False,
                 Stage.OPENING, "always", (), "opening")
    assert resolve_question_text(q, state) == "Where is your headache?"
