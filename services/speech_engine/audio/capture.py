import numpy as np
from .backend import pyaudio, is_loopback
from math import gcd
from scipy.signal import resample_poly

SAMPLE_RATE = 16000
CHUNK_FRAMES = 8000


def get_loopback_device(p: pyaudio.PyAudio) -> dict:
    from .backend import host_api

    api = host_api(p)
    out_idx = api.get("defaultOutputDevice")
    out_name = ""
    if out_idx is not None and out_idx >= 0:
        out_name = p.get_device_info_by_index(out_idx)["name"]

    first = None
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if not is_loopback(dev) or dev["maxInputChannels"] < 1:
            continue
        if first is None:
            first = dev
        if out_name and out_name.lower() in (dev.get("name") or "").lower():
            return dev
    if first:
        return first
    raise RuntimeError("Nenhum dispositivo loopback/monitor encontrado")


def list_loopback_devices() -> list[dict]:
    p = pyaudio.PyAudio()
    devices = []
    try:
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if is_loopback(dev):
                devices.append({
                    "index": i,
                    "name": dev["name"],
                    "rate": int(dev["defaultSampleRate"]),
                    "channels": dev["maxInputChannels"],
                })
    finally:
        p.terminate()
    return devices


def resample_audio(audio: np.ndarray, from_rate: int, to_rate: int = SAMPLE_RATE) -> np.ndarray:
    if from_rate == to_rate:
        return audio
    divisor = gcd(from_rate, to_rate)
    return resample_poly(audio, to_rate // divisor, from_rate // divisor).astype(np.float32)


def to_mono(audio: np.ndarray, channels: int) -> np.ndarray:
    if channels <= 1:
        return audio
    return audio.reshape(-1, channels).mean(axis=1)


def capture_loop(callback, device_index: int | None = None):
    p = pyaudio.PyAudio()
    try:
        if device_index is not None:
            device = p.get_device_info_by_index(device_index)
        else:
            device = get_loopback_device(p)

        native_rate = int(device["defaultSampleRate"])
        channels = device["maxInputChannels"]

        stream = p.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=native_rate,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=CHUNK_FRAMES,
        )

        print(f"Capturando: {device['name']}")
        print(f"Rate nativo: {native_rate} Hz -> resample para {SAMPLE_RATE} Hz")
        print(f"Canais: {channels} -> mono")

        try:
            while True:
                raw = stream.read(CHUNK_FRAMES, exception_on_overflow=False)
                audio = np.frombuffer(raw, dtype=np.float32)
                audio = to_mono(audio, channels)
                audio = resample_audio(audio, native_rate)
                callback(audio)
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        p.terminate()
