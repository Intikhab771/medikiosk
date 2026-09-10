# MediKiosk Reader’s Manual

## 1. What MediKiosk is

MediKiosk is a prototype clinical history-intake system. It helps collect a patient’s reported information in an organized order.

It is not a doctor, diagnostic system, emergency service, or treatment recommender. It does not decide what illness a patient has. It records answers, follows approved interview rules, identifies preconfigured safety triggers, and prepares a structured history for clinician review.

The central idea is adaptive questioning:

```text
Patient answer
    ↓
Structured answer
    ↓
PatientState
    ↓
Rules and safety checks
    ↓
Next approved question
```

The next question can change depending on the earlier answer. For example, a “yes” answer may open a follow-up question while a “no” answer skips it.

## 2. What is complete in this MVP

The current MVP includes:

- A data-driven Question Bank.
- A structured `PatientState` that remembers the interview.
- Deterministic question selection.
- Opening questions in the intended order.
- Shared symptom-history questions.
- Complaint-specific question flows.
- Conditional branches.
- Validation for supported answer types.
- Data-defined red-flag checks.
- Stopping normal questioning after a red flag.
- Completion detection based on the configured flow, not a question count.
- Safe state save and reload using `to_dict()` and `from_dict()`.
- A traceable clinical-history summary.
- Tests and an NLP-to-engine integration contract.

The current Streamlit screen is only a starter interface. It displays a title and an input box, but it does not yet drive the full engine conversation. The engine itself is the completed MVP component.

## 3. Important safety boundary

MediKiosk collects patient-reported information for clinician review. It must not be presented as a diagnosis or emergency triage replacement.

The engine does not:

- Diagnose a condition.
- Recommend medication or treatment.
- Invent questions.
- Decide the next question using an LLM.
- Interpret raw patient language.
- Replace clinical judgment.

An NLP or LLM component may convert natural language into a structured answer, but the deterministic engine makes all validation, branching, red-flag, and completion decisions.

## 4. Repository map

The important folders are:

```text
brain/
├── data/
│   ├── clinical_parameters.json
│   ├── question_bank.json
│   ├── red_flags.json
│   └── test_patients.json
├── engine/
│   ├── adaptive_engine.py
│   ├── completion.py
│   ├── errors.py
│   ├── loader.py
│   ├── models.py
│   ├── parameter_resolver.py
│   ├── patient_state.py
│   ├── red_flag_engine.py
│   └── rule_engine.py
├── src/
│   ├── ai/
│   ├── api/
│   └── summary/
├── tests/
├── ui/
├── app.py
└── requirements.txt
```

### The `data` folder

This is the clinical configuration layer. It is the source of truth for which questions exist and how they connect.

### The `engine` folder

This is the active deterministic implementation. It reads the data files and applies their rules.

### The `src` folder

This contains supporting layers such as the future NLP/AI integration, API entry point, and summary generator. The active state and questioning logic does not live here.

### The `tests` folder

These tests verify the engine’s behavior, including opening order, branching, validation, red flags, state restoration, and summaries.

## 5. How to install and run the project

Open PowerShell and move to the repository:

```powershell
cd "C:\Users\mohit\OneDrive\Desktop\medikiosk\brain"
```

If the virtual environment already exists, activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies if needed:

```powershell
python -m pip install -r requirements.txt
```

Run the tests:

```powershell
python -m pytest -q
```

Compile-check the Python files:

```powershell
python -m compileall .
```

Start the current Streamlit shell:

```powershell
streamlit run app.py
```

The browser page currently confirms that the UI shell starts. The complete engine can be used directly from Python until the UI integration is built.

## 6. The basic engine workflow

The normal application sequence is:

1. Load the Question Bank.
2. Load Clinical Parameters.
3. Create a `PatientState` with a session ID and complaint.
4. Ask the engine for the next question.
5. Send back the structured answer.
6. Ask for the next question again.
7. Continue until the status is `complete` or `escalation_required`.
8. Generate a summary from the final state.

Conceptually:

