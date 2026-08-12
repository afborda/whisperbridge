# WhisperBridge

Tradutor local de reuniões em tempo real. Captura o áudio do sistema, transcreve com IA e exibe legendas em português sobre qualquer janela.

Funciona 100% offline após a configuração. Custo por minuto: zero.

---

## Navegação

| Passo | Arquivo | Descrição |
|---|---|---|
| 0 | [hardware-analysis.md](./00-hardware-analysis.md) | Análise da máquina e viabilidade |
| 1 | [environment-setup.md](./01-environment-setup.md) | Python, Node, Rust, CUDA |
| 2 | [audio-capture.md](./02-audio-capture.md) | Captura WASAPI Loopback no Windows |
| 3 | [vad-pipeline.md](./03-vad-pipeline.md) | Detecção de voz com Silero VAD |
| 4 | [transcription-engine.md](./04-transcription-engine.md) | Transcrição com faster-whisper |
| 5 | [translation-engine.md](./05-translation-engine.md) | Tradução local inglês → português |
| 6 | [realtime-pipeline.md](./06-realtime-pipeline.md) | Pipeline completo em tempo real |
| 7 | [websocket-server.md](./07-websocket-server.md) | Servidor FastAPI + WebSocket local |
| 8 | [frontend-overlay.md](./08-frontend-overlay.md) | Interface flutuante Tauri + React |
| 9 | [gpu-optimization.md](./09-gpu-optimization.md) | CUDA, Intel UHD e otimização de VRAM |
| 10 | [packaging.md](./10-packaging.md) | Build e instalador Windows |
| 11 | [roadmap.md](./11-roadmap.md) | Fases futuras, macOS e SaaS |

---

## Fases do projeto

```
Fase 1 — Prova técnica        → passos 0 a 4   (terminal apenas)
Fase 2 — Tradução funcionando → passos 5 e 6   (terminal com tradução)
Fase 3 — Interface legenda    → passos 7 e 8   (overlay na tela)
Fase 4 — App utilizável       → passos 9 e 10  (instalável, atalhos)
Fase 5 — Roadmap              → passo 11       (macOS, SaaS)
```

---

## Stack

```
Interface      Tauri 2 + React + TypeScript
Motor de IA    Python 3.12 + FastAPI + WebSocket
Captura        WASAPI Loopback (Windows nativo)
VAD            Silero VAD
Transcrição    faster-whisper (CUDA float16)
Tradução       Helsinki-NLP opus-mt-tc-big-en-pt
GPU principal  RTX 4060 Ti — 8 GB VRAM
GPU display    Intel UHD 770 (libera a NVIDIA para IA)
```

---

## Requisitos mínimos recomendados

- Windows 10/11 64-bit
- GPU NVIDIA com 4 GB VRAM e CUDA 11+
- 8 GB RAM
- 5 GB de espaço em disco (modelos)
- Python 3.10+
- Node.js 18+
