"""
Inicia o servidor WhisperBridge.
Rode: .venv/Scripts/python.exe run_server.py
"""
import sys
import os
import atexit
import warnings

# Silencia warnings ruidosos e inúteis no uso diário
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(__file__))

# Reduz log do transformers / huggingface
try:
    import logging
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("pyannote").setLevel(logging.ERROR)
    logging.getLogger("torchcodec").setLevel(logging.ERROR)
    logging.getLogger("speechbrain").setLevel(logging.ERROR)
except Exception:
    pass

import uvicorn
from shared.ports import ENGINE_HOST, ENGINE_PORT
from services.speech_engine.websocket.server import app

if __name__ == "__main__":
    from services.speech_engine.websocket.server import _shutdown_engine

    def _atexit_unload():
        try:
            _shutdown_engine(exit_process=False)
        except Exception:
            pass

    atexit.register(_atexit_unload)
    print(f"WhisperBridge engine em http://{ENGINE_HOST}:{ENGINE_PORT}", flush=True)
    try:
        uvicorn.run(app, host=ENGINE_HOST, port=ENGINE_PORT, log_level="error", access_log=False)
    finally:
        _atexit_unload()
        # ThreadPoolExecutor não é daemon — sem isto o processo fica zumbi com a VRAM
        os._exit(0)
