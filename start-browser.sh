#!/usr/bin/env bash
# Abre o WhisperBridge no navegador. Ctrl+C encerra o engine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VPY="$ROOT/.venv/bin/python"
PORTA=37865
URL="http://127.0.0.1:${PORTA}/"

[[ -x "$VPY" ]] || { echo "  X   .venv nao encontrado. Rode:  ./doctor.sh --fix"; exit 1; }
[[ -f "$ROOT/apps/desktop/dist/index.html" ]] || { echo "  X   Interface nao compilada. Rode:  ./setup.sh"; exit 1; }

if command -v ss >/dev/null 2>&1 && ss -ltn | grep -q ":${PORTA} "; then
  echo "Ja existe um engine na porta $PORTA — abrindo o navegador nele."
  xdg-open "$URL" 2>/dev/null || true
  exit 0
fi

echo "Subindo o engine..."
"$VPY" -u "$ROOT/run_server.py" &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT

ok=0
for i in $(seq 1 60); do
  sleep 0.5
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "  X   O engine morreu ao subir."
    exit 1
  fi
  if curl -sf "$URL/health" >/dev/null 2>&1; then ok=1; break; fi
done
if [[ $ok -eq 0 ]]; then
  echo "  X   O engine nao respondeu em 30s."
  exit 1
fi

echo "Abrindo $URL"
xdg-open "$URL" 2>/dev/null || echo "Abra no navegador: $URL"
echo
echo "Ctrl+C encerra."
wait "$PID"
