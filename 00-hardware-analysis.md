# 00 — Análise de Hardware

Levantamento feito na máquina de desenvolvimento em agosto de 2026.

---

## Configuração encontrada

### Processador
- **Modelo:** Intel Core i7-12700 (Alder Lake)
- **Núcleos:** 12 núcleos físicos, 20 threads
- **Clock base:** 2.1 GHz
- **Uso no projeto:** buffer de áudio, VAD em CPU, WebSocket, interface

### Memória RAM
- **Total:** 32 GB
- **Uso no projeto:** carga dos modelos, múltiplos processos simultâneos, sem risco de swap

### GPU Principal — NVIDIA GeForce RTX 4060 Ti
- **VRAM:** 8 GB (8188 MiB)
- **Driver:** 595.97
- **CUDA disponível:** 13.2
- **Uso atual em idle:** 2219 MiB (~2.2 GB com interface gráfica)
- **VRAM livre para IA:** ~5.9 GB
- **Consumo idle:** 8W de 160W máximos
- **Temperatura idle:** 34°C
- **Uso no projeto:** faster-whisper, tradução, VAD acelerado

### GPU Integrada — Intel UHD Graphics 770
- **Origem:** integrada no i7-12700
- **VRAM:** compartilhada dinamicamente com a RAM do sistema
- **APIs:** OpenCL, DirectX 12, Intel Quick Sync
- **CUDA:** não suporta
- **Uso no projeto:** assumir a renderização do Windows e apps, liberando a NVIDIA exclusivamente para IA

### Armazenamento
- **Disco 1:** Kingston SA400S37 — SSD SATA 960 GB
- **Disco 2:** Kingston SNV2S500G — SSD NVMe 466 GB
- **Espaço livre (C:):** 115 GB
- **Uso no projeto:** modelos ficam no NVMe para carregamento mais rápido

### Sistema Operacional
- **SO:** Windows 11 Pro 64-bit
- **Build:** 10.0.26200

---

## Ferramentas já instaladas

| Ferramenta | Versão | Status |
|---|---|---|
| Python | 3.12.10 | instalado |
| pip | 25.0.1 | instalado |
| Node.js | v24.13.1 | instalado |
| npm | 11.8.0 | instalado |
| Git | 2.54.0 | instalado |
| VS Code | 1.129.1 | instalado |
| Docker Desktop | — | instalado |
| Rust / Cargo | — | **faltando** |

---

## Pacotes Python relevantes

| Pacote | Status |
|---|---|
| PyTorch + CUDA | **não instalado** |
| faster-whisper | **não instalado** |
| Silero VAD | **não instalado** |
| Transformers (HuggingFace) | **não instalado** |
| FastAPI | **não instalado** |
| Uvicorn | **não instalado** |
| sounddevice | **não instalado** |
| numpy | **não instalado** |

---

## Uso de VRAM estimado durante reunião

| Componente | VRAM |
|---|---|
| Sistema + interface gráfica | ~2.2 GB |
| Whisper medium.en | ~2.5 GB |
| Helsinki EN→PT | ~300 MB |
| Silero VAD | ~50 MB |
| **Total estimado** | **~5.1 GB** |
| **Margem disponível** | **~2.9 GB** |

O modelo `medium.en` cabe com folga. É possível testar o `large-v3` (~3.1 GB) se quiser qualidade máxima.

---

## Estimativa de latência local

| Etapa | Tempo estimado |
|---|---|
| VAD detectar pausa | ~100 ms |
| Whisper `medium.en` — 5s de áudio | ~600–900 ms |
| Tradução Helsinki | ~100–200 ms |
| WebSocket + render overlay | ~50 ms |
| **Total ponta a ponta** | **~900 ms a 1.5 s** |

---

## Estratégia de alocação de GPU

```
Intel UHD 770
    └── Windows, Teams, browser, Discord, Spotify

RTX 4060 Ti (reservada para IA)
    ├── faster-whisper medium.en   CUDA float16
    ├── Helsinki EN→PT             CUDA
    └── Silero VAD                 CUDA

i7-12700 (CPU)
    ├── Captura WASAPI Loopback
    ├── Reamostrador 16 kHz mono
    ├── WebSocket server
    └── Overlay Tauri + React
```

---

## Veredicto

Hardware **acima do necessário** para o projeto. A RTX 4060 Ti entrega qualidade e velocidade que a maioria das soluções de nuvem cobra por minuto. Com a Intel UHD assumindo o display, a NVIDIA fica exclusiva para IA.

**Próximo passo:** [01-environment-setup.md](./01-environment-setup.md)
