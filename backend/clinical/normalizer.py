import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .schema import ClinicalExtraction, NormalizedClinicalData


load_dotenv()


class ClinicalNormalizer:

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=api_key)

    def normalize(
        self,
        extraction: ClinicalExtraction
    ) -> NormalizedClinicalData:

        prompt = f"""
You are a clinical data normalization system.

Normalize the provided clinical information into consistent
canonical English terminology.

Rules:

1. Do NOT add information that is not present.
2. Do NOT diagnose the patient.
3. Do NOT infer medical conditions.
4. Preserve negation.
5. Preserve the distinction between current and past conditions.
6. Convert numbers and durations into simple standardized English.
7. Normalize body locations into simple English terms.
8. Normalize symptom names into common clinical English terms,
   without diagnosing them.
9. Normalize radiation separately from associated symptoms.
10. Keep lists concise and standardized.
11. If a value is unknown, keep it null.
12. Do not remove explicitly stated information.

Examples:

"सीने में दर्द" -> "chest pain"
"सीना" -> "chest"
"बाएं हाथ" -> "left arm"
"तीन दिन" -> "3 days"
"चलने पर" -> "walking"
"पिछले एक महीने से" -> "1 month"
"बुखार नहीं है" -> present=false

Input clinical extraction:

{extraction.model_dump_json(indent=2)}
"""

        response = self.client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=NormalizedClinicalData,
            ),
        )

        return NormalizedClinicalData.model_validate_json(
            response.text
        )