# AGENTS.md

WhisperBridge captura o áudio do Windows (WASAPI loopback ou microfone), transcreve inglês localmente com Whisper, traduz para português e mostra legendas num overlay always-on-top. A transcrição nunca sai da máquina. Comentários, docs e strings de UI são em português brasileiro — código novo segue o mesmo.

## Layout

```
src/whisperbridge/     pacote Python (server, audio, vad, transcription, translation, config)
scripts/windows|linux/ doctor, setup, launcher, stop
apps/desktop/          React + Tauri
requirements/          windows.txt · linux.txt
```

Na raiz só ficam atalhos (`Instalar.bat`, `WhisperBridge.bat`, `install.sh`) e `run_server.py`.

## Comandos

Não existe linter nem test runner. Sempre use o interpretador do `.venv`. Python suportado: **3.10–3.12** (torch 2.5.1 não tem wheel para 3.13).

`requirements/windows.txt` existe, mas **não rode `pip install -r` nele direto**. O PyTorch CUDA fica de fora de propósito: o pip trata `+cu121` como versão local, desinstala a build CUDA e põe a CPU no lugar, sem erro. Use o instalador:

```powershell
.\scripts\windows\setup.ps1                 # detecta a máquina; cria .venv, instala torch, builda a UI
.\scripts\windows\setup.ps1 -Cpu            # ignora a GPU
.\scripts\windows\setup.ps1 -Speakers       # + pyannote (opcional; pip recusa por conflito de torch)
.\scripts\windows\setup.ps1 -Overlay        # + janela Tauri (precisa de Rust, ~10 min)
```

```powershell
# Engine (FastAPI + modelos + UI estática) — 127.0.0.1:37865
.venv\Scripts\python.exe -u run_server.py
# equivalente: .venv\Scripts\python.exe -m whisperbridge

# App completo (engine + overlay)
.\WhisperBridge.bat              # ou duplo clique em WhisperBridge.vbs
.\WhisperBridge.bat -console     # console + log
.\WhisperBridge.bat -Dev         # engine + `npm run tauri dev`

# Sem Rust: mesma UI numa aba do navegador
.\scripts\windows\start-browser.ps1

# Mata engine/UI presos (libera a porta 37865)
.\scripts\windows\stop.ps1

# Frontend
cd apps\desktop
npm run build                    # tsc + vite → apps/desktop/dist  (OBRIGATÓRIO, ver abaixo)
npm run tauri build              # exe em src-tauri/target/release/desktop.exe

# Copia o exe para a raiz como WhisperBridge-UI.exe e recria o atalho
.\scripts\windows\install-shortcut.ps1
```

Log do launcher: `%TEMP%\WhisperBridge-launch.log`.

## Arquitetura

### Dois processos

Coordenados por `scripts/windows/launcher.ps1`:

1. **Engine** (`run_server.py` → `src/whisperbridge/server.py`) — FastAPI em `127.0.0.1:37865`. Serve `/health`, `/profiles`, `/debug`, `/ws` e o React buildado em `/` via `StaticFiles`.
2. **UI** — shell Tauri frameless always-on-top cujo único trabalho é apontar o WebView para a URL do engine. O Rust em `lib.rs` quase não tem lógica. Sem Rust, `scripts/windows/start-browser.ps1` abre a mesma UI no navegador.

O launcher sobe o engine, espera `/health` responder `loading` ou `ok` (não espera os modelos), e abre a UI. Fechar a janela mata o engine.

### A frontend é servida pelo Python, não pelo Tauri

`apps/desktop/src-tauri/tauri.conf.json` pinna a janela em `"url": "http://127.0.0.1:37865/"`. Essa URL absoluta ganha de `frontendDist` e do Vite `devUrl`:

- **Depois de qualquer mudança em `apps/desktop/src`, rode `npm run build`.** O engine serve `apps/desktop/dist`; sem rebuild o overlay mostra o bundle antigo mesmo no `tauri dev`.
- `apps/desktop/dist/` está no gitignore mas é requisito de runtime — sem ele o engine imprime `AVISO: dist da UI nao encontrado` e `/` fica vazio.
- Recompilar o exe Rust falha com o app aberto (Cargo não sobrescreve o binário em uso). Feche a janela primeiro.
- Janela atual: 520×560, `transparent: false`, `decorations: false`, `alwaysOnTop: true`, `center: true`.

Componentes em `apps/desktop/src/components/`: `TitleBar` (controles, perfil, áudio, custo), `SubtitleOverlay`, `LoadingScreen`, `ProfilePicker`, `AudioSourcePicker`. `ControlBar.tsx` é leftover — não está montado; os botões moram no `TitleBar`.

### Perfis de execução

