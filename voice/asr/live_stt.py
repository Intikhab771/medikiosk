import queue
import time

import numpy as np
import sounddevice as sd
import torch
from transformers import AutoModel


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_NAME = "ai4bharat/indic-conformer-600m-multilingual"

SAMPLE_RATE = 16000

# Microphone block size
BLOCK_DURATION = 0.25
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)

# How long silence must last before transcription
SILENCE_DURATION = 0.8

# Ignore extremely short sounds
MIN_SPEECH_DURATION = 0.5

# Maximum length of one utterance
MAX_SPEECH_DURATION = 15.0


# ============================================================
# LOAD MODEL
# ============================================================

print("Loading IndicConformer...")

model = AutoModel.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True
)

device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Using device: {device}")

model = model.to(device)
model.eval()

print("Model loaded.\n")


# ============================================================
# AUDIO QUEUE
# ============================================================

audio_queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):

    if status:
        print(f"\nAudio status: {status}")

    audio_queue.put(indata.copy())


# ============================================================
# CALCULATE AUDIO LEVEL
# ============================================================

def get_rms(audio):

    return float(np.sqrt(np.mean(audio ** 2)))


# ============================================================
# TRANSCRIBE
# ============================================================

def transcribe(audio):

    # Flatten
    audio = audio.flatten()

    # Convert NumPy → PyTorch
    audio_tensor = torch.from_numpy(audio).float()

    # [samples] → [1, samples]
    audio_tensor = audio_tensor.unsqueeze(0)

    # Move to device
    audio_tensor = audio_tensor.to(device)

    with torch.inference_mode():

        text = model(
            audio_tensor,
            "hi",
            "ctc"
        )

    return text


# ============================================================
# CALIBRATE MICROPHONE
# ============================================================

def calibrate_noise():

    print("Calibrating microphone...")
    print("Please remain silent for 2 seconds.")

    levels = []

    start = time.time()

    while time.time() - start < 2.0:

        block = audio_queue.get()

        samples = block[:, 0]

        rms = get_rms(samples)

        levels.append(rms)

    noise_floor = float(np.median(levels))

    # Speech threshold is several times above background noise.
    threshold = max(noise_floor * 3.0, 0.003)

    print(f"Noise floor: {noise_floor:.6f}")
    print(f"Speech threshold: {threshold:.6f}")
    print()

    return threshold


# ============================================================
# MAIN
# ============================================================

print("========================================")
print("       MediKiosk Live Speech-to-Text")
print("========================================")
print()
print("Language: Hindi")
print("Press Ctrl+C to stop.")
print()


try:

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SIZE,
        callback=audio_callback
    ):

        # ----------------------------------------------------
        # CALIBRATION
        # ----------------------------------------------------

        threshold = calibrate_noise()

        print("Listening...")
        print("Speak normally.\n")

        speech_buffer = []

        speech_started = False

        speech_time = 0.0
        silence_time = 0.0

        while True:

            # ------------------------------------------------
            # GET AUDIO BLOCK
            # ------------------------------------------------

            block = audio_queue.get()

            samples = block[:, 0]

            rms = get_rms(samples)

            # ------------------------------------------------
            # DEBUG LEVEL
            # ------------------------------------------------

            # Uncomment this if you want to see microphone level.
            #
            # print(
            #     f"\rMic: {rms:.5f} | Threshold: {threshold:.5f}",
            #     end=""
            # )

            # ------------------------------------------------
            # SPEECH
            # ------------------------------------------------

            if rms > threshold:

                if not speech_started:

                    print("🎙 Speech detected...")

                    speech_started = True

                    speech_buffer = []

                    speech_time = 0.0
                    silence_time = 0.0

                speech_buffer.append(samples)

                speech_time += BLOCK_DURATION

                # Reset silence timer
                silence_time = 0.0

                # ------------------------------------------------
                # MAXIMUM UTTERANCE LENGTH
                # ------------------------------------------------

                if speech_time >= MAX_SPEECH_DURATION:

                    print("\nMaximum utterance length reached.")
                    print("Processing...")

                    audio = np.concatenate(speech_buffer)

                    start = time.time()

                    try:

                        text = transcribe(audio)

                        elapsed = time.time() - start

                        print()
                        print("Patient:")
                        print(text)

                        print()
                        print(f"Processing time: {elapsed:.2f}s")
                        print("----------------------------------------")
                        print("Listening...\n")

                    except Exception as e:

                        print("\nTranscription error:")
                        print(e)

                    # Reset
                    speech_buffer = []
                    speech_started = False
                    speech_time = 0.0
                    silence_time = 0.0

            # ------------------------------------------------
            # SILENCE
            # ------------------------------------------------

            else:

                if speech_started:

                    # Keep the silence block.
                    # This preserves the end of the sentence.
                    speech_buffer.append(samples)

                    silence_time += BLOCK_DURATION

                    # ------------------------------------------------
                    # USER FINISHED SPEAKING
                    # ------------------------------------------------

                    if (
                        silence_time >= SILENCE_DURATION
                        and speech_time >= MIN_SPEECH_DURATION
                    ):

                        print("Processing...")

                        audio = np.concatenate(speech_buffer)

                        start = time.time()

                        try:

                            text = transcribe(audio)

                            elapsed = time.time() - start

                            print()
                            print("Patient:")
                            print(text)

                            print()
                            print(f"Processing time: {elapsed:.2f}s")
                            print("----------------------------------------")
                            print("Listening...\n")

                        except Exception as e:

                            print("\nTranscription error:")
                            print(e)

                        # Reset
                        speech_buffer = []
                        speech_started = False
                        speech_time = 0.0
                        silence_time = 0.0


except KeyboardInterrupt:

    print("\nStopping microphone...")

except Exception as e:

    print("\nMicrophone error:")
    print(e)