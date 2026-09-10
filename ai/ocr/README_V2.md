# 🩺 Medikiosk Document OCR Service

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![Gemini](https://img.shields.io/badge/Google%20GenAI-Gemini%20Vision-4285F4?logo=google&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)
![License](https://img.shields.io/badge/status-internal-lightgrey)

A portable, production-ready **FastAPI microservice** that uses **Gemini Vision models** to extract structured clinical data — prescriptions, lab reports, discharge summaries, and imaging reports — from medical images and PDFs into validated **Pydantic JSON schemas**.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Tech Stack](#-tech-stack)
- [Prerequisites & System Setup](#-prerequisites--system-setup)
- [Getting Started (New Machine Setup)](#-getting-started-new-machine-setup)
- [Testing the API](#-testing-the-api)
- [Engineering Highlights](#-engineering-highlights)
- [Troubleshooting](#-troubleshooting)
- [Security Notes](#-security-notes)

---

## 🔍 Overview

**Medikiosk Document OCR Service** ingests scanned/photographed medical documents (images or PDFs) and returns clean, structured JSON — ready to plug into downstream clinical systems. It is built to be resilient to upstream AI API instability and strict about output validation, so consuming services can trust the shape of the data they receive.

Supported document types:
- 💊 Prescriptions
- 🧪 Lab reports
- 🏥 Discharge summaries
- 🩻 Imaging reports

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Backend & Server** | FastAPI + Uvicorn |
| **AI Engine** | Google GenAI SDK (`google-genai`) |
| **Models** | `gemini-3.6-flash` (primary) → `gemini-2.0-flash` → `gemini-1.5-flash` (automatic fallback) |
| **Data Validation** | Pydantic v2 (strict `YYYY-MM-DD` dates, lab values, severity ratings, medication breakdowns) |
| **File Processing** | Pillow (PIL), pdf2image, Poppler |
| **Config/Secrets** | python-dotenv (`.env`, local only) |

---

## ⚙️ Prerequisites & System Setup

> ⚠️ **Important:** Installing the Python packages alone is **not enough**. This service depends on system-level software (Poppler) for PDF rendering. Skipping this step is the #1 cause of setup failures on a fresh machine.

### 1. Python

- Python **3.10+** is recommended.
- Verify with:
  ```bash
  python --version
  ```

### 2. Poppler (required for PDF rendering via `pdf2image`)

Choose the instructions for your OS:

<details>
<summary><strong>🪟 Windows</strong></summary>

1. Download the Poppler binary `.zip` for Windows.
2. Extract it somewhere permanent, e.g. `C:\poppler`.
3. Add the `bin` folder to your **System PATH** environment variable, e.g.:
   ```
   C:\poppler\Library\bin
   ```
4. **Restart your terminal** (or your machine) after updating PATH so the change takes effect.
5. Verify installation:
   ```powershell
   pdftoppm -v
   ```

</details>

<details>
<summary><strong>🍎 macOS</strong></summary>

```bash
brew install poppler
```

Verify installation:
```bash
pdftoppm -v
```

</details>

<details>
<summary><strong>🐧 Linux (Ubuntu/Debian)</strong></summary>

```bash
sudo apt-get install -y poppler-utils
```

Verify installation:
```bash
pdftoppm -v
```

</details>

---

## 🚀 Getting Started (New Machine Setup)

Follow these steps **in order** on a completely fresh laptop.

### Step 1 — Pull the latest code

```bash
git pull
```

### Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Create your local environment file

Create a file named **`.env`** inside the **`ai/ocr/`** directory (the same folder that contains `test_local.py`):

```
ai/ocr/.env
```

Add your Gemini API key inside it:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

> 🔑 Get your API key from [Google AI Studio](https://aistudio.google.com/).
> 🚫 **Never commit this file to Git** — it is already excluded via `.gitignore`.

### Step 4 — Launch the local server

```bash
cd ai/ocr
uvicorn test_local:app --reload
```

If everything is configured correctly, you should see Uvicorn start up and report that it's running on `http://127.0.0.1:8000`.

---

## 🧪 Testing the API

1. Open your browser to the interactive Swagger docs:
   ```
   http://127.0.0.1:8000/docs
   ```
2. Expand **`POST /extract`**.
3. Click **"Try it out"**.
4. Upload a test medical file (`.png`, `.jpg`, or `.pdf`).
5. Click **"Execute"**.
6. Review the structured JSON response returned in the response body.

---

## 🏗 Engineering Highlights

A quick summary of what's been built into this service and why:

### 🔐 Authentication Security
Moved off hardcoded credentials entirely. API keys are now loaded exclusively via environment variables using `python-dotenv`, and `.env` is included in `.gitignore` to prevent accidental secret leaks into version control.

### 🔁 503 Error Resilience
Implemented an automated retry loop across model tiers:

```
gemini-3.6-flash  →  gemini-2.0-flash  →  gemini-1.5-flash
```

This means transient `503 UNAVAILABLE` / high-demand responses from any single model tier no longer crash the `/extract` endpoint — the service seamlessly falls back to the next available model.

### ✅ Schema Validation
Custom Pydantic v2 validators enforce:
- Strict ISO 8601 (`YYYY-MM-DD`) date formatting
- Structured lab value fields
- Severity rating constraints
- Medication breakdown structures

This guarantees downstream consumers always receive predictable, well-typed JSON.

### 📄 Multi-format Processing
Supports `PNG`, `JPEG`, `WEBP`, `BMP`, and **multi-page PDFs**, using temporary file handling with automated cleanup after each extraction request.

---

## 🆘 Troubleshooting

| Error / Symptom | Cause | Fix |
|---|---|---|
| `GEMINI_API_KEY environment variable is not configured` | The `.env` file is missing or misplaced | Confirm `.env` exists inside `ai/ocr/` (same folder as `test_local.py`) and contains `GEMINI_API_KEY=...` |
| `PDFInfoNotInstalledError` / "Poppler dependency missing on server" | Poppler isn't installed, or its `bin` folder isn't on your System PATH | Reinstall Poppler per the [Prerequisites](#️-prerequisites--system-setup) section above, and restart your terminal after updating PATH |
| `502 Bad Gateway` / Model Error | Invalid API key, or Google API is experiencing downtime across **all** fallback model tiers | Double-check your API key in `.env`; if the key is valid, check [Google Cloud/AI Studio status](https://aistudio.google.com/) for an outage |

---

## 🔒 Security Notes

- Your `.env` file contains a **secret API key** — it must never be committed to Git.
- `.env` is already listed in `.gitignore`; do not remove it from there.
- Each teammate should generate/use their **own** Gemini API key rather than sharing one.
- If a key is ever accidentally committed or exposed, rotate it immediately in Google AI Studio.

---

<p align="center">Made for the Medikiosk engineering team 💙</p>
