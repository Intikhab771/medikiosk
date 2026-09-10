# MediKiosk Interface Contract Guide

## Purpose

This guide explains the messages exchanged between the patient-facing/NLP section and the deterministic MediKiosk engine.

Use this as the implementation agreement between teams. If a value is not described here, do not invent a new format without updating the contract and tests.

The short version is:

```text
Engine sends approved question
        ↓
NLP/UI shows it to the patient
        ↓
Patient speaks or types naturally
        ↓
NLP converts the response into a structured value
        ↓
Engine validates and stores the value
        ↓
Engine sends the next approved question or a terminal status
```

## 1. Responsibility split

### Your NLP/UI section owns

- Receiving the engine’s question payload.
- Showing the question to the patient.
- Accepting typed or spoken patient language.
- Converting natural language into the expected structured value.
- Classifying the initial complaint when needed.
- Sending the structured answer back with the correct `question_id`.
- Displaying engine errors or terminal statuses safely.

### The engine owns

- Deciding which question comes next.
- Checking that the question ID exists and is active.
- Validating the answer type and allowed values.
- Updating `PatientState`.
- Applying branches and `ask_when` rules.
- Evaluating configured red flags.
- Deciding whether the interview is complete.
- Returning the structured clinical-history summary.

Your section must never choose a question, skip validation, determine a red flag, or declare completion.

## 2. Engine-to-NLP/UI contract: question output

Call:

```python
result = engine.get_next_question(state)
```

The result is an `EngineResult`. For transport over HTTP or messaging, use:

```python
payload = result.to_dict()
```

### Questioning response

```json
{
  "status": "questioning",
  "next_question": {
    "id": "CP_001",
    "text": "Does the pain spread to your arm, shoulder, back, neck, or jaw?",
    "answer_type": "yes_no_unknown",
    "options": ["yes", "no"],
    "item_fields": null,
    "required": true
  },
  "reason": {
    "priority": 1,
    "priority_source": "question_bank.priority",
    "stage": "complaint_specific",
    "triggered_by": ["chest_pain"],
    "rule_evaluation": "applicable"
  },
  "red_flags": [],
  "completion_status": "incomplete"
}
```

### Meaning of each question field

| Field | Meaning | What your section should do |
|---|---|---|
| `id` | Stable Question Bank ID. | Return this exact value when submitting the answer. |
| `text` | Patient-facing approved wording. | Display it; do not rewrite its clinical meaning. |
| `answer_type` | Expected shape of the answer. | Use it to guide extraction and UI controls. |
| `options` | Allowed choices, if applicable. | Map patient language to one or more of these values only. |
| `item_fields` | Required keys for `structured_list`. | Return records containing these keys. |
| `required` | Whether the question is required in the bank. | Do not use this to bypass engine validation. |

The engine may return the same question again if it is still unanswered. This is intentional. Do not automatically advance to another question.

## 3. NLP/UI-to-engine contract: answer input

Call:

```python
engine.submit_answer(state, question_id, value)
```

The transport object should be:

```json
{
  "question_id": "CP_001",
  "value": "yes"
}
```

The `question_id` must be the ID from the most recent active engine question. The value must already be structured, but it does not need to be clinically interpreted beyond what is explicitly stated by the patient.

## 4. Supported answer formats

### `free_text`

Send a string.

```json
{"question_id": "CORE_003", "value": "A sharp pain in my chest"}
```

Do not turn missing information into a guessed sentence. If the patient did not answer, ask for clarification or follow the product’s explicit missing-answer policy.

### `integer`

Send a whole number, not a numeric string.

```json
{"question_id": "CORE_002", "value": "30"}
```

The JSON representation must be a number, for example:

```json
{"question_id": "CORE_002", "value": 30}
```

The engine checks the configured range. Age currently uses the range 0–130.

### `scale`

Send a number within the Question Bank/Clinical Parameters range.

```json
{"question_id": "CORE_008", "value": 5}
```

The current severity scale is 0–10.

### `yes_no_unknown`

Send the declared controlled value. Current data commonly uses `yes`, `no`, and sometimes `not_sure`.

```json
{"question_id": "CP_001", "value": "yes"}
```

The engine normalizes capitalization and surrounding whitespace. Your section should still prefer canonical values from `options`.

### `single_choice`

Send exactly one option from the question’s `options` list.

```json
{"question_id": "CP_002", "value": "Heavy pressure or squeezing"}
```

Do not send an explanation plus the option. Keep the structured value separate from any raw transcript.

### `multiple_choice`

Send an array of distinct options.

```json
{
  "question_id": "CP_001a",
  "value": ["Left arm", "Neck/Jaw"]
}
```

Do not send duplicates. Do not send options that are not declared by the question.

### `structured_list`

Send an array of objects. Every object must contain the fields listed in `item_fields`.

For allergies:

```json
{
  "question_id": "CORE_012",
  "value": [
    {
      "substance": "Penicillin",
      "reaction": "Rash",
      "severity_if_known": "Mild"
    }
  ]
}
```

For no reported items, the project convention is an empty array:

```json
{"question_id": "CORE_012", "value": []}
```

Do not omit required keys inside a record. Use `null` only when the project’s data convention allows an unknown field and the engine/schema accepts it.

## 5. Raw language versus structured value

The patient may say:

> “Yeah, it shoots down my left arm and sometimes up to my jaw.”

Your section may extract:

```json
{
  "question_id": "CP_001a",
  "value": ["Left arm", "Neck/Jaw"]
}
```

The engine does not receive the raw sentence as the answer for a multiple-choice question. If auditability requires the original wording, keep it in a separate application-side transcript field; do not replace the engine’s structured `value` with it.

