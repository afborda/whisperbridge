"""
Passo 04 - Transcricao ao vivo com faster-whisper
Captura -> VAD -> Whisper -> texto em ingles no terminal
Rode: .venv/Scripts/python.exe test_transcription.py
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
from services.speech_engine.transcription.whisper_engine import WhisperEngine

SAMPLE_RATE = 16000
CHUNK = 8000
MODEL = "medium.en"
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


# --- estado global de metricas ---
results = []


def make_on_segment(engine: WhisperEngine):
    def on_segment(seg: AudioSegment):
        n = len(results) + 1
        print(f"\n  [{n}] transcrevendo {seg.duration_s:.1f}s de audio...", end=" ", flush=True)

        result = engine.transcribe(seg.audio)

        results.append({
            "duration": seg.duration_s,
            "processing": result.processing_time_s,
            "factor": result.realtime_factor,
            "text": result.text,
        })

        if result.text.strip():
            print(f"\n\n  [EN] {result.text}")
            print(f"       {result.processing_time_s:.2f}s processamento | "
                  f"fator {result.realtime_factor:.1f}x tempo real\n")
        else:
            print("(sem texto detectado)")

    return on_segment


def main():
    print("\n" + "=" * 60)
    print("  WhisperBridge - Passo 04: Transcricao ao vivo")
    print("=" * 60 + "\n")

    print(f"Carregando modelos (primeira vez baixa ~1.5 GB)...")
    detector = VoiceDetector()

    engine = WhisperEngine(model_size=MODEL, models_dir="./models")
    voice_buffer = VoiceBuffer(on_segment=make_on_segment(engine))

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

    print(f"\nDispositivo : {device['name']}")
    print(f"Modelo      : {MODEL} (CUDA float16)")
    print(f"\nReproduza audio em ingles. Ctrl+C para encerrar.")
    print(f"Aguardando fala...\n")
    print(f"  {'ESTADO':<10} {'CONFIANCA'}")
    print(f"  {'-'*10} {'-'*10}")

    try:
        while True:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.float32)
            audio = to_mono(audio, channels)
            audio = resample(audio, native_rate)

            speech, score = detector.is_speech(audio)
            voice_buffer.push(audio, speech)

            label = "VOZ    " if speech else "silencio"
            print(f"\r  {label:<10} {score:.4f}", end="", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    print(f"\n\n{'=' * 60}")
    print(f"  Resumo de desempenho")
    print(f"{'=' * 60}")

    if not results:
        print("  Nenhum segmento transcrito.")
    else:
        print(f"  Segmentos    : {len(results)}")
        avg_factor = sum(r["factor"] for r in results) / len(results)
        avg_proc   = sum(r["processing"] for r in results) / len(results)
        min_factor = min(r["factor"] for r in results)
        print(f"  Fator medio  : {avg_factor:.1f}x tempo real")
        print(f"  Fator minimo : {min_factor:.1f}x (pior caso)")
        print(f"  Tempo medio  : {avg_proc:.2f}s por segmento")
        print()
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r['duration']:.1f}s audio -> {r['processing']:.2f}s proc "
                  f"({r['factor']:.1f}x) | {r['text'][:60]}")
        print()
        if min_factor >= 3.0:
            print("  LATENCIA OK - pipeline confortavelmente em tempo real")
            print("  Pronto para o Passo 05 (traducao EN->PT)")
        else:
            print("  ATENCAO: fator abaixo de 3x, pode haver latencia visivelmente alta")

    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
