# MediKiosk

MediKiosk is a multilingual AI-assisted clinical interview system designed for patient interaction and structured medical history collection.

The current implementation focuses on:

- Multilingual speech recognition
- Clinical information extraction
- Clinical data normalization
- Backend API integration
- Voice-to-clinical-data processing

The system is being developed incrementally as part of the SIH project.

---

# Architecture

The current clinical pipeline is:

Patient
   │
   ▼
Microphone
   │
   ▼
IndicConformer ASR
   │
   ▼
Raw Transcript
   │
   ▼
FastAPI
   │
   ▼
Clinical Extractor
   │
   ▼
Clinical Extraction
   │
   ▼
Clinical Normalizer
   │
   ▼
Normalized Clinical Data
   │
   ▼
Patient State
   │
   ▼
Question Engine
   │
   ▼
Clinical Summary

The Patient State, Question Engine, and final clinical summary are planned components and are not yet implemented.

---

# Current Implementation

## 1. Speech Recognition

The voice pipeline uses:

`ai4bharat/indic-conformer-600m-multilingual`

The model is used for speech-to-text transcription of Indian languages.

The ASR layer is intentionally kept separate from clinical reasoning.

Its responsibility is only:

Audio → Transcript

It should not:

- Diagnose the patient
- Interpret symptoms
- Generate medical advice
- Determine whether a symptom is dangerous
- Modify the patient's statement

---

## 2. Clinical Information Extraction

The clinical extractor processes the raw transcript using the Gemini API.

Its responsibility is to identify information explicitly stated by the patient.

The current extraction schema includes:

- Chief complaint
- Symptoms
- Duration
- Severity
- Location
- Radiation
- Aggravating factors
- Relieving factors
- Associated symptoms
- Medications
- Allergies
- Past medical history
- Family history
- Symptom presence/absence

The extractor is instructed not to diagnose or infer information that the patient did not explicitly state.

### Example

Patient:

    मुझे तीन दिन से सीने में दर्द हो रहा है।
    दर्द चलने पर बढ़ता है और कभी-कभी बाएं हाथ तक जाता है।
    मुझे बुखार नहीं है।

The extractor can produce information such as:

    chest pain
    duration: 3 days
    aggravating factor: walking
    radiation: left arm
    fever: present = false

---

## 3. Clinical Normalization

The normalizer converts multilingual extracted information into canonical English terminology.

Example:

    सीने में दर्द
        ↓
    chest pain

    तीन दिन
        ↓
    3 days

    बाएं हाथ तक
        ↓
    left arm

    खाइ के बाद
        ↓
    eating

Normalization does NOT mean diagnosis.

For example:

    chest pain
        ↓
    chest pain

is valid normalization.

But:

    chest pain
        ↓
    angina

would be a clinical inference and is therefore outside the responsibility of the normalizer.

---

# Project Structure

Current structure:

    medikiosk/
    │
    ├── backend/
    │   ├── api/
    │   │   └── .gitkeep
    │   │
    │   ├── clinical/
    │   │   ├── __init__.py
    │   │   ├── schema.py
    │   │   ├── extractor.py
    │   │   └── normalizer.py
    │   │
    │   ├── database/
    │   │   └── .gitkeep
    │   │
    │   ├── models/
    │   │   └── .gitkeep
    │   │
    │   ├── services/
    │   │   └── .gitkeep
    │   │
    │   ├── main.py
    │   ├── test_gemini.py
    │   └── test_normalizer.py
    │
    ├── voice/
    │   ├── __init__.py
    │   └── asr/
    │       ├── __init__.py
    │       ├── model.py
    │       └── live_stt.py
    │
    ├── frontend/
    ├── tests/
    ├── docs/
    ├── .env
    ├── .gitignore
    ├── requirements.txt
    └── README.md

Note:

The local development files `test_gemini.py` and `test_normalizer.py` may not be committed to the repository.

---

# Requirements

The project currently requires:

