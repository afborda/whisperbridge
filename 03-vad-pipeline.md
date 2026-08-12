# 03 — Detecção de Voz (Silero VAD)

O VAD (Voice Activity Detection) decide quando alguém está falando e quando há pausa. Isso evita mandar silêncio ao Whisper e ajuda a delimitar frases.

---

## Por que usar VAD

Sem VAD:
- O Whisper recebe blocos contínuos, mesmo em silêncio
- Gera transcrições de ruído como texto ("hmm", "uh", "...")
- Desperdiça GPU processando silêncio
- Não sabe onde uma frase termina

Com VAD:
- Só ativa o Whisper quando há voz real
- Delimita início e fim de cada segmento de fala
- Reduz carga de GPU em ~60% em reuniões com pausas
- Permite montar segmentos coerentes para tradução

---

## 3.1 Instalação

```powershell
pip install silero-vad
```

O modelo é baixado automaticamente na primeira execução (~1 MB).

---

## 3.2 Detector básico

```python
# services/speech-engine/vad/detector.py

import torch
import numpy as np
from silero_vad import load_silero_vad, get_speech_timestamps

SAMPLE_RATE = 16000
THRESHOLD = 0.5          # confiança mínima para considerar voz
MIN_SPEECH_MS = 250      # fala mínima de 250ms para não ignorar
MIN_SILENCE_MS = 600     # pausa de 600ms indica fim de segmento

class VoiceDetector:
    def __init__(self):
        self.model = load_silero_vad()
        self.model.eval()

        if torch.cuda.is_available():
            self.model = self.model.cuda()
            self.device = "cuda"
        else:
            self.device = "cpu"

        print(f"VAD carregado em: {self.device}")

    def is_speech(self, audio: np.ndarray) -> float:
        tensor = torch.from_numpy(audio)
        if self.device == "cuda":
            tensor = tensor.cuda()

        with torch.no_grad():
            confidence = self.model(tensor, SAMPLE_RATE).item()

        return confidence

    def get_segments(self, audio: np.ndarray) -> list[dict]:
        tensor = torch.from_numpy(audio)
        if self.device == "cuda":
            tensor = tensor.cuda()

        segments = get_speech_timestamps(
            tensor,
            self.model,
            sampling_rate=SAMPLE_RATE,
            threshold=THRESHOLD,
            min_speech_duration_ms=MIN_SPEECH_MS,
            min_silence_duration_ms=MIN_SILENCE_MS,
        )

        return [
            {
                "start": s["start"] / SAMPLE_RATE,
                "end": s["end"] / SAMPLE_RATE,
                "audio": audio[s["start"]:s["end"]],
            }
            for s in segments
        ]
```

---

## 3.3 Buffer de voz — acumulador de segmentos

O áudio chega em blocos de 500ms. O buffer acumula e decide quando um segmento está pronto para ser transcrito.

```python
# services/speech-engine/vad/buffer.py

import numpy as np
import time
from dataclasses import dataclass, field

SAMPLE_RATE = 16000
SILENCE_THRESHOLD_S = 0.8    # 800ms de silêncio = frase encerrada
MAX_SEGMENT_S = 15.0         # segmento máximo antes de forçar envio

@dataclass
class AudioSegment:
    audio: np.ndarray
    started_at: float
    ended_at: float | None = None
    is_final: bool = False

class VoiceBuffer:
    def __init__(self, on_segment):
        self.on_segment = on_segment      # callback quando segmento está pronto
        self.buffer = np.array([], dtype=np.float32)
        self.last_speech_time = 0.0
        self.segment_start = 0.0
        self.in_speech = False

    def push(self, audio: np.ndarray, is_speech: bool):
        now = time.time()

        if is_speech:
            if not self.in_speech:
                self.in_speech = True
                self.segment_start = now
                self.buffer = np.array([], dtype=np.float32)

            self.buffer = np.concatenate([self.buffer, audio])
            self.last_speech_time = now

        elif self.in_speech:
            self.buffer = np.concatenate([self.buffer, audio])
            silence_duration = now - self.last_speech_time

            # Pausa longa ou segmento muito grande = enviar
            segment_duration = now - self.segment_start
            should_flush = (
                silence_duration >= SILENCE_THRESHOLD_S
                or segment_duration >= MAX_SEGMENT_S
            )

            if should_flush:
                segment = AudioSegment(
                    audio=self.buffer.copy(),
                    started_at=self.segment_start,
                    ended_at=now,
                    is_final=True,
                )
                self.on_segment(segment)
                self.in_speech = False
                self.buffer = np.array([], dtype=np.float32)
```

---

## 3.4 Teste do VAD

```python
# services/speech-engine/vad/test_vad.py

import numpy as np
import time
import pyaudiowpatch as pyaudio
from detector import VoiceDetector
from buffer import VoiceBuffer

def on_segment(segment):
    duration = segment.ended_at - segment.started_at
    print(f"\n[SEGMENTO] {duration:.1f}s — {len(segment.audio)} amostras prontas para transcrição")

def main():
    detector = VoiceDetector()
    voice_buffer = VoiceBuffer(on_segment=on_segment)

    p = pyaudio.PyAudio()
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_output = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

    loopback = None
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev["name"] == default_output["name"] and dev["isLoopbackDevice"]:
            loopback = dev
            break

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=loopback["maxInputChannels"],
        rate=int(loopback["defaultSampleRate"]),
        input=True,
        input_device_index=loopback["index"],
        frames_per_buffer=8000,
    )

    print("Monitorando voz — fale ou reproduza áudio...")

    while True:
        data = stream.read(8000, exception_on_overflow=False)
        audio = np.frombuffer(data, dtype=np.float32)

        if loopback["maxInputChannels"] > 1:
            audio = audio.reshape(-1, loopback["maxInputChannels"]).mean(axis=1)

        confidence = detector.is_speech(audio)
        is_speech = confidence > 0.5

        indicator = "🗣" if is_speech else "·"
        print(f"\r{indicator} conf: {confidence:.2f}", end="")

        voice_buffer.push(audio, is_speech)

if __name__ == "__main__":
    main()
```

```powershell
python services/speech-engine/vad/test_vad.py
```

O terminal deve mostrar `🗣` quando detectar voz e `·` em silêncio. Ao terminar uma frase, aparece `[SEGMENTO]` com o tamanho do áudio capturado.

---

**Próximo passo:** [04-transcription-engine.md](./04-transcription-engine.md)
