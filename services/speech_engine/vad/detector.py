import torch
import numpy as np
from silero_vad import load_silero_vad

SAMPLE_RATE = 16000
# 0.5 perdia fala baixa de reunião no loopback (headset / volume do Windows baixo).
# 0.35 ainda rejeita teclado e ruído de fundo.
THRESHOLD = 0.35
CHUNK_SAMPLES = 512   # silero exige multiplo de 512 a 16kHz


class VoiceDetector:
    def __init__(self):
        self.model = load_silero_vad()
        self.model.eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cuda":
            self.model = self.model.cuda()

    def confidence(self, audio: np.ndarray) -> float:
        # Silero: blocos de 512 @ 16kHz. Média de vários blocos do chunk
        # (antes só olhava os primeiros 32ms de um chunk de 500ms).
        if len(audio) < CHUNK_SAMPLES:
            audio = np.pad(audio, (0, CHUNK_SAMPLES - len(audio)))

        n = max(1, len(audio) // CHUNK_SAMPLES)
        scores = []
        with torch.no_grad():
            for i in range(n):
                chunk = audio[i * CHUNK_SAMPLES : (i + 1) * CHUNK_SAMPLES]
                if len(chunk) < CHUNK_SAMPLES:
                    break
                tensor = torch.from_numpy(chunk.astype(np.float32, copy=False))
                if self.device == "cuda":
                    tensor = tensor.cuda()
                scores.append(float(self.model(tensor, SAMPLE_RATE).item()))

        return max(scores) if scores else 0.0

    def is_speech(self, audio: np.ndarray) -> tuple[bool, float]:
        score = self.confidence(audio)
        return score >= THRESHOLD, score