`src/whisperbridge/config/profiles.py` define quatro perfis. O que importa é **o que sobe na memória**, não só onde traduz. Quem come a GPU é o Whisper (~2.3 GB via CTranslate2); o tradutor é 0.44 GB. Mandar só a tradução para a nuvem **não** libera a placa — os perfis leves movem o Whisper para CPU (`small.en` + `int8`).

| id | Whisper | Tradução | Precisa |
|---|---|---|---|
| `gpu` (padrão) | medium.en CUDA float16 | MarianMT local CUDA | GPU |
| `gpu-nuvem` | medium.en CUDA float16 | LLM + MarianMT fallback | GPU + chave |
| `leve` | small.en CPU int8 | LLM + MarianMT fallback | chave |
| `leve-offline` | small.en CPU int8 | MarianMT local CPU | nada |

**Transcrição nunca vai para a nuvem.** Whisper local resolve 6 s em ~336 ms; RTT de qualquer API de transcrição já custa 400–900 ms. A nuvem só entra na tradução.

`_switch_profile_sync()` para a captura, dá join na thread de áudio, espera o segmento em voo, descarrega, recarrega — tudo sob `_swap_lock`. Pular qualquer passo derruba o processo, porque a thread de captura segura referências a `_whisper`.

Fechar a janela **tem** que matar o engine. `ThreadPoolExecutor` não é daemon: se o Python só “encerra” o uvicorn, Whisper fica na RAM/VRAM. Contrato: `POST /shutdown` descarrega modelos e dá `os._exit(0)`. A UI chama isso no ✕; o último WebSocket desconectado agenda o mesmo em 20 s; o launcher usa Job Object `KILL_ON_JOB_CLOSE`. Não remova nenhum desses três — um sozinho falha (aba do browser, X da taskbar, console fechado).

**VRAM vem de `torch.cuda.mem_get_info()`, nunca de `memory_allocated()`.** O segundo só vê o alocador do PyTorch; faster-whisper aloca via CTranslate2 e reportava 0.00 GB com 1.09 GB no driver.

Perfil impossível (sem CUDA, sem chave) chega com `available: false` e `unavailable_reason` — a UI bloqueia a opção, não deixa escolher algo que vai falhar.

### Tradução na nuvem (revisão híbrida)

`translation/llm_translator.py` fala com Gemini e qualquer endpoint OpenAI-compatível (GPT, DeepSeek, Kimi, MiniMax) via `httpx` cru — sem SDKs (retry com backoff briga com o orçamento de latência; timeout padrão 2.5 s).

O tradutor local **sempre carrega**, inclusive nos perfis de nuvem: na CPU não gasta VRAM e é o que segura a legenda se a rede cair. Pipeline sempre local-first — `_process_segment_inner` emite a legenda local na hora, depois `_submit_revision` manda para `_revision_executor` (pool separado, 2 workers). A revisão volta como `subtitle_revision` com o **mesmo `id`**; o hook React substitui a linha no lugar.

`load_cloud_translator` nunca levanta: perfil de nuvem sem chave degrada para local e o engine sobe.

Falha da nuvem devolve `None` e a legenda local fica. Nunca é aceitável uma legenda sumir porque a internet piscou. Falhas logam com throttle de 30 s. `MAX_PENDING_REVISIONS` (6) descarta revisão em vez de enfileirar se a nuvem não acompanha a fala.

A revisão **pode** receber as últimas 6 falas em inglês como contexto — o LLM tem prompt de verdade. Não reintroduzir prefixo de contexto no MarianMT (ver abaixo).

### Carga de modelos é adiada de propósito

`lifespan` retorna na hora e empurra `_load_models_sync` para um executor: HTTP sobe em ~1 s enquanto ~2.5 GB de modelos carregam. `/health` reporta `loading` → `ok` → `error`. O hook `useEngineReady` faz poll e segura o app atrás de `LoadingScreen` até `ok`. `start` recebido com `_models_ready == false` é rejeitado, não enfileirado. Preserve isso — é o que evita a janela branca / connection refused no boot.

### Pipeline de áudio (threads)

```
capture thread          _capture_thread()   chunks de 100 ms, resample → 16 kHz mono
   ├─ VAD               VoiceDetector       Silero, max score em blocos de 512
   ├─ VoiceBuffer.push  buffer.py           flush em 0.65 s de silêncio OU 6.0 s;
   │     │                                  descarta < MIN_SEGMENT_S (0.45 s)
   │     └─ _on_segment → executor.submit   retorna na hora; captura nunca bloqueia
   └─ preview parcial   transcribe_partial  só com _segment_in_flight limpo
                                            (nunca disputa GPU com segmento real)

segment worker          ThreadPoolExecutor(max_workers=1)   ← garantia de ordem
   Whisper.transcribe → _split_chunks (1 frase, ≤24 palavras) → translate_batch
   → SpeakerTracker.identify → _emit() → (opcional) _submit_revision

asyncio                 _broadcaster()      drena a queue, espalha para os /ws
```

