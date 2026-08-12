import asyncio
import json
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Set

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from scipy.signal import resample_poly
from math import gcd

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

from shared import user_settings as uset
uset.load()  # overlay do user-settings.json em cima do .env

from ..audio.backend import pyaudio, is_loopback, host_api, display_name

from ..vad.detector import VoiceDetector
from ..vad.buffer import VoiceBuffer, AudioSegment
from ..vad.speaker_tracker import load_tracker, SpeakerTracker
from ..transcription.whisper_engine import (
    WhisperEngine, collapse_repeats, similar_enough,
)
from ..translation.translator import Translator
from ..translation.glossary import apply_glossary
from ..translation.ptbr import to_ptbr
from ..translation.llm_translator import (
    CloudTranslator, load_cloud_translator, is_portuguese_target,
)
from shared import profiles as prof

SAMPLE_RATE = 16000
# 1600 samples @ 16kHz = 100ms — antes era 8000 (500ms), o que atrasava VAD e legendas
CHUNK = 1600
# Só fallback se o loopback da saída padrão não existir. NÃO preferir JBL Quantum
# por palavra-chave: headset gamer expõe 3–5 dispositivos virtuais (Game/Chat/7.1)
# e o primeiro match costuma ser o canal errado — áudio baixo, Whisper "surdo".

# ── estado global ─────────────────────────────────────────────────────────────
_detector: VoiceDetector | None = None
_whisper: WhisperEngine | None = None
_translator: Translator | None = None
_voice_buffer: VoiceBuffer | None = None
_speaker_tracker: SpeakerTracker | None = None

_cloud: CloudTranslator | None = None
_active_profile: prof.Profile = prof.resolve()

_is_running = False
_models_ready = False
_models_error: str | None = None
_audio_thread: threading.Thread | None = None

# Serializa carga/descarga de modelos contra a captura. Sem isto, trocar de perfil
# enquanto a thread de áudio usa _whisper derruba o processo.
_swap_lock = threading.Lock()

# Executor com 1 worker: garante que segmentos são processados em ordem
# mas sem bloquear o thread de captura de áudio
_segment_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="seg-worker")

# Revisões da nuvem ficam FORA do executor de segmentos, senão a latência de rede
# entraria no caminho crítico da legenda. 2 workers: revisão é I/O, não CPU.
_revision_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="revision")
_revisions_pending = 0
_revisions_lock = threading.Lock()
MAX_PENDING_REVISIONS = 6  # fala rápida + nuvem lenta: descarta em vez de acumular

# Gasto acumulado de tradutores JÁ descarregados. O tradutor vivo conta por conta
# própria; o total mostrado na UI é este + o dele. Ver _bank_cloud_cost().
_cloud_spent = {"calls": 0, "tokensIn": 0, "tokensOut": 0, "usd": 0.0}
_cloud_spent_lock = threading.Lock()

# Encerramento: o launcher às vezes não mata o Python (VBS não espera, console
# fechado no X, aba do browser). Sem isto os modelos ficam na RAM/VRAM.
_shutting_down = False
_had_client = False
_idle_timer: threading.Timer | None = None
_idle_lock = threading.Lock()
# 20s era curto demais: a UI abre, o React reconecta o WS (fecha o socket
# antigo) e o timer matava o engine — a janela "abria e fechava sozinha".
# 15 min cobre fechar a aba de verdade sem derrubar um piscar de reconnect.
IDLE_SHUTDOWN_S = 15 * 60.0


def _bank_cloud_cost(cloud: CloudTranslator) -> None:
    s = cloud.stats()
    with _cloud_spent_lock:
        _cloud_spent["calls"] += s["calls"]
        _cloud_spent["tokensIn"] += s["tokensIn"]
        _cloud_spent["tokensOut"] += s["tokensOut"]
        _cloud_spent["usd"] += s["usd"] or 0.0


def _cost_state() -> dict:
    """Gasto da sessão: o que já foi descarregado + o tradutor atual."""
    cloud = _cloud
    live = cloud.stats() if cloud else None
    with _cloud_spent_lock:
        base = dict(_cloud_spent)
    if not live:
        return {**base, "model": None, "priced": True}
    return {
        "calls": base["calls"] + live["calls"],
        "tokensIn": base["tokensIn"] + live["tokensIn"],
        "tokensOut": base["tokensOut"] + live["tokensOut"],
        "usd": base["usd"] + (live["usd"] or 0.0),
        "model": live["model"],
        # False => modelo fora da tabela de preços: mostrar tokens, não dinheiro
        "priced": live["pricedPerMillion"] is not None,
    }

