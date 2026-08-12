# 04 — Motor de Transcrição (faster-whisper)

Transcreve os segmentos de áudio em inglês usando o Whisper rodando localmente na GPU.

---

## Por que faster-whisper

O faster-whisper é uma reimplementação do Whisper usando CTranslate2. Comparado ao Whisper original:

| | Whisper original | faster-whisper |
|---|---|---|
| Velocidade | 1x | 2–4x mais rápido |
| VRAM | base | ~50% menos |
| Quantização | float32 | float16, int8 |
| Streaming | não nativo | suportado |
| GPU | CUDA | CUDA + CPU |

---

## 4.1 Modelos disponíveis

| Modelo | VRAM | Velocidade | Qualidade |
|---|---|---|---|
| tiny.en | ~390 MB | muito rápido | baixa |
| base.en | ~580 MB | rápido | razoável |
| small.en | ~970 MB | bom | boa |
| **medium.en** | **~2.5 GB** | **ótimo** | **ótima** |
| large-v3 | ~3.1 GB | mais lento | excelente |
| distil-large-v3 | ~1.5 GB | rápido | muito boa |

Para o seu hardware, comece com `medium.en`. Se quiser testar qualidade máxima, `large-v3` também cabe nos 8 GB com folga.

O sufixo `.en` indica modelos treinados apenas para inglês — mais rápidos e precisos do que os multilíngues quando o idioma de entrada é fixo.

---

## 4.2 Download do modelo

```python
# O modelo é baixado automaticamente na primeira execução
# Para fazer o download antecipado:

from faster_whisper import WhisperModel

model = WhisperModel(
    "medium.en",
    device="cuda",
    compute_type="float16",
    download_root="./models",
)

print("Modelo carregado com sucesso")
```

O download do `medium.en` é de ~1.5 GB. Os arquivos ficam em `./models/`.

---

## 4.3 Motor de transcrição

```python
# services/speech-engine/transcription/whisper_engine.py

import numpy as np
import time
from faster_whisper import WhisperModel
from dataclasses import dataclass

@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_s: float
    processing_time_s: float
    is_final: bool

class WhisperEngine:
    def __init__(self, model_size: str = "medium.en", models_dir: str = "./models"):
        print(f"Carregando Whisper {model_size}...")
        start = time.time()

        self.model = WhisperModel(
            model_size,
            device="cuda",
            compute_type="float16",
            download_root=models_dir,
            num_workers=2,
        )

        load_time = time.time() - start
        print(f"Whisper {model_size} carregado em {load_time:.1f}s")

    def transcribe(self, audio: np.ndarray, language: str = "en") -> TranscriptionResult:
        start = time.time()

        segments, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=True,
            vad_filter=False,    # já filtramos com Silero antes
            word_timestamps=False,
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        processing_time = time.time() - start
        audio_duration = len(audio) / 16000

        return TranscriptionResult(
            text=text,
            language=info.language,
            duration_s=audio_duration,
            processing_time_s=processing_time,
            is_final=True,
        )

    def transcribe_partial(self, audio: np.ndarray) -> str:
        """Transcrição rápida para resultado parcial — usa beam_size menor."""
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            temperature=0.0,
            vad_filter=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
```

---

## 4.4 Teste de transcrição — Fase 1 completa

```python
# services/speech-engine/transcription/test_transcription.py

import numpy as np
import time
import pyaudiowpatch as pyaudio
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from vad.detector import VoiceDetector
from vad.buffer import VoiceBuffer, AudioSegment
from whisper_engine import WhisperEngine

engine = WhisperEngine("medium.en")
detector = VoiceDetector()

def on_segment(segment: AudioSegment):
    print(f"\n[Transcrevendo {segment.ended_at - segment.started_at:.1f}s de áudio...]")
    result = engine.transcribe(segment.audio)
    print(f"[EN] {result.text}")
    print(f"[{result.processing_time_s:.2f}s de processamento | fator {segment.ended_at - segment.started_at:.1f}x/{result.processing_time_s:.1f}x]")

voice_buffer = VoiceBuffer(on_segment=on_segment)

def main():
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

    print("Fase 1 completa — transcrição ao vivo. Reproduza áudio em inglês...")

    while True:
        data = stream.read(8000, exception_on_overflow=False)
        audio = np.frombuffer(data, dtype=np.float32)

        if loopback["maxInputChannels"] > 1:
            audio = audio.reshape(-1, loopback["maxInputChannels"]).mean(axis=1)

        confidence = detector.is_speech(audio)
        voice_buffer.push(audio, confidence > 0.5)

        print(f"\r{'🗣' if confidence > 0.5 else '·'} {confidence:.2f}", end="")

if __name__ == "__main__":
    main()
```

```powershell
python services/speech-engine/transcription/test_transcription.py
```

Saída esperada ao falar ou reproduzir áudio em inglês:

```
🗣 0.92
[Transcrevendo 4.2s de áudio...]
[EN] We need to review the dashboard before the deploy.
[0.43s de processamento | fator 4.2x/0.43x]
```

O fator mostra quantas vezes mais rápido que o tempo real o Whisper está processando. Qualquer valor acima de 1x significa que está em tempo real confortável.

---

## 4.5 Métricas esperadas no seu hardware

| Modelo | Tempo para 5s de áudio | Fator tempo real |
|---|---|---|
| small.en | ~200–350 ms | ~14–25x |
| medium.en | ~500–800 ms | ~6–10x |
| large-v3 | ~900–1400 ms | ~3–5x |

Esses números são para float16 em CUDA com RTX 4060 Ti.

---

**Próximo passo:** [05-translation-engine.md](./05-translation-engine.md)