The NLP layer must only extract information explicitly present. It must not infer a diagnosis or add a symptom the patient did not state.

## 6. Complaint classification contract

Before complaint-specific questioning can begin, the application/NLP layer must set a complaint ID on `PatientState`:

```python
state.set_complaint("chest_pain")
```

The value must exactly match a complaint flow in `data/question_bank.json`.

The classifier may return an application-level object such as:

```json
{
  "complaint": "chest_pain",
  "confidence": 0.93,
  "evidence": "Patient repeatedly described chest pain"
}
```

Only the validated complaint ID should be passed to the engine. Confidence and evidence are application metadata; they do not choose questions or override the Question Bank.

If the classifier cannot map the concern to a known complaint, do not invent an ID. The application should request clarification or use an approved fallback workflow.

## 7. Engine result statuses

### `questioning`

There is another approved question to ask. `next_question` normally contains an object.

Your section should display the question and wait for an answer.

### `complete`

The configured interview reached its end.

Expected shape:

```json
{
  "status": "complete",
  "next_question": null,
  "red_flags": [],
  "completion_status": "complete"
}
```

Stop asking questions and request the clinical summary.

### `escalation_required`

A configured red flag was triggered.

Expected shape:

```json
{
  "status": "escalation_required",
  "next_question": null,
  "red_flags": [
    {
      "id": "CP_001a",
      "severity": "high",
      "reason": "Radiation to these areas carries a higher clinical risk...",
      "action": "urgent_triage"
    }
  ],
  "completion_status": "blocked_by_red_flag"
}
```

Stop normal questioning. Show the product’s approved escalation message. Do not add your own diagnosis or treatment recommendation.

## 8. Error contract

The engine raises a controlled exception instead of silently accepting unsafe or ambiguous input.

| Error | Meaning | Expected response |
|---|---|---|
| `MissingQuestionReferenceError` | Question ID does not exist. | Treat as an integration/configuration error; do not retry with a guessed ID. |
| `QuestionNotActiveError` | Answer refers to a question that is not currently active, or interview is terminal. | Refresh state/result and do not submit the stale answer. |
| `InvalidAnswerTypeError` | Wrong type, option, range, duplicate, or structured-list shape. | Ask for clarification or remap the value; state was not mutated. |
| `InvalidBranchAnswerError` | Answer has no declared branch and no default. | Surface a controlled clarification/error flow; do not choose a branch yourself. |
| `UnknownComplaintError` | Complaint is not in the Question Bank. | Reclassify or request clarification. |
| `MissingParameterError` | A patient-facing parameter token cannot be resolved. | Treat as a configuration error; do not show unresolved tokens. |
| `QuestionBankLoadError` and related loader errors | Clinical configuration is malformed. | Do not start the interview; fix the data/configuration. |

All failed submissions must be treated as non-mutating. The caller should assume the prior `PatientState` is still valid.

## 9. Correct request loop

The safe application loop is:

```python
while True:
    result = engine.get_next_question(state)

    if result.status.value == "complete":
        break

    if result.status.value == "escalation_required":
        show_escalation(result.red_flags)
        break

    question = result.next_question
    show_to_patient(question["text"])
    raw_response = collect_patient_response()
    structured_value = nlp_extract(raw_response, question)

    try:
        engine.submit_answer(state, question["id"], structured_value)
    except Exception as error:
        show_answer_correction(error)
```

The NLP function receives the current question as context. It must return a value compatible with that question’s `answer_type` and `options`.

## 10. Completion and summary handoff

When the engine returns `complete`, generate the summary from `PatientState`:

```python
from src.summary.summary_generator import generate_summary

summary = generate_summary(state)
```

The summary is structured data, for example:

```json
{
  "session_id": "demo-001",
  "chief_concern": "Chest pain",
  "complaint": "chest_pain",
  "shared_symptom_history": {},
  "complaint_specific_information": {},
  "health_background": {},
  "red_flags": [],
  "status": "complete",
  "completion_status": "complete",
  "trace": []
}
```

The summary generator does not take raw patient language and does not make a diagnosis. It only reports structured state.

## 11. State persistence contract

If the application pauses an interview, save:

```python
saved_state = state.to_dict()
```

Restore it with:

```python
state = PatientState.from_dict(saved_state)
```

After restoration, call `get_next_question(state)` again. If a question was already presented but not answered, the engine returns that same active question.

Do not construct a new state with only the complaint; that would lose the branch path, answers, red flags, and audit trail.

## 12. Versioning rules

The following are contract-breaking changes and require coordinated updates:

- Renaming a question ID.
- Changing an answer type.
- Removing or renaming an option.
- Changing a structured-list field name.
- Changing a complaint ID.
- Changing status values.
- Changing the shape of the answer packet.

Adding a new question or branch is also a clinical change and requires Question Bank review plus tests.

When a breaking change is unavoidable, update:

1. `data/question_bank.json`.
2. This guide.
3. `docs/NLP_ENGINE_CONTRACT.md`.
4. The relevant tests.
5. Any UI/NLP adapter code.

## 13. Integration checklist

Before connecting your section to the engine, confirm:

- You call `get_next_question` before collecting an answer.
- You return the exact active `question_id`.
- You use the question’s `answer_type` and `options`.
- You send structured values, not unprocessed prose.
- You do not invent missing values.
- You do not choose the next question.
- You handle all three engine statuses.
- You handle validation errors without assuming state changed.
- You stop after `complete` or `escalation_required`.
- You preserve and restore the full `PatientState` when pausing.
- You keep raw transcripts separate from structured engine answers.

## 14. One-line rule to remember

**Your section interprets what the patient said; the engine decides what happens next.**