```python
from pathlib import Path

from engine.adaptive_engine import AdaptiveEngine
from engine.loader import load_clinical_parameters, load_question_bank
from engine.patient_state import PatientState
from src.summary.summary_generator import generate_summary

root = Path(".")
question_bank = load_question_bank(root / "data/question_bank.json")
clinical_parameters = load_clinical_parameters(root / "data/clinical_parameters.json")
engine = AdaptiveEngine(question_bank, clinical_parameters)

state = PatientState(
    session_id="demo-001",
    complaint="chest_pain",
)

result = engine.get_next_question(state)
question = result.next_question

engine.submit_answer(
    state,
    question_id=question["id"],
    value="yes",
)

next_result = engine.get_next_question(state)
summary = generate_summary(state)
```

In a real application, the UI or NLP layer supplies the answer instead of the hard-coded `"yes"`.

## 7. Opening sequence

The opening sequence is configured in `data/question_bank.json` and is intentionally:

```text
CORE_001  Consent
CORE_003  Chief concern
CORE_002  Age
CORE_004  Additional concern
```

This is an important example of the difference between clinical priority and interview order. A question can have a high priority without being allowed to jump ahead of the configured opening sequence.

The complaint category is normally selected by the NLP or application layer after interpreting the patient’s chief concern. The engine then checks that the selected complaint exists in the Question Bank.

## 8. How adaptive branching works

A complaint flow is a small graph of approved questions. Each question can point to another question or to `END`.

Example:

```json
"branches": {
  "yes": "CP_001a",
  "no": "CP_002"
}
```

The engine normalizes simple controlled answers, so `YES`, `Yes`, and `yes` behave the same. It does not guess unsupported values. If an answer does not match a declared branch and there is no declared `default`, the engine raises `InvalidBranchAnswerError`.

Questions are never generated from scratch. Every returned question must already exist in the Question Bank.

## 9. How answer validation works

The engine validates an answer before changing `PatientState`. If validation fails, the previous state remains unchanged.

Supported answer types are:

| Type | Meaning |
|---|---|
| `free_text` | A text response. |
| `integer` | A whole number, such as age. |
| `scale` | A numeric rating, such as 0–10. |
| `yes_no_unknown` | A controlled yes/no/unknown response. |
| `single_choice` | One value from the declared options. |
| `multiple_choice` | A list of distinct values from the declared options. |
| `structured_list` | A list of records with required fields. |

Examples:

```json
{"question_id": "CP_001", "value": "yes"}
```

```json
{"question_id": "CP_001a", "value": ["Left arm", "Neck/Jaw"]}
```

Invalid examples include a string for an integer question, an option not present in the Question Bank, a duplicated multiple-choice value, a number outside its configured range, or a structured record missing a required field.

## 10. What PatientState contains

`PatientState` is the interview’s memory. It contains:

- `session_id`: the interview identifier.
- `complaint`: the selected complaint flow.
- `answers`: answers indexed by parameter name.
- `answers_by_question_id`: answers indexed by question ID.
- `asked_questions`: questions already shown.
- `answered_parameters`: parameters already answered.
- `current_question`: the question currently awaiting an answer.
- `question_history`: an ordered audit trail.
- `red_flags`: triggered data-defined safety rules.
- `status`: `questioning`, `complete`, or `escalation_required`.
- `completion_status`: `incomplete`, `complete`, or `blocked_by_red_flag`.

Both parameter-level and question-level answer maps are intentional. A rule may refer to either a question ID or a parameter ID.

## 11. Saving and reloading an interview

The state is JSON-safe:

```python
saved_payload = state.to_dict()
restored_state = PatientState.from_dict(saved_payload)
```

This preserves the session, answers, question history, current question, red flags, and status. A database is not included in this MVP; an API or application can later store the dictionary in a database or file.

## 12. Red flags

Red flags are declared in the Question Bank on specific questions. A rule contains:

- Whether it is active.
- Trigger answers.
- An action label.
- A rationale.

When a trigger matches:

1. The answer is stored.
2. A structured red-flag record is added.
3. The state becomes `escalation_required`.
4. The current question is cleared.
5. Normal questioning stops.
6. Future answer submission is rejected.

The engine does not diagnose what the red flag means. It only reports the configured rule and action.

Red-flag evaluation is idempotent: checking the same state again does not create duplicate entries.

## 13. Completion

Completion is not based on asking an arbitrary number of questions. The interview is complete only when:

