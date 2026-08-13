#!/usr/bin/env bash
# WhisperBridge doctor + instalador Linux.
#   ./scripts/linux/doctor.sh           so verifica
#   ./scripts/linux/doctor.sh --fix     instala o que falta
#   ./scripts/linux/doctor.sh --menu    menu (install.sh na raiz)
set -u

FIX=0; MENU=0; CPU=0; OVERLAY=0; SPEAKERS=0
for a in "$@"; do
  case "$a" in
    --fix) FIX=1 ;;
    --menu) MENU=1 ;;
    --cpu) CPU=1 ;;
    --overlay) OVERLAY=1 ;;
    --speakers) SPEAKERS=1 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VPY="$ROOT/.venv/bin/python"
DIST="$ROOT/apps/desktop/dist/index.html"
ENVF="$ROOT/.env"

ok()    { printf '  \033[32mOK   %s\033[0m\n' "$*"; }
falha() { printf '  \033[31mX    %s\033[0m\n' "$*"; }
aviso() { printf '  \033[33m!    %s\033[0m\n' "$*"; }
info()  { printf '       %s\n' "$*"; }
titulo(){ printf '\n\033[36m=== %s ===\033[0m\n' "$*"; }

if [[ $MENU -eq 1 ]]; then
  echo
  echo "  WhisperBridge - o que voce quer fazer?"
  echo
  echo "    1  So verificar este PC (doctor)"
  echo "    2  Instalar o que falta          (recomendado)"
  echo "    3  Instalar + janela flutuante   (precisa de Rust)"
  echo "    4  Abrir o WhisperBridge agora"
  echo "    5  Sair"
  echo
  read -r -p "  Escolha [2] " esc
  esc="${esc:-2}"
  case "$esc" in
    1) ;;
    2) FIX=1 ;;
    3) FIX=1; OVERLAY=1 ;;
    4) exec "$HERE/start-browser.sh" ;;
    *) exit 0 ;;
  esac
fi

titulo "WhisperBridge doctor (Linux)"
info "pasta: $ROOT"

FALTAS=()
AVISOS=()

titulo "1. Computador"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  ok "${PRETTY_NAME:-Linux}"
else
  aviso "Nao li /etc/os-release"
fi
RAM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
RAM_GB=$(awk -v k="$RAM_KB" 'BEGIN{printf "%.1f", k/1024/1024}')
ok "RAM ${RAM_GB} GB"
if awk -v r="$RAM_GB" 'BEGIN{exit !(r>0 && r<8)}'; then
  AVISOS+=("RAM abaixo de 8 GB: o modo rapido na placa pode ficar apertado.")
fi

GPU=""
VRAM=0
if command -v nvidia-smi >/dev/null 2>&1; then
  LINE=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 || true)
  if [[ -n "$LINE" ]]; then
    GPU=$(echo "$LINE" | cut -d, -f1 | xargs)
    MB=$(echo "$LINE" | cut -d, -f2 | xargs)
    VRAM=$(awk -v m="$MB" 'BEGIN{printf "%.1f", m/1024}')
    ok "GPU NVIDIA: $GPU  ·  ${VRAM} GB VRAM"
  fi
fi
[[ -n "$GPU" ]] || aviso "Nenhuma GPU NVIDIA visivel. Modos rapidos na placa indisponiveis."

titulo "2. Programas"
PY=""
VER=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    VER="$("$c" -c 'import sys; print("%d.%d"%sys.version_info[:2])' 2>/dev/null || true)"
    PY="$(command -v "$c")"
    break
  fi
done
if [[ -n "$VER" ]]; then
  MAJ="${VER%%.*}"; MIN="${VER#*.}"
  if (( MAJ==3 && MIN>=10 && MIN<13 )); then ok "Python $VER"
  else falha "Python $VER nao serve (precisa 3.10-3.12)"; FALTAS+=("python-versao"); fi
else
  falha "Python nao encontrado"
  FALTAS+=("python")
fi

if command -v node >/dev/null 2>&1; then ok "Node.js $(node -v)"
else falha "Node.js / npm nao encontrado"; FALTAS+=("node"); fi

if command -v cargo >/dev/null 2>&1; then ok "Rust (cargo)"
else info "Rust nao instalado - use o navegador"; fi

if command -v pactl >/dev/null 2>&1 || command -v pw-cli >/dev/null 2>&1; then
  ok "PulseAudio/PipeWire (da para ouvir o som do PC via monitor)"
else
  aviso "Sem pactl/pw-cli. Som do PC (loopback) pode nao aparecer; o microfone ainda funciona."
fi

titulo "3. Este projeto"
if [[ -x "$VPY" ]]; then ok ".venv pronto"
else aviso ".venv ainda nao existe"; FALTAS+=("venv"); fi

TORCH_CUDA=0
if [[ -x "$VPY" ]]; then
  TV="$("$VPY" -c 'import torch; print(torch.__version__); print(torch.cuda.is_available())' 2>/dev/null || true)"
  if [[ -n "$TV" ]]; then
    VER_T=$(echo "$TV" | sed -n '1p')
    CUDA=$(echo "$TV" | sed -n '2p')
    if [[ "$CUDA" == "True" ]]; then TORCH_CUDA=1; ok "PyTorch $VER_T com CUDA"
    else ok "PyTorch $VER_T (CPU)"
      [[ -n "$GPU" ]] && AVISOS+=("Tem NVIDIA mas o torch e CPU. Rode: ./install.sh")
    fi
  else
    aviso "PyTorch ainda nao instalado"
    FALTAS+=("torch")
  fi