# True enquanto _process_segment está RODANDO. Antes olhávamos _work_queue.qsize(),
# mas a fila zera assim que o worker pega a tarefa — ou seja, o preview "live" rodava
# Whisper na thread de captura ao mesmo tempo que o segmento final, disputando a GPU.
_segment_in_flight = threading.Event()

# Queue para comunicação thread → asyncio (o jeito correto)
_broadcast_queue: asyncio.Queue | None = None
_loop: asyncio.AbstractEventLoop | None = None
_clients: Set[WebSocket] = set()


def _emit(msg: dict) -> None:
    """Publica no broadcaster a partir de QUALQUER thread.

    asyncio.Queue não é thread-safe: put_nowait direto da thread de captura ou do
    worker pode não acordar o _broadcaster que está parado no await get().
    call_soon_threadsafe agenda no loop dono da queue.
    """
    if _broadcast_queue is None or _loop is None:
        return
    try:
        _loop.call_soon_threadsafe(_broadcast_queue.put_nowait, msg)
    except RuntimeError:
        pass  # loop já fechado no shutdown


# ── helpers ───────────────────────────────────────────────────────────────────
def _resample(audio, from_rate, to_rate=SAMPLE_RATE):
    if from_rate == to_rate:
        return audio
    d = gcd(from_rate, to_rate)
    return resample_poly(audio, to_rate // d, from_rate // d).astype(np.float32)


def _to_mono(audio, channels):
    if channels <= 1:
        return audio
    return audio.reshape(-1, channels).mean(axis=1)


def _find_loopback(p):
    """Loopback da SAÍDA PADRÃO do Windows — o que o Teams/Meet está tocando.

    Antes preferíamos o primeiro dispositivo cujo nome tivesse 'jbl quantum'.
    Headset gamer publica vários endpoints virtuais; o match errado entrega
    áudio quase mudo e o Whisper só entende quem fala colado no microfone.
    """
    loopbacks = [(i, p.get_device_info_by_index(i))
                 for i in range(p.get_device_count())
                 if is_loopback(p.get_device_info_by_index(i))]
    if not loopbacks:
        raise RuntimeError("Nenhum dispositivo loopback encontrado")

    try:
        out_idx = host_api(p).get("defaultOutputDevice")
        if out_idx is not None and out_idx >= 0:
            out_name = p.get_device_info_by_index(out_idx)["name"]
            out_key = out_name.lower().replace(" [loopback]", "")
            for idx, dev in loopbacks:
                if dev["name"].lower().replace(" [loopback]", "") == out_key:
                    return idx, dev
            for idx, dev in loopbacks:
                if out_key and out_key in dev["name"].lower():
                    return idx, dev
    except Exception as e:
        print(f"[audio] nao achei loopback da saida padrao: {e}", flush=True)

    return loopbacks[0]


# ── fonte de áudio ────────────────────────────────────────────────────────────
# "loopback" = o que o PC está tocando (a reunião que você ouve). É o caso para
#              o qual o projeto foi feito: legendar quem fala com você.
# "mic"      = a sua própria voz.
#
# Atenção ao usar "mic": o Whisper aqui é medium.en / small.en, modelos SÓ de
# inglês, e a tradução é EN->PT de mão única. Falar português no microfone não
# produz legenda em português — produz lixo. O microfone só faz sentido se quem
# fala nele estiver falando inglês.
_audio_source = "loopback"
_audio_device_index: int | None = None   # None = escolha automática dentro da fonte

_devices_cache: tuple[float, list[dict]] = (0.0, [])


def _list_audio_devices() -> list[dict]:
    """Entradas de audio, separadas por fonte. Cache curto: /health consulta
    de segundo em segundo no boot e abrir o PyAudio custa."""
    global _devices_cache
    agora = time.time()
    if agora - _devices_cache[0] < 5.0:
        return _devices_cache[1]

    devices: list[dict] = []
    p = pyaudio.PyAudio()
    try:
        w = host_api(p)
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if d["hostApi"] != w["index"] or d["maxInputChannels"] < 1:
                continue
            devices.append({
                "index": i,
                "name": display_name(d),
                "source": "loopback" if is_loopback(d) else "mic",
                "isDefault": i == w.get("defaultInputDevice"),
            })
    except Exception as e:
        print(f"[audio] nao consegui listar dispositivos: {e}", flush=True)
    finally:
        p.terminate()

    _devices_cache = (agora, devices)
    return devices


def _find_mic(p):
    """Entrada padrao; se nao houver, a primeira que nao e loopback."""
    idx = host_api(p).get("defaultInputDevice")
    if idx is not None and idx >= 0:
        dev = p.get_device_info_by_index(idx)
        if not is_loopback(dev) and dev["maxInputChannels"] >= 1:
            return idx, dev
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["maxInputChannels"] >= 1 and not is_loopback(d):
            return i, d
    raise RuntimeError("Nenhum microfone encontrado")


def _find_device(p):
    """Resolve a fonte ativa em (indice, info)."""
    if _audio_device_index is not None:
        try:
            dev = p.get_device_info_by_index(_audio_device_index)
            if dev["maxInputChannels"] >= 1:
                return _audio_device_index, dev
        except Exception:
            # dispositivo escolhido sumiu (fone desconectado, dock removido) —
            # melhor voltar ao automático do que derrubar a captura
            print("[audio] dispositivo escolhido indisponivel; usando o padrao",
                  flush=True)
    return _find_mic(p) if _audio_source == "mic" else _find_loopback(p)


def _set_audio_source(source: str, index: int | None = None) -> None:
    """Troca a fonte. Se a captura estiver rodando, para e recria a thread — o
    stream do PyAudio é aberto uma vez no início dela e não dá para trocar de
    dispositivo com ele aberto."""
    global _audio_source, _audio_device_index, _is_running, _audio_thread

    estava_rodando = _is_running
    if estava_rodando:
        _is_running = False
        if _audio_thread is not None:
            _audio_thread.join(timeout=3)

    _audio_source = source
    _audio_device_index = index if isinstance(index, int) else None
    print(f"[audio] fonte agora: {source} (indice {_audio_device_index})", flush=True)

    if estava_rodando:
        _is_running = True
        _audio_thread = threading.Thread(target=_capture_thread, daemon=True)
        _audio_thread.start()


def _audio_state() -> dict:
    return {
        "source": _audio_source,
        "deviceIndex": _audio_device_index,
        "devices": _list_audio_devices(),
    }


# Válvula de segurança para fala longa SEM pontuação (o Whisper às vezes devolve um
# parágrafo inteiro sem ponto). Não é o tamanho alvo da linha: a UI quebra sozinha,
# então frase inteira é sempre melhor para o tradutor do que linha curta.
MAX_WORDS_PER_CHUNK = 24


def _split_chunks(text: str, max_words: int = MAX_WORDS_PER_CHUNK) -> list[str]:
    """UMA frase por chunk — nunca duas.

    O MarianMT é sentence-level. Se receber duas frases numa entrada só, ele
    costuma traduzir uma e DESCARTAR a outra. Visto ao vivo:
        "Then what are we talking about? Just asking a simple question."
        -> "Só estou a fazer uma pergunta simples."     (perdeu a pergunta)
    Por isso frases nunca são agrupadas; só quebramos uma frase comprida demais,
    preferindo a vírgula ao corte bruto por contagem de palavras.
    """
    text = text.strip()
    if not text:
        return []

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        sentences = [text]

    chunks: list[str] = []
    for sent in sentences:
        words = sent.split()
        if len(words) <= max_words:
            chunks.append(sent)
            continue

        parts = [p.strip() for p in re.split(r"(?<=,)\s+", sent) if p.strip()]
        if len(parts) > 1:
            buf: list[str] = []
            for part in parts:
                pw = part.split()
                if buf and len(buf) + len(pw) > max_words:
                    chunks.append(" ".join(buf))
                    buf = pw
                else:
                    buf.extend(pw)
            if buf:
                chunks.append(" ".join(buf))
        else:
            for i in range(0, len(words), max_words):
                chunks.append(" ".join(words[i:i + max_words]))

    return [c for c in chunks if c]


def _process_segment(seg: AudioSegment):
    """Roda em thread separada — não bloqueia a captura de áudio."""
    _segment_in_flight.set()
    try:
        _process_segment_inner(seg)
    finally:
        _segment_in_flight.clear()


_last_emitted_en = ""
_last_emitted_lock = threading.Lock()


def _process_segment_inner(seg: AudioSegment):
    global _last_emitted_en
    t_start = time.time()

    # 1. transcrição (prioridade: legenda rápida)
    result = _whisper.transcribe(seg.audio, language=uset.get().whisper_language())
    if not result.text.strip():
        return

    with _last_emitted_lock:
        if similar_enough(result.text, _last_emitted_en):
            print("[pipeline] segmento repetido — ignorado", flush=True)
            return

    # 2. uma frase por chunk (MarianMT/LLM quebram se juntar duas)
    chunks = _split_chunks(result.text)

    # 3. falante (rápido; não bloqueia a captura — só este worker)
    speaker = {"id": None, "color": None, "is_new": False}
    t_spk = time.time()
    if _speaker_tracker:
        try:
            speaker = _speaker_tracker.identify(seg.audio)
        except Exception as e:
            print(f"[speaker] erro: {e}", flush=True)
    t_spk_ms = (time.time() - t_spk) * 1000

    # Com nuvem: NÃO roda MarianMT no caminho crítico. Ele gerava "gado" /
    # "oleoduto" na tela e a revisão ou não chegava ou piscava por cima.
    # Mostra o inglês (provisório); o PT vem da nuvem. Local só se a nuvem falhar.
    use_cloud = _cloud is not None
    t_trans = time.time()
    local_pts: list[str] = [""] * len(chunks)
    if not use_cloud:
        batch_results = _translator.translate_batch(chunks)
        local_pts = [
            apply_glossary(to_ptbr(collapse_repeats(tr.translated_text))).strip()
            for tr in batch_results
        ]
    t_trans_total = (time.time() - t_trans) * 1000

    print(
        f"[pipeline] audio={seg.duration_s:.1f}s "
        f"transcricao={result.processing_time_s*1000:.0f}ms "
        f"chunks={len(chunks)} "
        f"{'pt=nuvem' if use_cloud else f'traducao={t_trans_total:.0f}ms'} "
        f"speaker={t_spk_ms:.0f}ms "
        f"total={(time.time()-t_start)*1000:.0f}ms",
        flush=True,
    )

    emitted: list[tuple[str, str, str]] = []  # (id, en, pt_na_tela)
    for i, chunk_en in enumerate(chunks):
        shown = chunk_en if use_cloud else local_pts[i]
        if not shown:
            continue
        seg_id = f"seg-{int(seg.started_at * 1000)}-{i}"
        emitted.append((seg_id, chunk_en, shown))
        _emit({
            "type": "subtitle",
            "data": {
                "id": seg_id,
                "sourceText": chunk_en,
                "translatedText": shown,
                "status": "translated",
                "startedAt": seg.started_at,
                "endedAt": seg.ended_at,
                "processingMs": round((time.time() - t_start) * 1000 / max(len(chunks), 1)),
                "speakerId": speaker["id"],
                "speakerColor": speaker["color"],
                "speakerIsNew": speaker["is_new"] and i == 0,
                "willRevise": use_cloud,
            },
        })

    if emitted:
        with _last_emitted_lock:
            _last_emitted_en = result.text

    if use_cloud and emitted:
        _submit_revision(emitted)


# ── revisão assíncrona pela nuvem ─────────────────────────────────────────────
_recent_en: list[str] = []
_recent_lock = threading.Lock()


def _local_fallback_pt(chunks_en: list[str]) -> list[str]:
    """MarianMT só entra se a nuvem falhou E o destino é português."""
    if not _translator or not chunks_en or not is_portuguese_target():
        return []
    try:
        batch = _translator.translate_batch(chunks_en)
        return [
            apply_glossary(to_ptbr(collapse_repeats(tr.translated_text))).strip()
            for tr in batch
        ]
    except Exception as e:
        print(f"[revisao] fallback local falhou: {e}", flush=True)
        return []


def _submit_revision(emitted: list[tuple[str, str, str]]) -> None:
    """Inglês já está na tela. A nuvem (ou o local, se ela falhar) manda o PT."""
    global _revisions_pending
    with _revisions_lock:
        if _revisions_pending >= MAX_PENDING_REVISIONS:
            # fila cheia: ainda assim tenta o local, senão a linha fica em inglês
            pts = _local_fallback_pt([en for _, en, _ in emitted])
            for (seg_id, en, shown), pt in zip(emitted, pts):
                if pt and pt != shown:
                    _emit({
                        "type": "subtitle_revision",
                        "data": {"id": seg_id, "translatedText": pt},
                    })
            return
        _revisions_pending += 1

    with _recent_lock:
        context = list(_recent_en)
        _recent_en.extend(en for _, en, _ in emitted)
        del _recent_en[:-6]

    _revision_executor.submit(_run_revision, emitted, context)


def _run_revision(emitted: list[tuple[str, str, str]], context: list[str]) -> None:
    global _revisions_pending
    try:
        cloud = _cloud
        if cloud is None:
            return
        t0 = time.time()
        chunks_en = [en for _, en, _ in emitted]
        # sem rascunho do MarianMT: o lixo ("gado", "oleoduto") ancorava o LLM
        revised = cloud.translate(chunks_en, drafts_pt=None, context=context)
        _emit({"type": "cost", "data": _cost_state()})

        origem = "nuvem"
        if not revised:
            revised = _local_fallback_pt(chunks_en)
            origem = "local-fallback"

        if not revised:
            return

        changed = 0
        for (seg_id, _, shown), new_pt in zip(emitted, revised):
            new_pt = apply_glossary(collapse_repeats(new_pt)).strip()
            if not new_pt or new_pt == shown:
                continue
            changed += 1
            _emit({
                "type": "subtitle_revision",
                "data": {"id": seg_id, "translatedText": new_pt},
            })
        print(
            f"[revisao] {origem} {time.time()-t0:.2f}s "
            f"{changed}/{len(emitted)} linhas",
            flush=True,
        )
    finally:
        with _revisions_lock:
            _revisions_pending -= 1


# ── callback de segmento (roda na thread de captura — retorna imediatamente) ──
def _on_segment(seg: AudioSegment):
    _segment_executor.submit(_process_segment, seg)


# ── thread de captura ─────────────────────────────────────────────────────────
def _capture_thread():
    global _is_running
    p = pyaudio.PyAudio()
    try:
        dev_idx, device = _find_device(p)
        native_rate = int(device["defaultSampleRate"])
        channels = device["maxInputChannels"]

        stream = p.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=native_rate,
            input=True,
            input_device_index=dev_idx,
            frames_per_buffer=CHUNK,
        )

        _emit({"type": "status", "data": {
            "state": "running",
            "device": device["name"].replace(" [Loopback]", ""),
            "source": _audio_source,
        }})

        partial_buf: list[np.ndarray] = []
        last_partial_at = 0.0
        # Parcial mais frequente, mas NÃO no thread de captura se o worker
        # de segmento já está ocupado (evita fila e GPU dupla).
        PARTIAL_INTERVAL = 0.9
        PARTIAL_MIN_CHUNKS = 8  # ~0.8s de fala @ CHUNK=100ms
        vad_tick = 0

        while _is_running:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.float32)
            audio = _to_mono(audio, channels)
            audio = _resample(audio, native_rate)

            speech, score = _detector.is_speech(audio)
            _voice_buffer.push(audio, speech)

            now = time.time()
            if speech:
                partial_buf.append(audio)
                # partial só se o worker estiver ocioso de verdade — senão o preview
                # disputa a GPU com o segmento final e atrasa a legenda que importa
                if (
                    not _segment_in_flight.is_set()
                    and now - last_partial_at >= PARTIAL_INTERVAL
                    and len(partial_buf) >= PARTIAL_MIN_CHUNKS
                ):
                    # só os últimos ~2s (partial de monólogo inteiro é lento e inútil)
                    tail = partial_buf[-20:]
                    partial_audio = np.concatenate(tail)
                    partial_text = _whisper.transcribe_partial(
                        partial_audio, language=uset.get().whisper_language(),
                    )
                    if partial_text.strip():
                        _emit({
                            "type": "subtitle",
                            "data": {
                                "id": "live",
                                "sourceText": partial_text,
                                "translatedText": None,
                                "status": "partial",
                                "startedAt": now,
                            },
                        })
                    last_partial_at = now
            else:
                if partial_buf:
                    partial_buf = []

            # VAD a cada 3 frames (~300ms) — menos spam no WebSocket
            vad_tick += 1
            if vad_tick % 3 == 0:
                _emit({"type": "vad", "data": {"speech": speech, "score": round(score, 3)}})

        stream.stop_stream()
        stream.close()

    except Exception as e:
        print(f"[ERRO capture_thread] {e}", flush=True)
    finally:
        p.terminate()
        _emit({"type": "status", "data": {"state": "stopped"}})


