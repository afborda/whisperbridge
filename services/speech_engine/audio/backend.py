"""Backend de audio: WASAPI no Windows, PortAudio (Pulse/PipeWire) no Linux."""
from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import pyaudiowpatch as pyaudio  # type: ignore
else:
    import pyaudio  # type: ignore


def is_loopback(dev: dict) -> bool:
    if dev.get("isLoopbackDevice"):
        return True
    name = (dev.get("name") or "").lower()
    return any(
        k in name
        for k in ("monitor of", ".monitor", "loopback", "stereo mix", "what u hear")
    )


def host_api(p) -> dict:
    if IS_WINDOWS:
        try:
            return p.get_host_api_info_by_type(pyaudio.paWASAPI)
        except Exception:
            pass
    return p.get_host_api_info_by_index(p.get_default_host_api())


def display_name(dev: dict) -> str:
    return (
        (dev.get("name") or "")
        .replace(" [Loopback]", "")
        .replace("Monitor of ", "Som do PC · ")
    )
