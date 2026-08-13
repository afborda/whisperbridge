#!/usr/bin/env bash
# WhisperBridge — instalador Linux.
#   ./setup.sh              detecta a maquina
#   ./setup.sh --cpu        ignora a GPU
#   ./setup.sh --overlay    tenta compilar a janela Tauri (precisa Rust)
#   ./setup.sh --speakers   + pyannote
set -euo pipefail

CPU=0; OVERLAY=0; SPEAKERS=0
for a in "$@"; do
  case "$a" in
    --cpu) CPU=1 ;;
    --overlay) OVERLAY=1 ;;
    --speakers) SPEAKERS=1 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VENV="$ROOT/.venv"
VPY="$VENV/bin/python"
DESKTOP="$ROOT/apps/desktop"
AVISOS=()

ok()    { printf '  \033[32mOK  %s\033[0m\n' "$*"; }
info()  { printf '      %s\n' "$*"; }
aviso() { printf '  \033[33m!   %s\033[0m\n' "$*"; AVISOS+=("$*"); }
morre() { printf '\n  \033[31mX   %s\n\033[0m\n' "$*"; exit 1; }
passo() { printf '\n\033[36m[%s]\033[0m\n' "$*"; }

echo
echo "=== WhisperBridge — instalacao Linux ==="

# 1. Python
passo "1/6  Python"
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
done
[[ -n "$PY" ]] || morre "Python 3.10-3.12 nao encontrado. Ubuntu: sudo apt install python3.12 python3.12-venv python3.12-dev"
VER="$("$PY" -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
MAJ="${VER%%.*}"; MIN="${VER#*.}"
if (( MAJ != 3 || MIN < 10 || MIN >= 13 )); then
  morre "Python $VER nao serve. Precisa 3.10, 3.11 ou 3.12."
fi
ok "Python $VER ($PY)"

# 2. venv
passo "2/6  Ambiente virtual"
if [[ -x "$VPY" ]]; then
  ok ".venv ja existe"
else
  "$PY" -m venv "$VENV" || morre "Falhou ao criar o .venv (instale python3-venv)."
  ok ".venv criado"
fi
"$VPY" -m pip install --upgrade pip --quiet --disable-pip-version-check || aviso "Nao atualizei o pip; seguindo."

# 3. PyTorch
passo "3/6  PyTorch"
TEM_GPU=0
if [[ $CPU -eq 0 ]] && command -v nvidia-smi >/dev/null 2>&1; then
  if nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
    TEM_GPU=1
    info "placa: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  fi
fi
JA="$("$VPY" -c 'try:
 import torch
 print(torch.__version__)
except Exception:
 print("")' || true)"
if [[ -n "${JA// /}" ]]; then
  ok "torch $JA ja instalado"
else
  if [[ $TEM_GPU -eq 1 ]]; then
    info "instalando torch CUDA 12.1 (~2.5 GB)..."
    "$VPY" -m pip install "torch==2.5.1+cu121" "torchaudio==2.5.1+cu121" \
      --index-url https://download.pytorch.org/whl/cu121 --disable-pip-version-check
  else
    info "instalando torch CPU..."
    "$VPY" -m pip install "torch==2.5.1" "torchaudio==2.5.1" \
      --index-url https://download.pytorch.org/whl/cpu --disable-pip-version-check
    aviso "Sem CUDA: os modos rapidos na placa ficam indisponiveis."
  fi
  ok "torch instalado"
fi

# 4. deps
passo "4/6  Dependencias Python"
if ! "$VPY" -c "import pyaudio" >/dev/null 2>&1; then
  info "PyAudio precisa de portaudio. Se falhar: sudo apt install portaudio19-dev python3-dev"
fi
PINS="$(mktemp)"
"$VPY" -c "
import importlib
linhas=[]
for n in ('torch','torchaudio','torchvision'):
    try: linhas.append('%s==%s'%(n, importlib.import_module(n).__version__))
    except Exception: pass
open(r'$PINS','w').write('\\n'.join(linhas)+'\\n')
"
info "travando: $(tr '\n' ' ' < "$PINS")"
"$VPY" -m pip install -r "$ROOT/requirements/linux.txt" --constraint "$PINS" --disable-pip-version-check \
  || morre "pip install requirements/linux.txt falhou. Falta portaudio19-dev?"
if [[ $SPEAKERS -eq 1 ]]; then
  info "instalando pyannote (falantes)..."
  "$VPY" -m pip install "pyannote.audio==4.0.7" --no-deps --constraint "$PINS" --disable-pip-version-check \
    || aviso "pyannote falhou; o app roda sem separar falantes."
fi
CUDA="$("$VPY" -c 'import torch; print(torch.cuda.is_available())')"
ok "dependencias  (cuda=$CUDA)"
rm -f "$PINS"

# 5. .env
passo "5/6  Configuracao"
if [[ -f "$ROOT/.env" ]]; then
  ok ".env ja existe"
else
  cp "$ROOT/.env.example" "$ROOT/.env"
  ok ".env criado a partir do .env.example"
  info "Funciona vazio. GEMINI_API_KEY so se quiser traducao por IA."
fi

# 6. UI
passo "6/6  Interface"
if ! command -v npm >/dev/null 2>&1; then
  aviso "npm nao encontrado. Instale Node LTS e rode de novo. Sem UI o / fica vazio."
else
  pushd "$DESKTOP" >/dev/null
  if [[ ! -d node_modules ]]; then
    info "npm install..."
    npm install --silent
  fi
  info "npm run build..."
  npm run build
  ok "interface em apps/desktop/dist"
  if [[ $OVERLAY -eq 1 ]]; then
    if ! command -v cargo >/dev/null 2>&1; then
      aviso "--overlay pedido sem Rust (rustup.rs). Use o navegador."
    else
      info "compilando overlay Tauri..."
      npm run tauri build || aviso "overlay falhou; o navegador continua ok."
    fi
  fi
  popd >/dev/null
fi

echo
echo "=== Pronto. Para usar ==="
echo "  ./scripts/linux/start-browser.sh"
echo "  Toque audio em ingles e clique em Iniciar."
echo
if ((${#AVISOS[@]})); then
  echo "=== Avisos ==="
  for a in "${AVISOS[@]}"; do echo "  - $a"; done
  echo
fi