- Python 3.12
- A working microphone for the voice pipeline
- Internet connection for the Gemini API
- A Gemini API key
- Sufficient RAM/storage for the IndicConformer model

The ASR currently runs on CPU if CUDA is unavailable.

A GPU is not required for the current prototype.

---

# Installation

## 1. Clone the repository

Clone the repository and switch to the required branch.

Example:

    git clone <repository-url>
    cd medikiosk

Then switch to the relevant feature branch if required:

    git switch feature/clinical-nlp

---

# 2. Create a virtual environment

From the project root:

    python3 -m venv .venv

Activate it:

### Linux

    source .venv/bin/activate

Verify:

    which python

The path should point to:

    medikiosk/.venv/bin/python

---

# 3. Install dependencies

Install all Python dependencies:

    pip install -r requirements.txt

---

# Gemini API Configuration

The clinical extraction and normalization layers use the Gemini API.

Each developer should use their own API key.

Do NOT commit an API key to Git.

---

## 1. Create `.env`

Create this file in the project root:

    .env

Add:

    GEMINI_API_KEY=your_api_key_here

Example:

    GEMINI_API_KEY=xxxxxxxxxxxxxxxx

Do not replace the placeholder with someone else's key.

---

## 2. Security

The `.env` file must remain local.

It should be included in `.gitignore`:

    .env

Never commit:

- Gemini API keys
- Hugging Face tokens
- Patient information
- Patient audio recordings
- Model credentials
- Other secrets

---

# Hugging Face / IndicConformer

The ASR model is:

    ai4bharat/indic-conformer-600m-multilingual

The model is downloaded through Hugging Face when the ASR service is initialized.

The model weights should NOT be committed to Git.

The local Hugging Face cache should also NOT be committed.

If Hugging Face authentication is required, authenticate locally using your own Hugging Face account.

---

# Running the Backend

From the project root:

    source .venv/bin/activate

Start FastAPI:

    uvicorn backend.main:app --reload

The server should start at:

    http://127.0.0.1:8000

---

# API Documentation

FastAPI automatically provides interactive API documentation.

Open:

    http://127.0.0.1:8000/docs

The current clinical endpoint is:

    POST /api/interview/turn

---

# Interview API

## Endpoint

    POST /api/interview/turn

## Request

Example:

    {
        "session_id": "demo-session-001",
        "language": "hi",
        "transcript": "मुझे तीन दिन से सीने में दर्द हो रहा है।"
    }

---

## Response

The endpoint returns:

    {
        "session_id": "demo-session-001",
        "language": "hi",
        "transcript": "मुझे तीन दिन से सीने में दर्द हो रहा है।",
        "clinical_data": {
            ...
        }
    }

The `clinical_data` object contains the normalized clinical information.

---

# Running the Voice Pipeline

The voice pipeline captures microphone input, detects speech, sends completed utterances to IndicConformer, and sends the resulting transcript to the FastAPI backend.

The current implementation is utterance-based rather than continuous token-level streaming.

The flow is:

    Microphone
        ↓
    Speech detection
        ↓
    Audio buffer
        ↓
    IndicConformer
        ↓
    Transcript
        ↓
    POST /api/interview/turn
        ↓
    Clinical extraction
        ↓
    Normalization

---

# Start the Backend First

Terminal 1:

    source .venv/bin/activate

    uvicorn backend.main:app --reload

Keep this terminal running.

---

# Start Voice Mode

Terminal 2:

    source .venv/bin/activate

    python -m voice.asr.live_stt

The program will:

1. Initialize the ASR model
2. Calibrate microphone noise
3. Wait for speech
4. Detect an utterance
5. Transcribe the utterance
6. Send the transcript to FastAPI
7. Display the normalized clinical data
8. Return to listening

The current voice loop continues until manually stopped.

Press:

    Ctrl+C

to stop the microphone session.

---

# Supported Language Configuration

The language is configured in:

    voice/asr/live_stt.py

For example:

    asr = ASRService(language="hi")

for Hindi.

