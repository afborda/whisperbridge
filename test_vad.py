"""
Passo 03 - Teste de VAD (Voice Activity Detection)
Mostra em tempo real quando o Silero detecta voz e captura segmentos completos.
Rode: .venv/Scripts/python.exe test_vad.py
"""
import sys
import time
import numpy as np
import pyaudiowpatch as pyaudio
from scipy.signal import resample_poly
from math import gcd

sys.path.insert(0, ".")

from services.speech_engine.vad.detector import VoiceDetector
from services.speech_engine.vad.buffer import VoiceBuffer, AudioSegment

SAMPLE_RATE = 16000
CHUNK = 8000
PREFERRED = ["jbl quantum", "headset", "headphones", "fone"]


def resample(audio, from_rate, to_rate=SAMPLE_RATE):
    if from_rate == to_rate:
        return audio
    d = gcd(from_rate, to_rate)
    return resample_poly(audio, to_rate // d, from_rate // d).astype(np.float32)


def to_mono(audio, channels):
    if channels <= 1:
        return audio
    return audio.reshape(-1, channels).mean(axis=1)


def find_loopback(p):
    loopbacks = [(i, p.get_device_info_by_index(i))
                 for i in range(p.get_device_count())
                 if p.get_device_info_by_index(i).get("isLoopbackDevice")]
    if not loopbacks:
        raise RuntimeError("Nenhum dispositivo loopback encontrado")
    for idx, dev in loopbacks:
        if any(k in dev["name"].lower() for k in PREFERRED):
            return idx, dev
    return loopbacks[0]


segments_captured = []

def on_segment(seg: AudioSegment):
    n = len(segments_captured) + 1
    segments_captured.append(seg)
    samples = len(seg.audio)
    print(f"\n  [SEGMENTO {n}] {seg.duration_s:.2f}s | {samples} amostras | "
          f"{samples/SAMPLE_RATE:.2f}s de audio -> pronto para transcricao")


def main():
    print("\n" + "=" * 55)
    print("  WhisperBridge - Passo 03: VAD (Silero)")
    print("=" * 55)

    print("\nCarregando Silero VAD...", end=" ", flush=True)
    detector = VoiceDetector()
    print(f"OK ({detector.device})")

    voice_buffer = VoiceBuffer(on_segment=on_segment)

    p = pyaudio.PyAudio()
    dev_idx, device = find_loopback(p)
    native_rate = int(device["defaultSampleRate"])
    channels = device["maxInputChannels"]

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=channels,
        rate=native_rate,
        input=True,
        input_device_index=dev_idx,
        frames_per_buffer=CHUNK,
    )

    print(f"Dispositivo: {device['name']}")
    print(f"\nReproduza audio em ingles no Teams ou YouTube.")
    print(f"O VAD vai detectar a fala e demarcar os segmentos.")
    print(f"Ctrl+C para encerrar.\n")
    print(f"  {'ESTADO':<10} {'CONFIANCA':<12} {'INDICADOR'}")
    print(f"  {'-'*10} {'-'*12} {'-'*30}")

    try:
        while True:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.float32)
            audio = to_mono(audio, channels)
            audio = resample(audio, native_rate)

            speech, score = detector.is_speech(audio)
            voice_buffer.push(audio, speech)

            label = "VOZ    " if speech else "silencio"
            bar_len = min(int(score * 30), 30)
            bar = "#" * bar_len + "-" * (30 - bar_len)
            print(f"\r  {label:<10} {score:.4f}       [{bar}]", end="", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    print(f"\n\n{'=' * 55}")
    print(f"  Resultado")
    print(f"{'=' * 55}")
    print(f"  Segmentos capturados: {len(segments_captured)}")
    for i, seg in enumerate(segments_captured, 1):
        print(f"  [{i}] {seg.duration_s:.2f}s  ({len(seg.audio)} amostras)")
    if segments_captured:
        total = sum(s.duration_s for s in segments_captured)
        print(f"\n  Total de fala: {total:.1f}s")
        print(f"  VAD OK - pronto para o Passo 04 (transcricao)")
    else:
        print(f"\n  Nenhum segmento capturado.")
        print(f"  Reproduza audio em ingles e tente novamente.")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
