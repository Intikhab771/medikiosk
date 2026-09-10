"""Minimal FastAPI entry point for MediKiosk."""

from fastapi import FastAPI

app = FastAPI(title="MediKiosk API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
