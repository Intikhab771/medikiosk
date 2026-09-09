from fastapi import FastAPI
from pydantic import BaseModel

from backend.clinical.extractor import ClinicalExtractor
from backend.clinical.normalizer import ClinicalNormalizer


app = FastAPI(title="MediKiosk Backend")

extractor = ClinicalExtractor()
normalizer = ClinicalNormalizer()


class InterviewTurn(BaseModel):
    session_id: str
    language: str
    transcript: str


@app.post("/api/interview/turn")
def interview_turn(turn: InterviewTurn):

    extraction = extractor.extract(turn.transcript)

    normalized = normalizer.normalize(extraction)

    return {
        "session_id": turn.session_id,
        "language": turn.language,
        "transcript": turn.transcript,
        "clinical_data": normalized.model_dump()
    }