# ── task asyncio: drena a queue e envia para todos os clientes ────────────────
async def _broadcaster():
    while True:
        msg = await _broadcast_queue.get()
        dead = set()
        for ws in list(_clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        _clients.difference_update(dead)


def _project_root() -> str:
    # server.py -> websocket -> speech_engine -> services -> root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _vram() -> dict:
    """VRAM pelo DRIVER, não pelo alocador do PyTorch.

    torch.cuda.memory_allocated() só enxerga o que o próprio PyTorch alocou — e o
    Whisper roda em CTranslate2, que aloca por fora. Medido nesta máquina: o torch
    reportava 0.00 GB enquanto o driver via 1.09 GB em uso. Como o ponto do perfil
    leve é liberar a placa, um número que subestima em 2.5 GB seria pior que não
    mostrar nada. mem_get_info() vem do driver e conta tudo.
    """
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return {
                "usedGb": round((total - free) / 1024 ** 3, 2),
                "freeGb": round(free / 1024 ** 3, 2),
                "totalGb": round(total / 1024 ** 3, 2),
            }
    except Exception:
        pass
    return {"usedGb": 0.0, "freeGb": 0.0, "totalGb": 0.0}


def _vram_gb() -> float:
    """Uso da placa inteira, em GB — inclui outros apps, que é justamente o que
    interessa para responder 'dá para usar a GPU para outra coisa agora?'."""
    return _vram()["usedGb"]


def _unload_models() -> None:
    """Solta tudo e devolve a VRAM ao sistema.

    del sozinho não basta: o PyTorch guarda os blocos num cache próprio, então
    sem empty_cache() o nvidia-smi continua mostrando a memória ocupada e o
    usuário não consegue usar a placa para outra coisa — que é o motivo inteiro
    de existir o perfil leve.
    """
    global _detector, _whisper, _translator, _voice_buffer, _speaker_tracker, _cloud

    if _cloud is not None:
        # o gasto é da sessão, não do tradutor: guarda o total antes de soltar o
        # objeto, senão trocar de perfil zeraria o contador da UI
        _bank_cloud_cost(_cloud)
        _cloud.close()
    _detector = _whisper = _translator = _voice_buffer = _speaker_tracker = _cloud = None

    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass
    print(f"Modelos descarregados. VRAM em uso: {_vram_gb()} GB", flush=True)


def _cancel_idle_timer() -> None:
    global _idle_timer
    with _idle_lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None


def _schedule_idle_shutdown() -> None:
    """Desligado de propósito: reconectar a UI / F5 derrubava o engine
    e a pessoa via 'não consegue conectar'. A memória só libera no ✕ (/shutdown)."""
    return
    global _idle_timer
    if _shutting_down:
        return
    with _idle_lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
        _idle_timer = threading.Timer(IDLE_SHUTDOWN_S, _idle_shutdown)
        _idle_timer.daemon = True
        _idle_timer.start()
    print(
        f"[shutdown] nenhum cliente — engine encerra em {int(IDLE_SHUTDOWN_S)}s "
        "se a janela não reabrir",
        flush=True,
    )


def _idle_shutdown() -> None:
    if _clients or _shutting_down:
        return
    print("[shutdown] idle — encerrando para devolver RAM/VRAM", flush=True)
    _shutdown_engine(exit_process=True)


def _shutdown_engine(*, exit_process: bool = False) -> None:
    """Para captura, solta modelos, mata os executors. Sem isto o processo
    fica zumbi: ThreadPoolExecutor não é daemon e o uvicorn 'encerra' mas a
    VRAM continua ocupada."""
    global _is_running, _shutting_down, _audio_thread
    if _shutting_down and not exit_process:
        return
    _shutting_down = True
    _cancel_idle_timer()
    print("[shutdown] parando captura e descarregando modelos...", flush=True)

    _is_running = False
    thread = _audio_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.5)
    _audio_thread = None

    for _ in range(25):
        if not _segment_in_flight.is_set():
            break
        time.sleep(0.1)

    try:
        _unload_models()
    except Exception as e:
        print(f"[shutdown] unload: {e}", flush=True)

    for pool in (_segment_executor, _revision_executor):
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    print("[shutdown] pronto.", flush=True)
    if exit_process:
        # dá tempo de a resposta HTTP /shutdown sair antes de morrer
        def _die():
            time.sleep(0.35)
            os._exit(0)

        threading.Thread(target=_die, daemon=True).start()


