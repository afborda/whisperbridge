import time
import numpy as np
from dataclasses import dataclass, field
from typing import Callable

SAMPLE_RATE = 16000

# Pausa que fecha o segmento. 0.32s era agressivo demais: hesitação e respiração no
# meio de uma frase duram 0.2–0.35s, então a frase era cortada antes do fim.
# 0.65s ≈ pausa de fim de frase de verdade. Custa ~0.3s de latência e devolve
# frases inteiras — o preview "live" cobre a sensação de tempo real.
SILENCE_FLUSH_S = 0.65

# Corte forçado mesmo sem pausa. 1.8s dava ~4-5 palavras: o Whisper recebia fragmento
# truncado (o que mais induz alucinação) e o tradutor recebia oração sem sujeito.
# 6.0s ≈ 13-15 palavras = frase completa.
MAX_SEGMENT_S = 6.0

# Segmento curto demais não é fala útil — é clique, respiração ou ruído. O Whisper
# em cima disso inventa texto ("Thanks for watching"), então descartamos antes.
MIN_SEGMENT_S = 0.45


@dataclass
class AudioSegment:
    audio: np.ndarray
    started_at: float
    ended_at: float
    duration_s: float = field(init=False)

    def __post_init__(self):
        self.duration_s = self.ended_at - self.started_at


class VoiceBuffer:
    def __init__(self, on_segment: Callable[[AudioSegment], None]):
        self.on_segment = on_segment
        self._buffer: list[np.ndarray] = []
        self._in_speech = False
        self._segment_start = 0.0
        self._last_speech_at = 0.0

    def push(self, audio: np.ndarray, is_speech: bool):
        now = time.time()

        if is_speech:
            if not self._in_speech:
                self._in_speech = True
                self._segment_start = now
                self._buffer = []
            self._buffer.append(audio)
            self._last_speech_at = now

            # CRÍTICO: cortar durante fala contínua (antes só checava no silêncio)
            if now - self._segment_start >= MAX_SEGMENT_S:
                self._flush(now, continue_speech=True)
            return

        if not self._in_speech:
            return

        # ainda "em fala" mas este frame é silêncio — acumula e decide flush
        self._buffer.append(audio)
        silence = now - self._last_speech_at
        duration = now - self._segment_start

        if silence >= SILENCE_FLUSH_S or duration >= MAX_SEGMENT_S:
            self._flush(now, continue_speech=False)

    def _flush(self, ended_at: float, continue_speech: bool = False):
        if not self._buffer:
            return

        audio = np.concatenate(self._buffer)
        # Descarta blip de ruído antes de gastar GPU e antes de virar alucinação
        if len(audio) / SAMPLE_RATE < MIN_SEGMENT_S:
            self._buffer = []
            self._in_speech = continue_speech
            if continue_speech:
                self._segment_start = ended_at
            return

        segment = AudioSegment(
            audio=audio,
            started_at=self._segment_start,
            ended_at=ended_at,
        )

        if continue_speech:
            # monólogo longo: envia pedaço e continua capturando
            self._buffer = []
            self._segment_start = ended_at
            self._in_speech = True
        else:
            self._in_speech = False
            self._buffer = []

        self.on_segment(segment)
