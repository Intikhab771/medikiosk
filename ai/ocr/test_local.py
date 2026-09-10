import os
import shutil
import tempfile
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Load environment variables from .env file into os.environ
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, status
from google import genai
from google.genai import types
from google.genai.errors import APIError
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError, field_validator

# --- PDF Support Dependency ---
try:
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError

    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    PDFInfoNotInstalledError = Exception


# --- 1. Schemas ---


class DocumentType(str, Enum):
    PRESCRIPTION = "prescription"
    LAB_REPORT = "lab_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    IMAGING_REPORT = "imaging_report"
    OTHER = "other"


class Severity(str, Enum):
    NORMAL = "normal"
    MILD = "mild"
    MODERATE = "moderate"
    CRITICAL = "critical"


class Trend(str, Enum):
    IMPROVING = "improving"
    WORSENING = "worsening"
    STABLE = "stable"
    NEW = "new"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Medication(BaseModel):
    name: str
    strength: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None


class LabValue(BaseModel):
    test_name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = Field(
        None,
        description="Stored exactly as printed on document",
    )
    is_abnormal: bool = False
    severity: Optional[Severity] = None
    previous_value: Optional[str] = None
    trend: Optional[Trend] = None


class ImagingDetails(BaseModel):
    modality: str = Field(..., description="X-ray, CT, MRI, Ultrasound, etc.")
    body_part_examined: Optional[str] = None
    clinical_indication: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None
    comparison_to_prior: Optional[str] = None
    image_attached: bool = False
    impression_flagged: bool = False


class DocumentExtraction(BaseModel):
    document_type: DocumentType
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_sex: Optional[str] = None
    document_date_raw: Optional[str] = None
    document_date_iso: Optional[date] = Field(
        None, description="Must strictly follow ISO 8601 format: YYYY-MM-DD"
    )
    doctor_or_hospital: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    diagnoses: List[str] = Field(default_factory=list)
    procedures_or_surgery_history: List[str] = Field(default_factory=list)
    medications: List[Medication] = Field(default_factory=list)
    lab_panel_type: Optional[str] = None
    lab_values: List[LabValue] = Field(default_factory=list)
    imaging_details: Optional[ImagingDetails] = None
    drug_interaction_warnings: List[str] = Field(default_factory=list)
    extraction_confidence: ConfidenceLevel
    raw_text: Optional[str] = None

    @field_validator("document_date_iso", mode="before")
    @classmethod
    def validate_date_format(cls, value):
        if value is None or isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Date '{value}' is not a valid ISO format (YYYY-MM-DD).")


# --- 2. FastAPI Setup ---

app = FastAPI(
    title="Medikiosk Document OCR Service",
    version="1.0.0",
    description="Extracts structured clinical data from medical documents.",
)


def load_document_images(file_path: Path) -> List[Image.Image]:
    ext = file_path.suffix.lower()

    if ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
        try:
            img = Image.open(file_path)
            img.verify()
            return [Image.open(file_path)]
        except UnidentifiedImageError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded image is corrupted or invalid.",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error reading image file: {str(e)}",
            )

    elif ext == ".pdf":
        if not PDF2IMAGE_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="PDF processing is disabled. 'pdf2image' is missing.",
            )
        try:
            return convert_from_path(file_path, dpi=200)
        except PDFInfoNotInstalledError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Poppler dependency missing on server.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{ext}'. Upload PNG, JPEG, WEBP, BMP, or PDF.",
        )


# --- 3. Endpoints ---


@app.post(
    "/extract",
    response_model=DocumentExtraction,
    status_code=status.HTTP_200_OK,
    summary="Extract structured clinical data from medical files",
)
async def extract_document(file: UploadFile):
    # Validates that load_dotenv() picked up the environment variable
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GEMINI_API_KEY environment variable is not configured.",
        )

    # Store upload temporarily for conversion/processing
    ext = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = Path(tmp_file.name)

    try:
        images = load_document_images(tmp_path)

        # Client automatically uses GEMINI_API_KEY from environment
        client = genai.Client(
            http_options=types.HttpOptions(timeout=30000),
        )

        prompt = (
            "Analyze this medical document image/pages. First, classify its document_type "
            "(prescription, lab_report, discharge_summary, imaging_report, or other). "
            "Extract all available information precisely matching the response schema. "
            "Ensure document_date_iso strictly uses YYYY-MM-DD format."
        )

        contents = images + [prompt]

        # Automatic fallback sequence if a model tier experiences 503 high-demand errors
        models_to_try = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
        response = None
        last_error = None

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=DocumentExtraction,
                        max_output_tokens=8192,
                    ),
                )
                if response:
                    break
            except APIError as e:
                last_error = e
                # Fallback on 503 / high demand spikes
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    continue
                raise e

        if response is None and last_error:
            raise last_error

        parsed_data: Optional[DocumentExtraction] = response.parsed

        if parsed_data is None:
            if response.text:
                try:
                    parsed_data = DocumentExtraction.model_validate_json(
                        response.text
                    )
                except ValidationError as ve:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "message": "Model output failed schema validation",
                            "errors": ve.errors(),
                            "raw_response": response.text,
                        },
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Model generated an empty response.",
                )

        return parsed_data

    except APIError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API Exception: {str(e)}",
        )
    finally:
        # Guarantee temp file cleanup
        if tmp_path.exists():
            os.remove(tmp_path)