"""
Teste de captura WASAPI — Passo 02
Roda por 15 segundos mostrando o volume em tempo real.
Reproduza qualquer audio no computador para ver a barra subir.
"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pyaudiowpatch as pyaudio
from services.speech_engine.audio.capture import (
    get_loopback_device,
    list_loopback_devices,
    resample_audio,
    to_mono,
    SAMPLE_RATE,
)

DURATION_S = 15
CHUNK = 8000


def main():
    print("\n=== WhisperBridge — Teste de Captura WASAPI ===\n")

    devices = list_loopback_devices()
    if not devices:
        print("ERRO: nenhum dispositivo loopback encontrado.")
        print("Verifique se pyaudiowpatch esta instalado corretamente.")
        sys.exit(1)

    print("Dispositivos loopback disponiveis:")
    for d in devices:
        print(f"  [{d['index']}] {d['name']}  ({d['rate']} Hz, {d['channels']}ch)")

    p = pyaudio.PyAudio()
    try:
        device = get_loopback_device(p)
    except RuntimeError as e:
        print(f"\nERRO: {e}")
        p.terminate()
        sys.exit(1)

    native_rate = int(device["defaultSampleRate"])
    channels = device["maxInputChannels"]

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=channels,
        rate=native_rate,
        input=True,
        input_device_index=device["index"],
        frames_per_buffer=CHUNK,
    )

    print(f"\nCapturando: {device['name']}")
    print(f"Rate: {native_rate} Hz -> {SAMPLE_RATE} Hz (mono)")
    print(f"\nReproduza audio no computador (Teams, YouTube, Spotify...)")
    print(f"Monitorando por {DURATION_S} segundos:\n")

    start = time.time()
    peak_volume = 0.0
    total_chunks = 0

    while time.time() - start < DURATION_S:
        raw = stream.read(CHUNK, exception_on_overflow=False)
        audio = np.frombuffer(raw, dtype=np.float32)
        audio = to_mono(audio, channels)
        audio = resample_audio(audio, native_rate)

        volume = float(np.abs(audio).mean())
        peak_volume = max(peak_volume, volume)
        total_chunks += 1

        bar_len = min(int(volume * 400), 40)
        bar = "█" * bar_len + "░" * (40 - bar_len)
        elapsed = time.time() - start
        print(f"\r[{elapsed:5.1f}s] {bar} {volume:.5f}", end="", flush=True)

    stream.stop_stream()
    stream.close()
    p.terminate()

    print(f"\n\n{'=' * 50}")
    print(f"Resultado:")
    print(f"  Chunks capturados: {total_chunks}")
    print(f"  Taxa efetiva:      {total_chunks * (CHUNK / native_rate):.1f}s de audio em {DURATION_S}s")
    print(f"  Volume de pico:    {peak_volume:.5f}")

    if peak_volume > 0.001:
        print(f"\n  CAPTURA OK — audio detectado com sucesso!")
        print(f"  Pronto para o Passo 03 (VAD)")
    else:
        print(f"\n  ATENCAO: volume muito baixo.")
        print(f"  Certifique-se de que ha audio sendo reproduzido")
        print(f"  e que o dispositivo correto esta selecionado.")

    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
