"""
Passo 02 — Teste de captura WASAPI
Rode na raiz do projeto: python test_audio.py
"""
import time
import numpy as np
import pyaudiowpatch as pyaudio
from scipy.signal import resample_poly
from math import gcd

SAMPLE_RATE = 16000
CHUNK = 8000
DURATION_S = 15

# Preferencia de dispositivo para o Teams (headset JBL)
PREFERRED_KEYWORDS = ["jbl quantum", "headset", "headphones", "fone"]


def resample(audio, from_rate, to_rate=SAMPLE_RATE):
    if from_rate == to_rate:
        return audio
    d = gcd(from_rate, to_rate)
    return resample_poly(audio, to_rate // d, from_rate // d).astype(np.float32)


def to_mono(audio, channels):
    if channels <= 1:
        return audio
    return audio.reshape(-1, channels).mean(axis=1)


def find_best_loopback(p):
    loopbacks = []
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev.get("isLoopbackDevice"):
            loopbacks.append((i, dev))

    if not loopbacks:
        return None

    # Tenta achar o headset preferido
    for idx, dev in loopbacks:
        name_lower = dev["name"].lower()
        if any(kw in name_lower for kw in PREFERRED_KEYWORDS):
            return idx, dev

    # Senao pega o padrao do sistema
    try:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        for idx, dev in loopbacks:
            if dev["name"] == default_out["name"]:
                return idx, dev
    except Exception:
        pass

    # Ultimo recurso: primeiro da lista
    return loopbacks[0]


def main():
    print("\n" + "=" * 55)
    print("  WhisperBridge — Passo 02: Captura WASAPI")
    print("=" * 55 + "\n")

    p = pyaudio.PyAudio()

    result = find_best_loopback(p)
    if result is None:
        print("ERRO: nenhum dispositivo loopback encontrado.")
        p.terminate()
        return

    dev_idx, device = result
    native_rate = int(device["defaultSampleRate"])
    channels = device["maxInputChannels"]

    print(f"Dispositivo selecionado: [{dev_idx}] {device['name']}")
    print(f"Rate nativo: {native_rate} Hz  |  Canais: {channels}")
    print(f"Saida para Whisper: {SAMPLE_RATE} Hz mono")
    print(f"\nReproduza audio agora (Teams, YouTube, musica...)")
    print(f"Monitorando {DURATION_S} segundos:\n")

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=channels,
        rate=native_rate,
        input=True,
        input_device_index=dev_idx,
        frames_per_buffer=CHUNK,
    )

    start = time.time()
    peak = 0.0
    chunks = 0
    has_signal = False

    while time.time() - start < DURATION_S:
        raw = stream.read(CHUNK, exception_on_overflow=False)
        audio = np.frombuffer(raw, dtype=np.float32)
        audio = to_mono(audio, channels)
        audio = resample(audio, native_rate)

        vol = float(np.abs(audio).mean())
        peak = max(peak, vol)
        chunks += 1

        if vol > 0.001:
            has_signal = True

        filled = min(int(vol * 500), 38)
        bar = "#" * filled + "-" * (38 - filled)
        elapsed = time.time() - start
        print(f"\r  [{elapsed:5.1f}s] [{bar}] {vol:.5f}", end="", flush=True)

    stream.stop_stream()
    stream.close()
    p.terminate()

    print(f"\n\n{'=' * 55}")
    print(f"  Resultado")
    print(f"{'=' * 55}")
    print(f"  Chunks capturados : {chunks}")
    print(f"  Audio processado  : {chunks * (CHUNK / native_rate):.1f}s")
    print(f"  Volume de pico    : {peak:.5f}")

    if has_signal:
        print(f"\n  CAPTURA OK — sinal de audio detectado!")
        print(f"  Dispositivo correto: {device['name']}")
        print(f"\n  Proximo passo: python test_vad.py")
    else:
        print(f"\n  ATENCAO: nenhum sinal detectado.")
        print(f"  Certifique-se de que ha audio sendo reproduzido")
        print(f"  no dispositivo: {device['name']}")

    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