- The opening stage is exhausted.
- Shared symptom history is exhausted.
- A valid complaint is selected.
- The complaint flow reaches `END`.
- Health background is exhausted.
- No red flag has blocked the interview.

The engine returns `complete` with no next question. It returns `escalation_required` when a red flag blocks normal completion.

## 14. Clinical summary

The summary generator uses only structured `PatientState`. It includes, when available:

- Session ID.
- Chief concern.
- Complaint.
- Shared symptom history.
- Complaint-specific information.
- Health background.
- Red flags.
- Interview status.
- Question-and-answer trace.

Missing information remains missing. The summary does not invent details, diagnosis, or treatment recommendations.

```python
from src.summary.summary_generator import generate_summary

summary = generate_summary(state)
```

## 15. How the NLP layer fits in

The NLP layer has three jobs:

1. Understand natural patient language.
2. Extract a structured value for the currently displayed question.
3. Classify the patient’s complaint and provide a valid complaint ID.

The NLP layer must not:

- Select the next question.
- Skip validation.
- Decide that a red flag exists.
- Decide that the interview is complete.
- Invent a question.

The exact interface is documented in [NLP_ENGINE_CONTRACT.md](NLP_ENGINE_CONTRACT.md).

## 16. How to change the interview safely

For a new question or branch, edit `data/question_bank.json`, not Python clinical logic.

Before saving the change:

1. Give the question a globally unique ID.
2. Use one of the supported answer types.
3. Declare options when the answer type needs them.
4. Use valid `applies_to` complaint IDs.
5. Point branches only to questions in the same complaint flow or to `END`.
6. Ensure the flow has one root.
7. Avoid cycles.
8. Add or update a test.
9. Run `python -m pytest -q`.

Do not add a new clinical branch directly inside `adaptive_engine.py`. That would bypass the Question Bank and make the system harder to review.

## 17. What the loader checks

When data is loaded, the loader rejects malformed clinical configuration such as:

- Missing required question fields.
- Duplicate question IDs.
- Unsupported answer types.
- Duplicate options.
- Invalid `applies_to` complaints.
- Malformed red-flag structures.
- Missing branch targets.
- Cross-flow branch targets.
- Multiple roots.
- Circular flows.

Failing loudly is safer than silently running an incorrect clinical flow.

## 18. Understanding the tests

The tests are executable examples of expected behavior. They cover:

- Opening order.
- Active-question stability.
- Wrong-question submission.
- Invalid answers without state mutation.
- Numeric validation.
- Branching and yes/no normalization.
- Red-flag escalation.
- Cross-flow validation.
- Rule evaluation.
- State updates and round trips.
- Summary generation.

Run them with:

```powershell
python -m pytest -q
```

The current MVP result is 15 passing tests.

## 19. Common terms in plain English

| Technical term | Plain-English meaning |
|---|---|
| Question Bank | The approved menu and structure of questions. |
| PatientState | The memory of one interview session. |
| Parameter | A named piece of information, such as age or onset. |
| Rule Engine | The component that evaluates conditions safely. |
| Branch | The next path selected from an answer. |
| Red flag | A preconfigured safety trigger that stops normal questioning. |
| Completion | The point where the configured interview has gathered its required information. |
| Serialization | Turning state into a dictionary that can be saved. |
| Deterministic | The same state and answer always produce the same result. |

## 20. Current limitations and next steps

This is an MVP, not a production clinical product. The next practical work would be:

- Connect the Streamlit UI to `AdaptiveEngine`.
- Connect the NLP extractor to the documented contract.
- Add a reviewed complaint-selection workflow.
- Store sessions in a controlled backend database.
- Add authentication, authorization, audit logging, and privacy controls.
- Expand clinical review of every question and red-flag rule.
- Add more synthetic fixtures and UI-level tests.
- Add deployment and monitoring safeguards.

None of these should be implemented by weakening the deterministic engine boundary.

## 21. Quick start checklist

For a new teammate:

- Read this manual.
- Read [NLP_ENGINE_CONTRACT.md](NLP_ENGINE_CONTRACT.md).
- Open `data/question_bank.json` to see the approved interview content.
- Open `engine/adaptive_engine.py` to see the main workflow.
- Run `python -m pytest -q`.
- Run the synthetic interview or a test case before changing clinical data.
- Keep clinical behavior in JSON and keep engine behavior deterministic.
