# 06 — Pipeline em Tempo Real

Conecta captura → VAD → transcrição → tradução em um fluxo contínuo com resultados parciais e finais.

---

## Estratégia de dois estados

O pipeline trabalha com dois tipos de resultado para a interface:

| Estado | Quando aparece | Cor sugerida |
|---|---|---|
| `partial` | A cada 800ms enquanto alguém fala | cinza claro |
| `translated` | Após pausa — frase confirmada | branco |

O usuário vê o texto parcial aparecer enquanto a pessoa ainda fala, e ele estabiliza quando há uma pausa.

---

## Fluxo de dados

```
Captura WASAPI (blocos de 500ms)
         │
         ▼
    VAD por bloco
         │
    ┌────┴────┐
    │ voz?    │
    sim       não
    │         │
    ▼         ▼
 acumula   silêncio
 no buffer  ≥ 800ms?
         │
         ▼
   segmento final
         │
    ┌────┴────────────────┐
    │                     │
    ▼                     ▼
transcrição           transcrição
parcial (rápida)      final (qualidade)
    │                     │
    ▼                     ▼
resultado parcial    tradução
via WebSocket        + resultado final
                     via WebSocket
```

---

## 6.1 Pipeline principal

```python
# services/speech-engine/pipeline/realtime_pipeline.py

import asyncio
import numpy as np
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from ..audio.capture import AudioCapture
from ..vad.detector import VoiceDetector
from ..vad.buffer import VoiceBuffer, AudioSegment
from ..transcription.whisper_engine import WhisperEngine
from ..translation.translator import Translator
from ..translation.glossary import apply_glossary

@dataclass
class SubtitleEvent:
    segment_id: str
    source_text: str
    translated_text: str | None
    status: str   # "partial" | "translated"
    started_at: float
    ended_at: float | None = None

class RealtimePipeline:
    def __init__(
        self,
        on_event: Callable[[SubtitleEvent], Awaitable[None]],
        model_size: str = "medium.en",
        partial_interval_s: float = 0.8,
    ):
        self.on_event = on_event
        self.partial_interval_s = partial_interval_s
        self.segment_counter = 0

        self.whisper = WhisperEngine(model_size)
        self.translator = Translator()
        self.detector = VoiceDetector()
        self.voice_buffer = VoiceBuffer(on_segment=self._on_final_segment)

        self._current_segment_id: str | None = None
        self._partial_buffer: list[np.ndarray] = []
        self._last_partial_time = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def process_chunk(self, audio: np.ndarray):
        confidence = self.detector.is_speech(audio)
        is_speech = confidence > 0.5

        if is_speech:
            if self._current_segment_id is None:
                self.segment_counter += 1
                self._current_segment_id = f"seg-{self.segment_counter}"
                self._partial_buffer = []
                self._last_partial_time = time.time()

            self._partial_buffer.append(audio)

            # Emitir parcial a cada N segundos
            if time.time() - self._last_partial_time >= self.partial_interval_s:
                self._emit_partial()
                self._last_partial_time = time.time()

        self.voice_buffer.push(audio, is_speech)

    def _emit_partial(self):
        if not self._partial_buffer or not self._current_segment_id:
            return

        audio = np.concatenate(self._partial_buffer)
        partial_text = self.whisper.transcribe_partial(audio)

        if not partial_text.strip():
            return

        event = SubtitleEvent(
            segment_id=self._current_segment_id,
            source_text=partial_text,
            translated_text=None,
            status="partial",
            started_at=time.time(),
        )

        if self._loop:
            asyncio.run_coroutine_threadsafe(self.on_event(event), self._loop)

    def _on_final_segment(self, segment: AudioSegment):
        segment_id = self._current_segment_id or f"seg-{self.segment_counter}"
        self._current_segment_id = None
        self._partial_buffer = []

        # Transcrição final
        result = self.whisper.transcribe(segment.audio)

        if not result.text.strip():
            return

        # Tradução
        translation = self.translator.translate(result.text)
        translated = apply_glossary(translation.translated_text)

        event = SubtitleEvent(
            segment_id=segment_id,
            source_text=result.text,
            translated_text=translated,
            status="translated",
            started_at=segment.started_at,
            ended_at=segment.ended_at,
        )

        if self._loop:
            asyncio.run_coroutine_threadsafe(self.on_event(event), self._loop)
```

---

## 6.2 Teste do pipeline completo

```python
# services/speech-engine/pipeline/test_pipeline.py

import asyncio
import numpy as np
import pyaudiowpatch as pyaudio
import threading
from realtime_pipeline import RealtimePipeline, SubtitleEvent

async def on_event(event: SubtitleEvent):
    if event.status == "partial":
        print(f"\r[parcial] {event.source_text}", end="")
    else:
        print(f"\n[EN] {event.source_text}")
        print(f"[PT] {event.translated_text}")
        print()

pipeline: RealtimePipeline | None = None

def audio_thread(loop: asyncio.AbstractEventLoop):
    global pipeline
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

    while True:
        data = stream.read(8000, exception_on_overflow=False)
        audio = np.frombuffer(data, dtype=np.float32)

        if loopback["maxInputChannels"] > 1:
            audio = audio.reshape(-1, loopback["maxInputChannels"]).mean(axis=1)

        pipeline.process_chunk(audio)

async def main():
    global pipeline
    loop = asyncio.get_event_loop()
    pipeline = RealtimePipeline(on_event=on_event)
    pipeline.start(loop)

    t = threading.Thread(target=audio_thread, args=(loop,), daemon=True)
    t.start()

    print("Pipeline completo ativo. Reproduza áudio em inglês...")
    print("Ctrl+C para encerrar\n")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
```

```powershell
python services/speech-engine/pipeline/test_pipeline.py
```

---

## 6.3 Latências esperadas (Fase 2 completa)

| Evento | Tempo após início da fala |
|---|---|
| Primeiro resultado parcial | ~800ms – 1.2s |
| Frase final em inglês | ~1s após pausa |
| Tradução em português | ~1.1s – 1.5s após pausa |

---

**Próximo passo:** [07-websocket-server.md](./07-websocket-server.md)
