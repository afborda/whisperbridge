# 01 — Configuração do Ambiente

Instala todas as dependências necessárias para rodar o WhisperBridge localmente.

---

## 1.1 Rust e Cargo (necessário para Tauri)

```powershell
# Baixar e executar o instalador do Rust
Invoke-WebRequest -Uri https://win.rustup.rs -OutFile rustup-init.exe
.\rustup-init.exe
```

Escolha a opção padrão (1) quando perguntado. Depois feche e abra o terminal novamente.

```powershell
# Verificar instalação
rustc --version
cargo --version
```

---

## 1.2 CUDA Toolkit

O driver CUDA 13.2 já está presente via driver NVIDIA. Para o faster-whisper funcionar com GPU, instale o CUDA Toolkit 12.x compatível.

```powershell
# Verificar se o toolkit já está disponível
nvcc --version
```

Se não encontrar, baixe o CUDA Toolkit 12.4 em:
`https://developer.nvidia.com/cuda-downloads`

Selecione:
- OS: Windows
- Architecture: x86_64
- Version: 11 ou 10
- Installer Type: exe (network)

---

## 1.3 Python — ambiente virtual

Sempre use um ambiente virtual para não misturar com o Python do sistema.

```powershell
# Criar ambiente virtual dentro da pasta do projeto
cd C:\Users\abner\Documents\whisperbridge
python -m venv .venv

# Ativar
.\.venv\Scripts\Activate.ps1
```

Confirmar que está no ambiente certo:

```powershell
python --version
where python
# deve mostrar o caminho dentro de .venv
```

---

## 1.4 PyTorch com CUDA

Instale a versão do PyTorch compatível com CUDA 12.x:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Verificar se a GPU foi reconhecida:

```python
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
# esperado: True / NVIDIA GeForce RTX 4060 Ti
```

---

## 1.5 Pacotes do motor de IA

```powershell
pip install faster-whisper
pip install transformers sentencepiece sacremoses
pip install silero-vad
```

---

## 1.6 Servidor e comunicação

```powershell
pip install fastapi uvicorn websockets
pip install numpy scipy sounddevice
```

---

## 1.7 Captura de áudio no Windows

```powershell
pip install sounddevice
pip install pyaudiowpatch
```

O `pyaudiowpatch` é um fork do PyAudio com suporte a WASAPI Loopback, necessário para capturar o áudio que está sendo reproduzido pelo sistema.

---

## 1.8 Utilitários

```powershell
pip install python-dotenv pydantic loguru
```

---

## 1.9 Node.js e dependências do frontend

```powershell
# Verificar versão (já instalado)
node --version   # v24.13.1
npm --version    # 11.8.0

# Instalar Tauri CLI globalmente
npm install -g @tauri-apps/cli
```

---

## 1.10 Verificação completa

```powershell
python -c "
import torch, faster_whisper, sounddevice, fastapi, numpy
print('PyTorch:', torch.__version__)
print('CUDA:', torch.cuda.is_available())
print('GPU:', torch.cuda.get_device_name(0))
print('faster-whisper: OK')
print('sounddevice:', sounddevice.__version__)
print('FastAPI: OK')
print('numpy:', numpy.__version__)
"
```

Resultado esperado:

```
PyTorch: 2.x.x+cu121
CUDA: True
GPU: NVIDIA GeForce RTX 4060 Ti
faster-whisper: OK
sounddevice: 0.x.x
FastAPI: OK
numpy: 1.x.x
```

---

## Estrutura de pastas do projeto

```
whisperbridge/
├── .venv/                    ← ambiente Python (não versionar)
├── services/
│   └── speech-engine/
│       ├── audio/
│       ├── vad/
│       ├── transcription/
│       ├── translation/
│       ├── pipeline/
│       └── websocket/
├── apps/
│   └── desktop/
│       ├── src/
│       └── src-tauri/
├── models/                   ← modelos baixados ficam aqui
└── docs/
```

Criar a estrutura:

```powershell
mkdir services\speech-engine\audio
mkdir services\speech-engine\vad
mkdir services\speech-engine\transcription
mkdir services\speech-engine\translation
mkdir services\speech-engine\pipeline
mkdir services\speech-engine\websocket
mkdir models
mkdir apps\desktop
```

---

**Próximo passo:** [02-audio-capture.md](./02-audio-capture.md)
