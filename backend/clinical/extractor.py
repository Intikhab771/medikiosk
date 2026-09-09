import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .schema import ClinicalExtraction


load_dotenv()


class ClinicalExtractor:

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set"
            )

        self.client = genai.Client(api_key=api_key)

    def extract(self, transcript: str) -> ClinicalExtraction:

        prompt = f"""
You are a clinical information extraction system.

Your job is ONLY to extract information explicitly stated by the patient.

Do NOT diagnose the patient.
Do NOT infer information that was not stated.
Do NOT invent missing information.

Pay particular attention to:
- symptoms
- duration
- severity
- location
- aggravating factors
- relieving factors
- associated symptoms
- medications
- allergies
- past medical history
- family history
- negation

If the patient says something is NOT present, represent it as absent rather than present.

Patient transcript:

{transcript}
"""

        response = self.client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ClinicalExtraction,
            ),
        )

        return ClinicalExtraction.model_validate_json(response.text)