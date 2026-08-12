"""
Passo 05 - Pipeline completo: captura -> VAD -> Whisper -> Helsinki -> PT
Rode: .venv/Scripts/python.exe test_translation.py
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
from services.speech_engine.translation.translator import Translator
from services.speech_engine.translation.glossary import apply_glossary

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


results = []
context_en: list[str] = []


def make_on_segment(whisper: WhisperEngine, translator: Translator):
    def on_segment(seg: AudioSegment):
        n = len(results) + 1
        t_total = time.time()

        # Transcrição
        t0 = time.time()
        trans = whisper.transcribe(seg.audio)
        t_whisper = time.time() - t0

        if not trans.text.strip():
            return

        # Tradução
        t0 = time.time()
        translation = translator.translate(trans.text, context=context_en)
        t_helsinki = time.time() - t0

        pt = apply_glossary(translation.translated_text)
        latency = time.time() - t_total

        context_en.append(trans.text)
        if len(context_en) > 5:
            context_en.pop(0)

        results.append({
            "audio_s": seg.duration_s,
            "whisper_s": t_whisper,
            "helsinki_s": t_helsinki,
            "total_s": latency,
            "en": trans.text,
            "pt": pt,
        })

        sep = "-" * 58
        print(f"\n\n  {sep}")
        print(f"  [{n}] audio: {seg.duration_s:.1f}s")
        print(f"  {sep}")
        print(f"  [EN] {trans.text}")
        print(f"  [PT] {pt}")
        print(f"  {sep}")
        print(f"  Whisper: {t_whisper:.2f}s | Helsinki: {t_helsinki:.2f}s | total: {latency:.2f}s")

    return on_segment


def main():
    print("\n" + "=" * 60)
    print("  WhisperBridge - Passo 05: EN -> PT ao vivo")
    print("=" * 60 + "\n")

    print("Carregando modelos...")
    detector  = VoiceDetector()
    whisper   = WhisperEngine(model_size="medium.en", models_dir="./models")
    translator = Translator(models_dir="./models")

    voice_buffer = VoiceBuffer(on_segment=make_on_segment(whisper, translator))

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
    print(f"Whisper     : medium.en (CUDA float16)")
    print(f"Traducao    : Helsinki opus-mt-tc-big-en-pt (CUDA)")
    print(f"\nReproduza audio em ingles. Ctrl+C para encerrar.")
    print(f"Aguardando fala...\n")

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
    print(f"  Resumo final")
    print(f"{'=' * 60}")

    if not results:
        print("  Nenhuma traducao realizada.")
    else:
        print(f"  Segmentos traduzidos : {len(results)}")
        avg_w = sum(r["whisper_s"] for r in results) / len(results)
        avg_h = sum(r["helsinki_s"] for r in results) / len(results)
        avg_t = sum(r["total_s"] for r in results) / len(results)
        print(f"  Whisper medio        : {avg_w:.2f}s")
        print(f"  Helsinki medio       : {avg_h:.2f}s")
        print(f"  Latencia total media : {avg_t:.2f}s apos fim da fala")
        print()
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r['audio_s']:.1f}s | {r['total_s']:.2f}s latencia")
            print(f"       EN: {r['en'][:70]}")
            print(f"       PT: {r['pt'][:70]}")
        print()
        if avg_t < 2.0:
            print("  PIPELINE OK - latencia abaixo de 2s")
            print("  Pronto para o Passo 06 (WebSocket + overlay)")
        else:
            print(f"  Latencia media de {avg_t:.1f}s - ainda utilizavel para reuniao")

    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