fi

if [[ -f "$DIST" ]]; then ok "Interface compilada"
else aviso "Interface ainda nao compilada"; FALTAS+=("ui"); fi

if [[ -f "$ENVF" ]]; then ok ".env existe"; else aviso ".env ainda nao existe"; fi

TEM_CHAVE=0
if [[ -f "$ENVF" ]]; then
  grep -qE '^\s*GEMINI_API_KEY\s*=\s*\S+' "$ENVF" && TEM_CHAVE=1
  grep -qE '^\s*LLM_API_KEY\s*=\s*\S+' "$ENVF" && TEM_CHAVE=1
fi
if [[ -f "$ROOT/user-settings.json" ]]; then
  grep -q '"gemini_key": "[^"]' "$ROOT/user-settings.json" 2>/dev/null && TEM_CHAVE=1
  grep -q '"llm_key": "[^"]' "$ROOT/user-settings.json" 2>/dev/null && TEM_CHAVE=1
fi
if [[ $TEM_CHAVE -eq 1 ]]; then ok "Chave de IA encontrada"
else info "Sem chave de IA - modos de nuvem pedem uma nas Configuracoes"; fi

titulo "4. O que ESTE PC consegue usar"
pode_gpu=$TORCH_CUDA
[[ $TORCH_CUDA -eq 0 && -n "$GPU" && ! -x "$VPY" ]] && pode_gpu=1

linha() {
  local nome="$1" sim="$2" txt="$3"
  if [[ $sim -eq 1 ]]; then printf '  \033[32mSIM   %s\033[0m\n' "$nome"
  else printf '  \033[90mNAO   %s\033[0m\n' "$nome"; fi
  info "$txt"
}

if [[ $pode_gpu -eq 1 ]]; then
  linha "Neste PC (rapido)" 1 "Ouve e traduz neste computador. Ingles -> portugues."
else
  linha "Neste PC (rapido)" 0 "Precisa de GPU NVIDIA + PyTorch CUDA."
fi
if [[ $pode_gpu -eq 1 && $TEM_CHAVE -eq 1 ]]; then
  linha "Recomendado (IA)" 1 "Melhor traducao. Voce escolhe os idiomas."
elif [[ $pode_gpu -eq 1 ]]; then
  linha "Recomendado (IA)" 0 "Placa ok. Falta colar a chave da IA (aistudio.google.com/apikey)."
else
  linha "Recomendado (IA)" 0 "Precisa da placa e de uma chave de IA."
fi
if [[ $TEM_CHAVE -eq 1 ]]; then
  linha "IA sem placa de video" 1 "Libera a placa. Ouvir fica mais lento."
else
  linha "IA sem placa de video" 0 "Funciona sem NVIDIA, mas precisa da chave da IA."
fi
linha "Neste PC (sem internet)" 1 "Sempre da. Tudo no processador. Mais lento."

if [[ $FIX -eq 1 ]]; then
  titulo "5. Instalando o que falta"
  if [[ " ${FALTAS[*]} " == *" python "* || " ${FALTAS[*]} " == *" python-versao "* ]]; then
    if command -v apt-get >/dev/null 2>&1; then
      info "sudo apt install python3.12 python3.12-venv python3.12-dev portaudio19-dev"
      sudo apt-get update
      sudo apt-get install -y python3.12 python3.12-venv python3.12-dev portaudio19-dev || true
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y python3.12 python3.12-devel portaudio-devel || true
    else
      falha "Instale Python 3.10-3.12 e portaudio-dev pelo gerenciador da sua distro."
    fi
  fi
  if [[ " ${FALTAS[*]} " == *" node "* ]]; then
    aviso "Instale Node LTS: https://nodejs.org/  ou  nvm install --lts"
  fi
  ARGS=()
  [[ $CPU -eq 1 ]] && ARGS+=(--cpu)
  [[ $OVERLAY -eq 1 ]] && ARGS+=(--overlay)
  [[ $SPEAKERS -eq 1 ]] && ARGS+=(--speakers)
  info "chamando setup.sh ${ARGS[*]} ..."
  bash "$HERE/setup.sh" "${ARGS[@]}"
fi

if ((${#AVISOS[@]})); then
  titulo "Avisos"
  for a in "${AVISOS[@]}"; do aviso "$a"; done
fi

titulo "Como iniciar"
if [[ ! -x "$VPY" || ! -f "$DIST" ]] && [[ $FIX -eq 0 ]]; then
  echo "  Ainda falta instalar. Rode:"
  echo "      ./install.sh"
  echo "  ou  ./scripts/linux/doctor.sh --fix"
else
  echo "  1.  ./scripts/linux/start-browser.sh     (navegador)"
  echo "  2.  Na tela: Som do PC ou Microfone  ->  Iniciar"
  echo "  3.  Modo Recomendado (IA): Configuracoes, chave, idiomas"
  echo
  echo "  No Linux, Som do PC usa o monitor do Pulse/PipeWire (Monitor of ...)."
fi
echo
if [[ $FIX -eq 0 && ${#FALTAS[@]} -gt 0 ]]; then
  echo "  Proximo passo:  ./install.sh"
  echo
fi
exit 0
