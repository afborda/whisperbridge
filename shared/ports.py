"""
Portas locais do WhisperBridge — escolhidas altas e pouco usadas
para reduzir conflito com apps comuns (3000, 5000, 8000, 8080, 8765, etc.).

  Engine (Whisper + tradução + WebSocket):  127.0.0.1:37865
  Vite dev (só desenvolvimento UI):         127.0.0.1:14287
"""

ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 37865

# Apenas npm run tauri dev / vite
VITE_DEV_PORT = 14287