def _load_models_sync(profile: prof.Profile | None = None) -> None:
    """Carrega o perfil pedido. O HTTP já está no ar com a tela de loading."""
    global _detector, _whisper, _translator, _voice_buffer, _speaker_tracker
    global _models_ready, _models_error, _cloud, _active_profile

    profile = profile or _active_profile
    try:
        print(f"Carregando perfil '{profile.id}' ({profile.label})...", flush=True)
        models_dir = os.path.join(_project_root(), "models")

        _detector = VoiceDetector()
        _whisper = WhisperEngine(
            model_size=profile.whisper_model,
            models_dir=models_dir,
            device=profile.whisper_device,
            compute_type=profile.whisper_compute,
        )
        # O tradutor local carrega SEMPRE, inclusive nos perfis de nuvem: na CPU
        # ele custa 0 de VRAM (não atrapalha liberar a placa) e é o que segura a
        # legenda quando a internet cai.
        _translator = Translator(models_dir=models_dir, device=profile.translator_device)
        _voice_buffer = VoiceBuffer(on_segment=_on_segment)

        _cloud = (
            load_cloud_translator(profile.translator)
            if profile.translator in prof.CLOUD_BACKENDS
            else None
        )

        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            _speaker_tracker = load_tracker(hf_token)
            if not _speaker_tracker:
                print("Speaker tracker nao disponivel — usando heuristica de pausa", flush=True)
        else:
            print("HF_TOKEN nao configurado — identificacao de falantes desativada", flush=True)

        _active_profile = profile
        _models_ready = True
        _models_error = None
        modo = "híbrido (local + nuvem)" if _cloud else "só local"
        print(
            f"Perfil '{profile.id}' pronto — tradução {modo}, VRAM {_vram_gb()} GB.",
            flush=True,
        )
    except Exception as e:
        _models_ready = False
        _models_error = str(e)
        print(f"[ERRO] falha ao carregar perfil '{profile.id}': {e}", flush=True)


