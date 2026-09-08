# Prescription OCR Module (Gemini 3.6 Flash)

This module extracts structured prescription data (patient details, diagnoses, and prescribed medications) from uploaded images using FastAPI and the Gemini API.

---

## 1. Prerequisites & Installation

Ensure you have Python installed, then install the required dependencies:

```bash
pip install fastapi uvicorn google-genai pydantic python-multipart



## 2. Setting Up the API Key

set GEMINI_API_KEY=your_gemini_api_key_here




## 3. Running the API Server

cd ai/ocr
uvicorn main:app --reload