# MediKiosk NLP ↔ Engine Contract

For detailed request/response payloads, answer-type examples, error handling, persistence, and integration checklists, see [Interface Contract Guide](INTERFACE_CONTRACT_GUIDE.md).

The NLP layer interprets patient language, extracts structured facts, and classifies the primary complaint. The deterministic engine validates structured answers, updates `PatientState`, evaluates branches and red flags, selects approved questions, and decides completion.

## Input

After the engine returns a question, NLP submits exactly one structured answer:

```json
{"question_id": "CP_001", "value": "yes"}
```

Multiple-choice values are arrays:

```json
{"question_id": "CP_001a", "value": ["Left arm", "Neck/Jaw"]}
```

The complaint classifier may set `PatientState.complaint` to a complaint ID that exists in the Question Bank. It must not select the next question.

## Output

`get_next_question(state)` returns a result with `status` (`questioning`, `complete`, or `escalation_required`), an approved `next_question` or `null`, completion status, red flags, and an explainable selection reason. `submit_answer` returns no question; call `get_next_question` afterward.

Invalid question IDs, inactive questions, null values, wrong types, unsupported options, invalid ranges, and malformed structured records raise an engine error and do not mutate state. Invalid branch answers raise `InvalidBranchAnswerError`. Once complete or escalated, no further answers are accepted.

The engine never interprets raw patient language, diagnoses, recommends treatment, invents questions, or delegates decisions to an LLM.