def _same_weights(a: prof.Profile, b: prof.Profile) -> bool:
    """gpu ↔ Recomendado (IA) usa o mesmo Whisper. Só liga/desliga o cliente HTTP."""
    return (
        a.whisper_device == b.whisper_device
        and a.whisper_model == b.whisper_model
        and a.whisper_compute == b.whisper_compute
        and a.translator_device == b.translator_device
    )


def _switch_profile_sync(profile_id: str) -> None:
    """Troca de perfil. Se o Whisper já está na memória, não recarrega."""
    global _is_running, _models_ready, _audio_thread, _active_profile, _cloud

    target = prof.resolve(profile_id)
    ok, reason = prof.availability(target)
    if not ok:
        _emit({"type": "profile_error", "data": {"profile": profile_id, "error": reason}})
        return

    # Atalho: Neste PC ↔ Recomendado (IA) — mesmo ouvido, só a tradução muda.
    if _models_ready and _same_weights(_active_profile, target):
        print(f"[perfil] troca rápida {_active_profile.id} → {target.id} (sem recarregar Whisper)", flush=True)
        _active_profile = target
        try:
            _reload_cloud_translator()
        except Exception as e:
            print(f"[perfil] nuvem: {e}", flush=True)
            _cloud = None
        _emit({
            "type": "profile_changed",
            "data": {**_profile_state(), "error": None},
        })
        return

    with _swap_lock:
        was_running = _is_running
        _models_ready = False
        _emit({"type": "status", "data": {"state": "loading", "profile": target.id}})

        # 1. parar a captura e ESPERAR a thread morrer — ela usa _whisper
        _is_running = False
        thread = _audio_thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        _audio_thread = None

        # 2. esperar o segmento em voo terminar (também usa os modelos)
        for _ in range(50):
            if not _segment_in_flight.is_set():
                break
            time.sleep(0.1)

        _unload_models()
        _load_models_sync(target)

        if was_running and _models_ready:
            _is_running = True
            _audio_thread = threading.Thread(target=_capture_thread, daemon=True)
            _audio_thread.start()

    _emit({
        "type": "profile_changed",
        "data": {**_profile_state(), "error": _models_error},
    })


