import numpy as np
import torch
from transformers import AutoModel


MODEL_NAME = "ai4bharat/indic-conformer-600m-multilingual"


class ASRService:
    def __init__(self, language="hi"):
        self.language = language

        print("Loading IndicConformer...")

        self.model = AutoModel.from_pretrained(
            MODEL_NAME,
            trust_remote_code=True
        )

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"Using device: {self.device}")

        self.model = self.model.to(self.device)
        self.model.eval()

        print("Model loaded.\n")

    def transcribe(self, audio):
        """
        Transcribe a NumPy audio waveform.

        Parameters
        ----------
        audio : numpy.ndarray
            Mono float32 audio at 16 kHz.

        Returns
        -------
        str
            Transcribed text.
        """

        # Make sure the input is a NumPy array
        audio = np.asarray(audio, dtype=np.float32)

        # Flatten to [samples]
        audio = audio.flatten()

        # NumPy -> PyTorch
        audio_tensor = torch.from_numpy(audio).float()

        # Model expects [1, samples]
        audio_tensor = audio_tensor.unsqueeze(0)

        # Move to CPU/GPU
        audio_tensor = audio_tensor.to(self.device)

        with torch.inference_mode():

            text = self.model(
                audio_tensor,
                self.language,
                "ctc"
            )

        return text