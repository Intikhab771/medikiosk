import os
from typing import List, Optional
from fastapi import FastAPI, File, HTTPException, UploadFile
from google import genai
from google.genai import types
from pydantic import BaseModel

app = FastAPI(title="SIH Rx Reader API")

# 1. Initialize Gemini Client
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE""
)
client = genai.Client(api_key=GEMINI_API_KEY)


# 2. Define JSON Schemas
class Medicine(BaseModel):
    medicine_name: str
    strength: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None


class PrescriptionData(BaseModel):
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_sex: Optional[str] = None
    date: Optional[str] = None
    symptoms: List[str] = []
    diagnosis: Optional[str] = None
    medicines: List[Medicine] = []
    raw_text: Optional[str] = None


# 3. Extraction Endpoint
@app.post("/extract", response_model=PrescriptionData)
async def extract_prescription(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()

        prompt = """
        Analyze this medical prescription image carefully.
        Extract all details including patient name, age, gender, date, symptoms, diagnosis, 
        and all prescribed medicines (with name, dosage, frequency, and duration).
        Be precise and fill out all fields matching the provided JSON schema.
        """

        # Using the updated model endpoint required by your API account key
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes, mime_type=file.content_type
                ),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PrescriptionData,
            ),
        )

        return response.parsed

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))