<p align="center">
  <img src="assets/brand/whisperbridge-icon.png" width="96" alt="WhisperBridge">
</p>

<h1 align="center">WhisperBridge</h1>

<p align="center">
  <b>PT</b> Legendas ao vivo para reuniões em inglês · no seu Windows · áudio nunca sai do PC<br>
  <b>EN</b> Live meeting subtitles on Windows · audio stays on your machine
</p>

<p align="center">
  <a href="#português">Português</a> ·
  <a href="#english">English</a>
</p>

<p align="center">
  <img src="assets/docs/hero.jpg" width="720" alt="WhisperBridge">
</p>

---

# Português

Traduz o que está tocando no computador (Teams, Meet, Zoom, YouTube) ou o que entra no microfone e mostra a legenda numa janela por cima de tudo.

- **Ouvir é sempre local** (Whisper). O áudio da reunião não vai para a nuvem.
- **Traduzir** pode ser neste PC ou com a **sua** chave (Gemini, GPT, DeepSeek…).
- Sem Rust: funciona no **navegador**. Com Rust: janela flutuante.

<p align="center">
  <img src="assets/docs/fluxo-pt.svg" width="900" alt="Fluxo: captura → Whisper → tradução → legenda">
</p>

## O que você precisa

| | |
|---|---|
| Sistema | Windows 10/11 ou Linux (Pulse/PipeWire) |
| Python | **3.10, 3.11 ou 3.12** (3.13 não serve) |
| Node.js | LTS |
| GPU | NVIDIA ajuda bastante; sem placa também roda (mais lento) |
| Opcional | Rust — só se quiser a janela flutuante |

## Instalar (o mais fácil)

**Windows** — depois do `git clone`, duplo clique em `Instalar.bat`

**Linux** — no terminal:

```bash
chmod +x install.sh scripts/linux/*.sh
./install.sh          # menu
# ou
./scripts/linux/doctor.sh           # só verifica
./scripts/linux/doctor.sh --fix     # instala o que falta
```

Ubuntu/Debian, se o PyAudio falhar:

```bash
sudo apt install python3.12 python3.12-venv python3.12-dev portaudio19-dev
```

No Linux, **Som do PC** usa o *monitor* do PulseAudio/PipeWire (`Monitor of …`). O microfone funciona igual.

Ele pergunta o que fazer:

1. **Só verificar este PC** — doctor: RAM, GPU, Python, Node, o que falta, **quais modos você consegue usar**
2. **Instalar o que falta** (recomendado) — tenta Python/Node pelo `winget` e roda o setup
3. **Instalar + janela flutuante** — precisa de Rust
4. **Abrir o WhisperBridge agora**

Pelo terminal:

```powershell
git clone https://github.com/afborda/whisperbridge.git
cd whisperbridge
.\Instalar.bat                              # menu (duplo clique também)
.\scripts\windows\doctor.ps1                # só diagnóstico
.\scripts\windows\doctor.ps1 -Fix           # instala o que falta
```

O instalador cria o `.venv`, instala o PyTorch certo, compila a UI e gera o `.env`. É seguro rodar de novo.

```powershell
.\scripts\windows\setup.ps1 -Cpu         # força CPU
.\scripts\windows\setup.ps1 -Speakers    # + Pessoa 1 / Pessoa 2 (precisa de HF_TOKEN)
.\scripts\windows\setup.ps1 -Overlay     # + janela flutuante (precisa de Rust, ~10 min)
```

## Usar

**Janela flutuante** (depois do overlay) ou **navegador**:

```powershell
.\WhisperBridge.bat                          # overlay (ou navegador, se o exe não existir)
.\scripts\windows\start-browser.ps1          # só navegador
```

1. Toque uma reunião ou vídeo **em inglês** (ou fale no microfone).
2. Escolha **Som do PC** ou **Microfone**.
3. Clique em **Iniciar**.
4. No modo **Recomendado (IA)** (⚙): cole a chave e escolha os idiomas da fala e da legenda.

Não feche com **✕** se quiser deixar o servidor rodando — use **minimizar**. O ✕ desliga o motor de propósito (libera a memória da placa).

Para matar um processo preso: `.\scripts\windows\stop.ps1`

## Modos

| Nome na tela | Quando usar |
|---|---|
| **Neste PC (rápido)** | Sem internet. Inglês → português neste computador. |
| **Recomendado (IA)** | Melhor tradução. Você cola a chave (Gemini etc.) e escolhe os idiomas. |
| **IA sem placa de vídeo** | Quer liberar o jogo / outro app. Ouvir fica mais lento. |
| **Neste PC (sem internet)** | Sem placa e sem rede. Mais lento. |

Custo típico da IA no Gemini Flash-Lite: **cerca de US$ 0,02–0,04 por hora** de reunião. O áudio não é enviado.

## Chave da IA (opcional)

Não é obrigatória. Sem chave, o modo local já gera legendas.