For Assamese:

    asr = ASRService(language="as")

The language passed to the backend should match the language used by the ASR service.

---

# Testing the Clinical Pipeline

The recommended development workflow is:

    Transcript
        ↓
    ClinicalExtractor
        ↓
    ClinicalNormalizer

The local test script can be used during development:

    python backend/test_normalizer.py

This test:

1. Sends a sample transcript to the clinical extractor
2. Prints the extracted structure
3. Sends the extraction to the normalizer
4. Prints the normalized structure

These files are currently development/testing utilities and are not required by the production pipeline.

---

# Example Multilingual Test

Example Assamese input:

    মোৰ যোৱা দুসপ্তাহ ধৰি পেটৰ বিষ হৈ আছে।
    বিষটো মাজে মাজে বহুত বেছি হয়, বিশেষকৈ খোৱাৰ পিছত।
    লগতে মোৰ বমি বমি ভাব হয়, কিন্তু বমি হোৱা নাই।

Expected normalized concepts include:

    chief complaint:
        abdominal pain

    duration:
        2 weeks

    location:
        abdomen

    aggravating factor:
        eating

    associated symptom:
        nausea

    vomiting:
        present = false

The exact output may vary because the clinical extraction and normalization models are probabilistic.

---

# Clinical Safety Architecture

The clinical extractor is intentionally restricted to information extraction.

It should NOT:

- Diagnose diseases
- Prescribe medication
- Recommend treatment
- Invent symptoms
- Infer unstated medical history
- Convert symptoms directly into diagnoses

The eventual architecture will separate:

    Clinical Extraction
            ↓
    Clinical Normalization
            ↓
    Patient State
            ↓
    Red-Flag / Triage Layer
            ↓
    Question Engine
            ↓
    Clinical Summary

The red-flag/triage layer is intentionally separate from the extraction layer.

---

# Patient State

Patient State is planned but is not yet implemented.

The purpose of Patient State will be to combine information from multiple interview turns.

For example:

Turn 1:

    "I have had a headache for three days."

Turn 2:

    "It is mostly on the right side."

The system should eventually combine these into:

    {
        "name": "headache",
        "duration": "3 days",
        "location": "right side"
    }

rather than treating the two statements as unrelated symptoms.

---

# Development Principles

## Separation of Responsibilities

Each component should have a clear responsibility.

### ASR

    Audio → Transcript

### Clinical Extractor

    Transcript → Explicit clinical information

### Normalizer

    Extracted information → Canonical representation

### Patient State

    Multiple turns → Persistent patient information

### Question Engine

    Patient state → Next clinically relevant question

### Summary Generator

    Patient state → Physician-facing summary

Avoid putting multiple responsibilities into a single component.

---

# Git Guidelines

Do not commit:

    .env
    API keys
    Hugging Face tokens
    Model weights
    Model caches
    Patient audio
    Real patient data
    Temporary test artifacts

Before committing:

    git status

Review the staged files:

    git diff --cached

Then commit:

    git commit -m "feat: add clinical NLP pipeline"

Push the feature branch:

    git push -u origin feature/clinical-nlp

---

# Current Development Status

## Completed

- [x] IndicConformer ASR integration
- [x] Microphone input
- [x] Speech detection
- [x] Utterance-based transcription
- [x] FastAPI backend
- [x] Clinical extraction
- [x] Structured Pydantic output
- [x] Negation handling
- [x] Radiation field
- [x] Clinical normalization
- [x] Voice → FastAPI integration

## In Progress

- [ ] Persistent patient/session state
- [ ] Multi-turn clinical information merging
- [ ] Clinical question engine
- [ ] Red-flag / triage layer
- [ ] Physician-facing summary
- [ ] Frontend integration
- [ ] Automated tests

---

# Important Development Note

This project is currently a prototype.

Use synthetic or demonstration patient data during development.

Do not send identifiable real patient information to external AI APIs during development unless the project's privacy, security, consent, and deployment requirements have been properly addressed.