def _reload_cloud_translator() -> None:
    global _cloud
    if _cloud is not None:
        try:
            _bank_cloud_cost(_cloud)
            _cloud.close()
        except Exception:
            pass
        _cloud = None
    if _active_profile.translator in prof.CLOUD_BACKENDS:
        _cloud = load_cloud_translator(_active_profile.translator)


def _apply_settings_sync(msg: dict) -> None:
    """Salva idiomas/chave. Recarrega Whisper só se o idioma de entrada mudou de família."""
    global _models_ready, _active_profile
    _, need_whisper = uset.update_from_ui(msg)
    _active_profile = prof.resolve(_active_profile.id)
    try:
        _reload_cloud_translator()
    except Exception as e:
        print(f"[settings] nao recriei o tradutor da nuvem: {e}", flush=True)

    if need_whisper:
        print("[settings] idioma de entrada mudou — recarregando o ouvido...", flush=True)
        _switch_profile_sync(_active_profile.id)
        return

    _emit({"type": "settings", "data": uset.get().public_dict()})
    _emit({"type": "profiles", "data": _profile_state()})


# ── lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_queue, _loop

    _broadcast_queue = asyncio.Queue()
    _loop = asyncio.get_running_loop()
    broadcaster_task = asyncio.create_task(_broadcaster())
    # Sobe HTTP/UI na hora; modelos em background (evita tela branca / connection refused)
    _loop.run_in_executor(None, _load_models_sync)

    yield

    broadcaster_task.cancel()
    _shutdown_engine(exit_process=False)


