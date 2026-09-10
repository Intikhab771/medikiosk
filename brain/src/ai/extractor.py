import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


class AnswerExtractionError(RuntimeError):
    """Raised when the NLP layer cannot produce a structured answer."""
    pass


class AnswerExtractor:
    """
    Converts a patient's natural-language response into the structured
    value expected by the currently active Brain question.

    This class does NOT:
    - choose questions
    - validate questions
    - determine red flags
    - decide completion
    - diagnose
    """

    MODEL_NAME = "gemini-3.5-flash-lite"

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=api_key)

    def extract(self, question: dict[str, Any], transcript: str) -> Any:
        if not transcript or not transcript.strip():
            raise AnswerExtractionError("Patient response is empty.")

        prompt = f"""
You are an answer extraction system for a clinical interview engine.

Your ONLY job is to convert the patient's natural-language response
into the structured value required by the current question.

Do NOT:
- choose another question
- invent information
- diagnose the patient
- determine red flags
- determine whether the interview is complete
- add information not explicitly stated
- rewrite the answer into a different meaning

The deterministic interview engine will perform validation.

CURRENT QUESTION:

{question}

PATIENT RESPONSE:

{transcript}

Rules:

1. Return only information explicitly stated by the patient.
2. Follow the question's answer_type exactly.
3. For single-choice questions, return exactly one value from options.
4. For multiple-choice questions, return a list containing only values
   explicitly supported by the patient's response.
5. For yes_no_unknown questions, return the appropriate controlled value.
6. For integer questions, return an integer.
7. For scale questions, return the numeric value stated by the patient.
8. For free_text questions, return the patient's answer as a concise string.
9. For structured_list questions, return objects containing exactly the
   required item fields.
10. Never invent an answer when the patient did not provide one.
11. Do not use medical knowledge to infer an answer.

The returned value must be directly usable as the `value` argument to:

engine.submit_answer(state, question_id, value)
"""

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_response_schema_for_question(question),
                ),
            )

            return _parse_response(response.text)

        except Exception as exc:
            raise AnswerExtractionError(
                f"Failed to extract structured answer: {exc}"
            ) from exc


def _response_schema_for_question(question: dict[str, Any]) -> dict:
    """
    Build a Gemini response schema matching the Brain question's
    answer_type.

    The Brain remains the final validator.
    """

    answer_type = question["answer_type"]
    options = question.get("options") or []
    item_fields = question.get("item_fields") or []

    if answer_type == "free_text":
        return {
            "type": "STRING",
        }

    if answer_type == "integer":
        return {
            "type": "INTEGER",
        }

    if answer_type == "scale":
        return {
            "type": "NUMBER",
        }

    if answer_type in {"yes_no_unknown", "single_choice"}:
        schema = {
            "type": "STRING",
        }

        if options:
            schema["enum"] = options

        return schema

    if answer_type == "multiple_choice":
        schema = {
            "type": "ARRAY",
            "items": {
                "type": "STRING",
            },
        }

        return schema

    if answer_type == "structured_list":
        properties = {
            field: {
                "type": "STRING",
            }
            for field in item_fields
        }

        return {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": properties,
                "required": item_fields,
            },
        }

    raise ValueError(
        f"Unsupported question answer_type: {answer_type!r}"
    )


def _parse_response(response_text: str) -> Any:
    """
    Parse Gemini's JSON response.

    Gemini structured output should already contain valid JSON.
    """

    import json

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise AnswerExtractionError(
            f"Gemini returned invalid JSON: {response_text!r}"
        ) from exc
