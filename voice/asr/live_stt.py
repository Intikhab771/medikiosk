import json
import urllib.request
import urllib.error
import os
import queue
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

BACKEND_URL = "http://127.0.0.1:8000/api/interview/turn"
SESSION_ID = "demo-session-001"


def send_to_backend(question_id, transcript, structured_answer):
    payload = {
        "session_id": SESSION_ID,
        "language": asr.language,
        "question_id": question_id,
        "transcript": transcript,
        "structured_answer": structured_answer,
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        BACKEND_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.URLError as exc:
        print(f"Backend error: {exc}")
        return None

# Make brain/src importable when this file is run from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRAIN_SRC = PROJECT_ROOT / "brain" / "src"
if str(BRAIN_SRC) not in sys.path:
    sys.path.insert(0, str(BRAIN_SRC))

from .model import ASRService
from ai.extractor import AnswerExtractor
from engine.adaptive_engine import AdaptiveEngine
from engine.loader import load_clinical_parameters, load_question_bank
from engine.patient_state import PatientState


# ============================================================
# CONFIGURATION
# ============================================================

SAMPLE_RATE = 16000

BLOCK_DURATION = 0.25
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)

SILENCE_DURATION = 0.8
MIN_SPEECH_DURATION = 0.5
MAX_SPEECH_DURATION = 15.0

# Demo defaults. The frontend can eventually provide these.
LANGUAGE = os.getenv("MEDIKIOSK_LANGUAGE", "hi")
COMPLAINT = os.getenv("MEDIKIOSK_COMPLAINT", "chest_pain")
SESSION_ID = os.getenv("MEDIKIOSK_SESSION_ID", "voice-demo-001")


# ============================================================
# LOAD SERVICES
# ============================================================

print("Loading MediKiosk services...")

asr = ASRService(language=LANGUAGE)
answer_extractor = AnswerExtractor()

QB = load_question_bank(PROJECT_ROOT / "brain" / "data" / "question_bank.json")
CP = load_clinical_parameters(
    PROJECT_ROOT / "brain" / "data" / "clinical_parameters.json"
)
engine = AdaptiveEngine(QB, CP)

state = PatientState(
    session_id=SESSION_ID,
    complaint=COMPLAINT,
)

print("Services loaded.\n")


# ============================================================
# AUDIO QUEUE
# ============================================================

audio_queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"\nAudio status: {status}")
    audio_queue.put(indata.copy())


def get_rms(audio):
    return float(np.sqrt(np.mean(audio ** 2)))


# ============================================================
# MICROPHONE CALIBRATION
# ============================================================

def calibrate_noise():
    print("Calibrating microphone...")
    print("Please remain silent for 2 seconds.")

    levels = []
    start = time.time()

    while time.time() - start < 2.0:
        block = audio_queue.get()
        samples = block[:, 0]
        levels.append(get_rms(samples))

    noise_floor = float(np.median(levels))
    threshold = max(noise_floor * 3.0, 0.003)

    print(f"Noise floor: {noise_floor:.6f}")
    print(f"Speech threshold: {threshold:.6f}\n")

    return threshold


# ============================================================
# PROCESS ONE PATIENT UTTERANCE
# ============================================================

def process_utterance(audio):
    """ASR -> AnswerExtractor -> deterministic Brain engine."""

    start = time.time()

    # 1. Speech -> transcript
    transcript = asr.transcribe(audio)
    asr_elapsed = time.time() - start

    print(f"\nPatient:\n{transcript}")
    print(f"ASR time: {asr_elapsed:.2f}s")


    if not transcript or not str(transcript).strip():
        print("No transcript produced.")
        return

    print("\nPatient:")
    print(transcript)
    print(f"ASR time: {asr_elapsed:.2f}s")

    # 2. The engine already has the active question.
    result = engine.get_next_question(state)

    if result.next_question is None:
        print(f"Interview status: {result.status.value}")
        return

    question = result.next_question

    # 3. Natural language -> structured answer.
    try:
        structured_value = answer_extractor.extract(
            question,
            str(transcript),
        )
    except Exception as exc:
        print(f"\nAnswer extraction error: {exc}")
        print("The answer was NOT submitted to the engine.")
        return

    print("Structured answer:")
    print(structured_value)

    # 4. Structured answer -> deterministic engine.
    try:
        engine.submit_answer(
            state,
            question["id"],
            structured_value,
        )
    except Exception as exc:
        print(f"\nEngine rejected the structured answer: {exc}")
        print("The answer was NOT accepted.")
        return
        # 5. Send the accepted answer to the backend.
    backend_result = send_to_backend(
        question["id"],
        str(transcript),
        structured_value,
    )

    if backend_result:
        print("\nBackend:")
        print(json.dumps(backend_result, indent=2, ensure_ascii=False))

    # 6. Engine decides what happens next.
    next_result = engine.get_next_question(state)

    print("\nEngine:")
    print(f"Status: {next_result.status.value}")

    if next_result.red_flags:
        print("RED FLAG:")
        for flag in next_result.red_flags:
            print(f"  [{flag.severity}] {flag.reason}")

    if next_result.next_question is not None:
        print("\nNext question:")
        print(next_result.next_question["text"])
    else:
        print("No further question.")

    print("----------------------------------------\n")


# ============================================================
# MAIN
# ============================================================

print("========================================")
print("       MediKiosk Voice Interview")
print("========================================")
print(f"Language: {LANGUAGE}")
print(f"Complaint: {COMPLAINT}")
print(f"Session: {SESSION_ID}")
print("Press Ctrl+C to stop.")
print()

# Get the first question before opening the microphone.
initial_result = engine.get_next_question(state)

if initial_result.next_question is None:
    print("Unable to start interview:")
    print(initial_result.to_dict())
    raise SystemExit(1)

print("First question:")
print(initial_result.next_question["text"])
print()

try:
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SIZE,
        callback=audio_callback,
    ):
        threshold = calibrate_noise()

        print("Listening...")
        print("Speak your answer after each question.\n")

        speech_buffer = []
        speech_started = False
        speech_time = 0.0
        silence_time = 0.0

        while True:
            block = audio_queue.get()
            samples = block[:, 0]
            rms = get_rms(samples)

            if rms > threshold:
                if not speech_started:
                    print("Speech detected...")
                    speech_started = True
                    speech_buffer = []
                    speech_time = 0.0
                    silence_time = 0.0

                speech_buffer.append(samples)
                speech_time += BLOCK_DURATION
                silence_time = 0.0

                if speech_time >= MAX_SPEECH_DURATION:
                    print("\nMaximum utterance length reached.")
                    print("Processing...")
                    process_utterance(np.concatenate(speech_buffer))

                    speech_buffer = []
                    speech_started = False
                    speech_time = 0.0
                    silence_time = 0.0

            elif speech_started:
                speech_buffer.append(samples)
                silence_time += BLOCK_DURATION

                if (
                    silence_time >= SILENCE_DURATION
                    and speech_time >= MIN_SPEECH_DURATION
                ):
                    print("Processing...")
                    process_utterance(np.concatenate(speech_buffer))

                    speech_buffer = []
                    speech_started = False
                    speech_time = 0.0
                    silence_time = 0.0

                    # Stop automatically after escalation or completion.
                    if state.is_escalated() or engine.get_next_question(state).next_question is None:
                        print("Interview finished.")
                        break

except KeyboardInterrupt:
    print("\nStopping microphone...")

except Exception as exc:
    print(f"\nMicrophone error: {exc}")

if __name__ == "__main__":
    print("Starting MediKiosk voice interview...")