O executor de 1 worker é a garantia de ordem das legendas; subir `max_workers` reordena linhas. **Toda entrega entre threads passa por `_emit()`**, que envolve `loop.call_soon_threadsafe` — `asyncio.Queue` não é thread-safe. Nunca chame `_broadcast_queue.put_nowait` direto da captura ou do worker, e nunca `await ws.send` de nenhuma das duas.

Comprimento de segmento é botão de **legibilidade**, não só de latência: Whisper alucina em fragmento truncado, MarianMT produz lixo em oração sem sujeito, embedding do wespeaker é ruído abaixo de ~1.5 s. Os três degradam juntos. `SILENCE_FLUSH_S` / `MAX_SEGMENT_S` / `MIN_SEGMENT_S` (`src/whisperbridge/vad/buffer.py`), `CHUNK`, `MAX_WORDS_PER_CHUNK`, `PARTIAL_INTERVAL` (0.9 s), `PARTIAL_MIN_CHUNKS` (8) (`src/whisperbridge/server.py`) e `beam_size`/`best_of` (`src/whisperbridge/transcription/whisper_engine.py`) foram afinados uns contra os outros. Cada um tem um comentário do que o valor anterior quebrou — leia antes de mudar.

`_split_chunks` devolve **uma frase por chunk**. MarianMT é sentence-level: duas frases numa entrada e ele traduz uma e descarta a outra. 24 palavras é válvula de segurança para monólogo sem pontuação, não o tamanho alvo da linha.

### Fonte de áudio

`loopback` (padrão) = o que o PC está tocando (a reunião). `mic` = a voz de quem está na máquina.

Whisper aqui é `medium.en` / `small.en` e a tradução é EN→PT de mão única. Falar português no microfone produz lixo, não legenda em português. O mic só faz sentido se quem fala nele estiver falando inglês.

`set_audio_source` para a captura, dá join na thread e reabre o stream — o PyAudio não troca dispositivo com o stream aberto. Roda em executor para não bloquear o loop asyncio. Dispositivo escolhido que some (fone desconectado) volta ao automático.

### Identificação de falantes

`vad/speaker_tracker.py` faz **speaker ID online, não diarização**. Por pessoa: galeria rolante de embeddings pyannote/wespeaker + centróide. Decisão com histerese em similaridade cosseno (maior = mesma voz): `>= SAME_SPEAKER_SIM` (0.58) atribui e aprende; `< NEW_SPEAKER_SIM` (0.42) com áudio forte (`STRONG_AUDIO_S` 2.5 s) cria pessoa nova; a faixa do meio atribui sem aprender. Segmento curto (`< MIN_AUDIO_S` 0.9 s) ou quieto herda `_last_id`. A cada `RECLUSTER_EVERY` embeddings aprendidos, reagrupa fantasmas (sklearn agglomerative, fallback pairwise).

`pyannote.audio` **não** está em `requirements/windows.txt`: declara `torch>=2.8` e o pip recusa, embora funcione na prática com 2.5.1. Instala só com `.\scripts\windows\setup.ps1 -Speakers`.

Precisa de `HF_TOKEN` no `.env` da raiz (gitignore, carregado por `server.py`). Sem token ou sem pyannote o engine roda; `speakerId`/`speakerColor` chegam `null` e o frontend cai na heurística de pausa (> 2.5 s) em `useTranslationSocket`.

### Protocolo WebSocket

Cliente → servidor: `{type: "start" | "pause" | "stop" | "ping" | "clear_context" | "set_profile" | "get_profiles" | "set_audio_source"}`.

Servidor → cliente: `{type: "status" | "vad" | "subtitle" | "subtitle_revision" | "profiles" | "profile_changed" | "profile_error" | "audio" | "cost" | "pong", data: {...}}`.

Dois tipos de `subtitle`: `status: "partial"` sempre com `id: "live"` e texto só em inglês (o frontend substitui `livePartial`); `status: "translated"` com `id: "seg-<ms>-<i>"`, entra no histórico. `willRevise: true` quando uma revisão da nuvem ainda vem. Formas das mensagens estão duplicadas à mão em `useTranslationSocket.ts` — mude os dois lados juntos.

`clear_context` zera a galeria de falantes. Não há mais prefixo de contexto no MarianMT.

`/health` e a mensagem `profiles` carregam perfil ativo, lista (com `available`), VRAM, custo da sessão e estado de áudio. Mensagem `cost` sai junto de cada revisão.

### Portas — quatro lugares

