#!/usr/bin/env bash
# Encerra o engine na porta 37865.
PORTA=37865
echo "Procurando WhisperBridge..."
if command -v ss >/dev/null 2>&1; then
  pids=$(ss -ltnp 2>/dev/null | awk -v p=":$PORTA" '$4 ~ p {print}' | grep -oP 'pid=\K[0-9]+' || true)
  for pid in $pids; do
    echo "  matando PID $pid (porta $PORTA)"
    kill "$pid" 2>/dev/null || true
  done
fi
pkill -f 'run_server.py' 2>/dev/null && echo "  matei run_server.py" || true
sleep 0.3
if curl -sf "http://127.0.0.1:${PORTA}/health" >/dev/null 2>&1; then
  echo "AVISO: health ainda responde."
else
  echo "Porta $PORTA livre."
fi
