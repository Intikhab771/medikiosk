from pathlib import Path

from ai.extractor import AnswerExtractor
from engine.adaptive_engine import AdaptiveEngine
from engine.loader import load_clinical_parameters, load_question_bank
from engine.patient_state import PatientState
from engine.models import EngineStatus


ROOT = Path(__file__).resolve().parents[2]

QB = load_question_bank(ROOT / "data" / "question_bank.json")
CP = load_clinical_parameters(ROOT / "data" / "clinical_parameters.json")

ENGINE = AdaptiveEngine(QB, CP)
EXTRACTOR = AnswerExtractor()


def complete_shared_history(state):
    answers = {
        "CORE_001": "yes",
        "CORE_003": "chest pain",
        "CORE_002": 30,
        "CORE_004": "none",
        "CORE_005": "today",
        "CORE_006": "1 day",
        "CORE_007": "unchanged",
        "CORE_008": "5",
        "CORE_009": "chest",
        "CORE_010": "none",
        "CORE_011": "no",
    }

    for qid, value in answers.items():
        state.mark_question_asked(qid)
        state.update_answer(qid, QB.get(qid).parameter, value)

    state.current_question = None


# Create patient state
state = PatientState(
    session_id="integration-test",
    complaint="chest_pain",
)

complete_shared_history(state)

# Engine asks CP_001
result = ENGINE.get_next_question(state)
print("Q1:", result.next_question)

# Patient says yes
ENGINE.submit_answer(state, "CP_001", "yes")

# Engine should now ask CP_001a
result = ENGINE.get_next_question(state)
print("Q2:", result.next_question)

question = result.next_question

# Patient answers naturally
transcript = "No, the pain doesn't spread anywhere."

# NLP converts natural language -> structured answer
value = EXTRACTOR.extract(question, transcript)

print("Patient:", transcript)
print("Extracted value:", value)

# Feed EXACT structured value into deterministic engine
ENGINE.submit_answer(
    state,
    question["id"],
    value,
)

print("Stored answer:", state.get_answer_by_question_id(question["id"]))

# Engine continues
result = ENGINE.get_next_question(state)

print("Next result:", result.to_dict())