`src/whisperbridge/config/ports.py` (37865 / 14287) é a fonte da verdade, espelhada em `apps/desktop/src/config.ts`, `tauri.conf.json` (`app.windows[0].url` e `build.devUrl`) e `apps/desktop/vite.config.ts`. Mudar porta é editar os quatro.

### Tradução local

`Translator.translate_batch` manda todos os chunks do segmento num único `model.generate` — custo aproximadamente flat no número de chunks. Depois: `to_ptbr()` e só então `apply_glossary()`. A ordem importa: o glossário restaura termos técnicos que não podem ser reescritos. Vocabulário de domínio entra em `src/whisperbridge/translation/glossary.py`.

**O modelo de tradução foi avaliado e mantido de propósito.** `opus-mt-tc-big-en-pt` puxa para pt-PT; `unicamp-dl/translation-en-pt-t5` foi comparado em frases reais capturadas:

| | opus-mt (mantido) | unicamp t5 |
|---|---|---|
| VRAM | 0.44 GB | 0.83 GB |
| Latência, 1 frase | 70 ms | 170 ms |
| Latência, lote de 3 | 69 ms | 111 ms |
| marcas pt-PT | 6/12 | 1/12 |

O T5 é mais brasileiro e **menos fiel** — inverteu "have a little faith" em "tem pouca fé", dropou o objeto de "We need you", transformou "Let me work Donald on this" em "Tenho um trabalho de Donald". Sotaque é cosmético e se conserta com regex a ~0 ms; erro de sentido, não. Não troque o modelo por sotaque — rode a comparação de novo.

(Aquele repo só tem `pytorch_model.bin`; transformers 5.x recusa sob torch 2.5.1 por causa da CVE-2025-32434. Converter para safetensors localmente é o workaround; subir o torch quebra CTranslate2 e pyannote.)

**Defeito conhecido do modelo:** `Ó` e `Ú` maiúsculos são `<unk>` no SentencePiece do opus-mt (`Á` e `É` passam). "Ótimo" vira "timo", "Único" vira "nico". `ptbr.py` conserta, mas só no começo da frase, que é onde a capital aparece.

**Não reintroduza prefixo de contexto no MarianMT.** Uma versão antiga colava os dois chunks ingleses anteriores no primeiro item do lote. MarianMT é sentence-level e não distingue contexto de texto novo — traduzia e devolvia o conjunto inteiro, então cada legenda repetia as duas linhas anteriores e acrescentava um pedaço novo. Contexto só volta a fazer sentido com modelo que aceita prompt de verdade (já é o caso do LLM da revisão).

### Anti-alucinação do Whisper

`temperature` precisa continuar **tupla**. Com escalar `0.0` o loop de fallback do faster-whisper tem uma iteração só, então `compression_ratio_threshold` e `log_prob_threshold` são avaliados e ignorados — decode ruim passa. `best_of` também é morto se nenhuma temperatura for > 0. `hallucination_silence_threshold` não faz nada aqui porque só roda com `word_timestamps=True`.

Thresholds não pegam `"Thanks for watching"` e amigos: o Whisper emite isso com *alta* confiança (viés de legendas do YouTube). `whisper_engine.py` aplica `_is_hallucination()`, blocklist contra o segmento inteiro normalizado — nunca como substring, para um "thank you" real no meio de uma frase sobreviver.

## Variáveis de ambiente (`.env` na raiz, gitignore)

| variável | para quê |
|---|---|
| `PROFILE` | perfil inicial (`gpu`, `gpu-nuvem`, `leve`, `leve-offline`) |
| `HF_TOKEN` | speaker ID (pyannote). Sem ele, heurística de pausa |
| `TRANSLATOR_BACKEND` | `gemini` ou `openai-compat` nos perfis de nuvem |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Gemini (default `gemini-3.5-flash-lite`) |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | OpenAI-compat (default `gpt-4o-mini` em api.openai.com) |
| `LLM_TIMEOUT_S` | timeout da revisão (default 2.5) |
| `LLM_PRICE_IN` / `LLM_PRICE_OUT` | USD por milhão de tokens; sobrescreve a tabela |

Nada disso é obrigatório para o perfil `gpu` / `leve-offline`.

## Convenções

- Comentários e strings de UI em pt-BR.
- Não suba o torch além de 2.5.1 — teto do CTranslate2 e do pyannote.
- Não adicione SDK oficial de LLM. `httpx` cru é a regra.
- `pyproject.toml` só declara o pacote `src/whisperbridge`. Instalação continua pelos scripts + `requirements/` — não use Poetry/`pip install .` no lugar do setup.
- Constantes afinadas têm comentário do valor anterior que quebrou — leia antes de retocar.
- Fonte da verdade: os arquivos-fonte. Constantes, tamanho de janela e lista de componentes estão aqui e no código.
