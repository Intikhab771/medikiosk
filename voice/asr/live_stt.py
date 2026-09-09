import queue
import time

import numpy as np
import sounddevice as sd

from .model import ASRService


# ============================================================
# CONFIGURATION
# ============================================================

SAMPLE_RATE = 16000

BLOCK_DURATION = 0.25
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)

SILENCE_DURATION = 0.8

MIN_SPEECH_DURATION = 0.5

MAX_SPEECH_DURATION = 15.0


# ============================================================
# LOAD ASR SERVICE
# ============================================================

asr = ASRService(language="hi")


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
            # SPEECH
            # ------------------------------------------------

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

                # ------------------------------------------------
                # MAXIMUM UTTERANCE LENGTH
                # ------------------------------------------------

                if speech_time >= MAX_SPEECH_DURATION:

                    print("\nMaximum utterance length reached.")
                    print("Processing...")

                    audio = np.concatenate(speech_buffer)

                    start = time.time()

                    try:

                        text = asr.transcribe(audio)

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

                    speech_buffer = []
                    speech_started = False
                    speech_time = 0.0
                    silence_time = 0.0

            # ------------------------------------------------
            # SILENCE
            # ------------------------------------------------

            else:

                if speech_started:

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

                            text = asr.transcribe(audio)

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

                        speech_buffer = []
                        speech_started = False
                        speech_time = 0.0
                        silence_time = 0.0


except KeyboardInterrupt:

    print("\nStopping microphone...")

except Exception as e:

    print("\nMicrophone error:")
    print(e)