app = FastAPI(title="WhisperBridge Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── endpoints ─────────────────────────────────────────────────────────────────
def _profile_state() -> dict:
    return {
        "profile": _active_profile.to_dict(),
        "profiles": prof.list_profiles(),
        "vramGb": _vram_gb(),
        "vram": _vram(),
        "cloud": _cloud is not None,
        "cost": _cost_state(),
        "audio": _audio_state(),
        "settings": uset.get().public_dict(),
    }


@app.get("/health")
def health():
    base = {"timestamp": time.time(), **_profile_state()}
    if _models_error:
        return {"status": "error", "error": _models_error, "running": False, **base}
    if not _models_ready:
        return {"status": "loading", "running": False, **base}
    return {"status": "ok", "running": _is_running, **base}


@app.get("/profiles")
def profiles_endpoint():
    return _profile_state()


@app.post("/shutdown")
def shutdown_endpoint():
    """A UI chama isto ao fechar a janela. Sem o processo Python morrendo,
    Whisper+tradutor ficam na RAM/VRAM e o Windows mostra memória em 100%."""
    threading.Thread(
        target=_shutdown_engine, kwargs={"exit_process": True}, daemon=True,
    ).start()
    return {"status": "shutting_down"}


@app.get("/debug")
def debug():
    thread_alive = _audio_thread.is_alive() if _audio_thread else False
    return {
        "running": _is_running,
        "clients": len(_clients),
        "queue_size": _broadcast_queue.qsize() if _broadcast_queue else -1,
        "thread_alive": thread_alive,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _is_running, _audio_thread, _had_client, _last_emitted_en

    await ws.accept()
    _clients.add(ws)
    _had_client = True
    _cancel_idle_timer()

    await ws.send_json({
        "type": "status",
        "data": {"state": "running" if _is_running else "stopped"},
    })
    await ws.send_json({"type": "profiles", "data": _profile_state()})

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            cmd = msg.get("type")

            if cmd == "start" and not _is_running:
                if not _models_ready:
                    await ws.send_json({
                        "type": "status",
                        "data": {"state": "loading", "error": "Modelos ainda carregando"},
                    })
                    continue
                _is_running = True
                _audio_thread = threading.Thread(target=_capture_thread, daemon=True)
                _audio_thread.start()

            elif cmd == "pause" and _is_running:
                _is_running = False

            elif cmd == "stop":
                _is_running = False

            elif cmd == "ping":
                await ws.send_json({"type": "pong", "ts": time.time()})

            elif cmd == "set_profile":
                target = msg.get("profile")
                if target and target != _active_profile.id:
                    # em executor: descarregar/carregar leva ~15s e travaria o loop
                    asyncio.get_running_loop().run_in_executor(
                        None, _switch_profile_sync, target
                    )

            elif cmd == "set_audio_source":
                src = msg.get("source")
                if src in ("loopback", "mic"):
                    # em executor: troca a fonte parando e recriando a thread de
                    # captura, e o join dela bloquearia o loop do asyncio
                    await asyncio.get_running_loop().run_in_executor(
                        None, _set_audio_source, src, msg.get("index")
                    )
                    await ws.send_json({"type": "audio", "data": _audio_state()})

            elif cmd == "get_profiles":
                await ws.send_json({"type": "profiles", "data": _profile_state()})

            elif cmd == "get_settings":
                await ws.send_json({"type": "settings", "data": uset.get().public_dict()})

            elif cmd == "set_settings":
                asyncio.get_running_loop().run_in_executor(
                    None, _apply_settings_sync, msg,
                )

            elif cmd == "clear_context":
                # sem estado de contexto no tradutor desde a correção da duplicação;
                # o que ainda faz sentido zerar é a galeria de falantes
                if _speaker_tracker:
                    _speaker_tracker.reset()
                with _last_emitted_lock:
                    _last_emitted_en = ""

    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        if not _clients and _had_client and not _shutting_down:
            _schedule_idle_shutdown()


# UI React (dist) servida pelo mesmo host/porta do engine — WebView abre esta URL
# (evita ERR_CONNECTION_REFUSED do protocolo tauri / localhost:vite)
try:
    from fastapi.staticfiles import StaticFiles

    _dist = os.path.join(_project_root(), "apps", "desktop", "dist")
    if os.path.isdir(_dist):
        app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
        print(f"UI estatica: {_dist}", flush=True)
    else:
        print(f"AVISO: dist da UI nao encontrado em {_dist}", flush=True)
except Exception as _e:
    print(f"AVISO: nao montou UI estatica: {_e}", flush=True)


if __name__ == "__main__":
    from shared.ports import ENGINE_HOST, ENGINE_PORT
    uvicorn.run(app, host=ENGINE_HOST, port=ENGINE_PORT, log_level="warning")
