"""Ponto de entrada na raiz do repo.

    .venv\\Scripts\\python.exe -u run_server.py
    .venv\\Scripts\\python.exe -m whisperbridge
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from whisperbridge.__main__ import main

if __name__ == "__main__":
    main()
