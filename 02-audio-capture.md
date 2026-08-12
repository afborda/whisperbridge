# 02 — Captura de Áudio (WASAPI Loopback)

Captura o áudio que está sendo reproduzido pelo Windows — o som que sai pelo seu fone ou caixa de som, sem precisar de microfone.

---

## Como funciona o WASAPI Loopback

O Windows Audio Session API (WASAPI) no modo loopback permite capturar o stream de áudio que o sistema está enviando ao dispositivo de saída. O Teams, Meet ou qualquer outro app não precisa saber que está sendo capturado.

```
Microsoft Teams
      ↓
Windows Audio Engine (WASAPI)
      ↓ (loopback)
WhisperBridge captura aqui
      ↓
Pipeline de transcrição
```

---

## 2.1 Identificar o dispositivo de saída

```python
import sounddevice as sd

# Listar todos os dispositivos
devices = sd.query_devices()
for i, dev in enumerate(devices):
    if dev['max_input_channels'] > 0 or dev['max_output_channels'] > 0:
        print(f"[{i}] {dev['name']} | in:{dev['max_input_channels']} out:{dev['max_output_channels']}")
```

Procure pelo seu dispositivo de saída, geralmente algo como:
- `Headset Stereo (Realtek HD Audio)`
- `Speakers (Realtek)`
- `CABLE Output (VB-Audio)`

---

## 2.2 Captura com pyaudiowpatch

```python
import pyaudiowpatch as pyaudio
import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_MS = 500          # blocos de 500ms
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_MS / 1000)

def get_loopback_device(p):
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_output = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

    # Procurar o dispositivo loopback correspondente
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev["name"] == default_output["name"] and dev["isLoopbackDevice"]:
            return dev
    raise RuntimeError("Dispositivo loopback nao encontrado")

def capture_loop(callback):
    p = pyaudio.PyAudio()
    device = get_loopback_device(p)

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=device["maxInputChannels"],
        rate=int(device["defaultSampleRate"]),
        input=True,
        input_device_index=device["index"],
        frames_per_buffer=CHUNK_SIZE,
    )

    print(f"Capturando: {device['name']} @ {device['defaultSampleRate']} Hz")

    try:
        while True:
            raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.float32)

            # Converter para mono se necessário
            if device["maxInputChannels"] > 1:
                audio = audio.reshape(-1, device["maxInputChannels"]).mean(axis=1)

            # Reamostrar para 16 kHz se necessário
            if int(device["defaultSampleRate"]) != SAMPLE_RATE:
                audio = resample(audio, int(device["defaultSampleRate"]))

            callback(audio)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
```

---

## 2.3 Reamostrador para 16 kHz

O Whisper espera áudio em 16 kHz mono. Dispositivos de saída normalmente operam em 44100 Hz ou 48000 Hz.

```python
import numpy as np
from scipy.signal import resample_poly
from math import gcd

def resample(audio: np.ndarray, original_rate: int, target_rate: int = 16000) -> np.ndarray:
    if original_rate == target_rate:
        return audio

    divisor = gcd(original_rate, target_rate)
    up = target_rate // divisor
    down = original_rate // divisor

    return resample_poly(audio, up, down).astype(np.float32)
```

---

## 2.4 Teste de captura — Fase 1

Script mínimo para confirmar que o áudio está sendo capturado. Rode durante uma reunião ou coloque uma música para testar.

```python
# services/speech-engine/audio/test_capture.py

import pyaudiowpatch as pyaudio
import numpy as np
import time

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

    if not loopback:
        print("ERRO: dispositivo loopback nao encontrado")
        return

    print(f"Capturando: {loopback['name']}")
    print(f"Sample rate: {loopback['defaultSampleRate']} Hz")
    print(f"Canais: {loopback['maxInputChannels']}")
    print("Iniciando por 10 segundos...")

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=loopback["maxInputChannels"],
        rate=int(loopback["defaultSampleRate"]),
        input=True,
        input_device_index=loopback["index"],
        frames_per_buffer=1024,
    )

    start = time.time()
    total_frames = 0

    while time.time() - start < 10:
        data = stream.read(1024, exception_on_overflow=False)
        audio = np.frombuffer(data, dtype=np.float32)
        volume = np.abs(audio).mean()
        total_frames += len(audio)

        bar = "█" * int(volume * 100)
        print(f"\rVolume: {bar:<30} {volume:.4f}", end="")

    stream.stop_stream()
    stream.close()
    p.terminate()

    print(f"\n\nTotal de frames capturados: {total_frames}")
    print("Captura OK")

if __name__ == "__main__":
    main()
```

Executar:

```powershell
python services/speech-engine/audio/test_capture.py
```

O volume deve subir enquanto há áudio sendo reproduzido no sistema.

---

## Limitação conhecida

O loopback captura todo o áudio do dispositivo de saída. Músicas, notificações e outros apps entrarão no mesmo stream.

Na versão inicial isso é aceitável. Em versões futuras, é possível capturar especificamente o processo do Teams usando a API de sessões de áudio do Windows, mas envolve código C++ ou interop.

---

**Próximo passo:** [03-vad-pipeline.md](./03-vad-pipeline.md)
