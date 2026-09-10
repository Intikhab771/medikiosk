from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="MediKiosk Backend")


class InterviewTurn(BaseModel):
    session_id: str
    language: str
    question_id: str
    transcript: str
    structured_answer: Any


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/interview/turn")
def interview_turn(turn: InterviewTurn):
    return {
        "received": True,
        "session_id": turn.session_id,
        "language": turn.language,
        "question_id": turn.question_id,
        "transcript": turn.transcript,
        "structured_answer": turn.structured_answer,
    }