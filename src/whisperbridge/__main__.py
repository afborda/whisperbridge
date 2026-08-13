"""Ponto de entrada:  python -m whisperbridge"""
from __future__ import annotations

import atexit
import os
import sys
import warnings

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
warnings.filterwarnings("ignore")

try:
    import logging

    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("pyannote").setLevel(logging.ERROR)
    logging.getLogger("torchcodec").setLevel(logging.ERROR)
    logging.getLogger("speechbrain").setLevel(logging.ERROR)
except Exception:
    pass


def main() -> None:
    import uvicorn

    from whisperbridge.config.ports import ENGINE_HOST, ENGINE_PORT
    from whisperbridge.server import _shutdown_engine, app

    def _atexit_unload() -> None:
        try:
            _shutdown_engine(exit_process=False)
        except Exception:
            pass

    atexit.register(_atexit_unload)
    print(f"WhisperBridge engine em http://{ENGINE_HOST}:{ENGINE_PORT}", flush=True)
    try:
        uvicorn.run(
            app,
            host=ENGINE_HOST,
            port=ENGINE_PORT,
            log_level="error",
            access_log=False,
        )
    finally:
        _atexit_unload()
        # ThreadPoolExecutor não é daemon — sem isto o processo fica zumbi com a VRAM
        os._exit(0)


if __name__ == "__main__":
    main()