1. Abra **⚙ → Idiomas e chave da IA**
2. Gemini: [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
3. Ou GPT / DeepSeek: cole a chave + URL + modelo

A chave fica só na sua máquina (`user-settings.json` e `.env` — não vão para o Git).

## Privacidade

| Dado | Vai para a internet? |
|---|---|
| Áudio da reunião | **Não** |
| Texto transcrito (modo IA) | Sim, só o texto, para a API que você configurou |
| Sua chave | Só para o provedor que você escolheu |

## Estrutura

```
whisperbridge/
├── Instalar.bat / WhisperBridge.bat / install.sh   atalhos da raiz
├── run_server.py                                   python -m whisperbridge
├── src/whisperbridge/                              motor (áudio, VAD, Whisper, tradução)
│   ├── server.py                                   FastAPI + WebSocket
│   └── config/                                     portas, perfis, preferências
├── scripts/windows/  scripts/linux/                doctor, setup, launcher
├── requirements/                                   windows.txt · linux.txt
├── apps/desktop/                                   React + Tauri (overlay)
└── assets/                                         ícone e imagens do README
```

---

# English

Live subtitles for English meetings on Windows. Captures **system audio** (Teams, Meet, Zoom, YouTube) or the **microphone**, transcribes on-device with Whisper, and shows a translation overlay.

- **Listening is always local.** Meeting audio never leaves the PC.
- **Translation** can stay on-device or use **your** API key (Gemini, GPT, DeepSeek…).
- No Rust required: use the **browser**. Optional overlay window if you install Rust.

<p align="center">
  <img src="assets/docs/flow-en.svg" width="900" alt="Flow: capture → Whisper → translate → subtitle">
</p>

## Requirements

| | |
|---|---|
| OS | Windows 10/11 or Linux (Pulse/PipeWire) |
| Python | **3.10–3.12** (3.13 is not supported) |
| Node.js | LTS |
| GPU | NVIDIA recommended; CPU-only works, slower |
| Optional | Rust — only for the floating overlay |

## Install (easiest)

**Windows** — after `git clone`, double-click `Instalar.bat`

**Linux:**

```bash
chmod +x install.sh scripts/linux/*.sh
./install.sh
# or
./scripts/linux/doctor.sh           # check only
./scripts/linux/doctor.sh --fix     # install missing pieces
./scripts/linux/start-browser.sh    # run
```

If PyAudio fails on Ubuntu/Debian:

```bash
sudo apt install python3.12 python3.12-venv python3.12-dev portaudio19-dev
```

On Linux, **PC sound** uses the PulseAudio/PipeWire *monitor* device. Microphone works the same.

Menu:

1. **Check this PC only** — doctor: RAM, GPU, Python, Node, what’s missing, **which modes you can use**
2. **Install what’s missing** (recommended) — tries Python/Node via `winget`, then runs setup
3. **Install + floating window** — needs Rust
4. **Open WhisperBridge now**

From a terminal:

```powershell
git clone https://github.com/afborda/whisperbridge.git
cd whisperbridge
.\Instalar.bat                              # menu (double-click also works)
.\scripts\windows\doctor.ps1                # diagnose only
.\scripts\windows\doctor.ps1 -Fix           # install missing pieces
```

The installer creates the venv, installs the right PyTorch, builds the UI, and writes `.env`. Safe to re-run.

```powershell
.\scripts\windows\setup.ps1 -Cpu         # force CPU
.\scripts\windows\setup.ps1 -Speakers    # + speaker labels (needs HF_TOKEN)
.\scripts\windows\setup.ps1 -Overlay     # + floating window (needs Rust, ~10 min)
```

## Run

```powershell
.\WhisperBridge.bat                          # overlay (or browser if the exe is missing)
.\scripts\windows\start-browser.ps1          # browser only
```

1. Play an **English** meeting or video (or speak into the mic).
2. Pick **PC sound** or **Microphone**.
3. Click **Start**.
4. In **Recommended (AI)** (gear icon): paste your key and set spoken / subtitle languages.

Don’t use **✕** if you want the engine to keep running — **minimize** instead. ✕ shuts the engine down on purpose (frees GPU memory).

Stuck process: `.\scripts\windows\stop.ps1`

## Modes

| On-screen name | Use when |
|---|---|
| **On this PC (fast)** | Offline. English → Portuguese on this computer. |
| **Recommended (AI)** | Best translation. You paste a key and pick languages. |
| **AI without GPU** | Free the graphics card for a game / other app. Listening is slower. |
| **On this PC (offline)** | No GPU, no internet. Slowest. |

Typical Gemini Flash-Lite cost: **about US$ 0.02–0.04 per hour** of meeting. Audio is not uploaded.

## API key (optional)

Not required. Local mode already produces subtitles.

1. Open **⚙ → Languages and AI key**
2. Gemini: [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
3. Or GPT / DeepSeek: paste key + URL + model

Keys stay on your machine (`user-settings.json` and `.env` — gitignored).

## Privacy

| Data | Leaves the PC? |
|---|---|
| Meeting audio | **No** |
| Transcript text (AI mode) | Yes, text only, to the API you configured |
| Your API key | Only to the provider you chose |

## License

[MIT](LICENSE)
