import os
import re
import time
import numpy as np
from dataclasses import dataclass
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000

# ── Filtros de qualidade ──────────────────────────────────────────────────────
# O faster-whisper usa estes limites internamente para decidir se tenta de novo com
# temperatura maior, mas devolve o resultado mesmo assim quando todas as tentativas
# falham. Aqui aplicamos de novo, pós-hoc, para JOGAR FORA o segmento ruim.
MIN_AVG_LOGPROB = -1.15       # um pouco mais permissivo: reunião comprimida cai a confiança
MAX_NO_SPEECH_PROB = 0.7      # 0.6 descartava fala baixa de headset / loopback
MAX_COMPRESSION_RATIO = 2.2   # acima disso = texto repetitivo em loop
MIN_RMS_AFTER_GAIN = 0.004    # depois do AGC ainda é silêncio → não gasta Whisper

# RMS alvo depois do ganho. Áudio de reunião no loopback costuma chegar ~0.01–0.03;
# o Whisper foi treinado perto de 0.1. Sem isso ele "precisa de pronúncia perfeita".
TARGET_RMS = 0.10
MAX_GAIN = 16.0

# Frases que o Whisper INVENTA em silêncio/ruído — viés do corpus de legendas de
# YouTube com que foi treinado. Ele as produz com alta confiança, então nenhum
# threshold pega: só blocklist resolve.
# Comparadas com o segmento INTEIRO normalizado, nunca como substring — assim um
# "thank you" dito de verdade no meio de uma frase real continua aparecendo.
_HALLUCINATIONS = {
    "thanks for watching", "thank you for watching", "thanks for watching this video",
    "please subscribe", "subscribe to my channel", "like and subscribe",
    "dont forget to subscribe", "see you next time", "see you in the next video",
    "thank you", "thanks", "thank you very much", "thank you so much",
    "bye", "bye bye", "goodbye", "you", "the end",
    "subtitles by the amaraorg community", "transcription by castingwords",
}

_norm_re = re.compile(r"[^a-z0-9' ]+")


def _is_hallucination(text: str) -> bool:
    norm = " ".join(_norm_re.sub(" ", text.lower()).split())
    return norm in _HALLUCINATIONS


def normalize_gain(audio: np.ndarray) -> np.ndarray:
    """AGC simples: reunião no loopback chega baixa demais para o Whisper."""
    if audio is None or len(audio) == 0:
        return audio
    x = audio.astype(np.float32, copy=False)
    rms = float(np.sqrt(np.mean(np.square(x))))
    if rms < 1e-7:
        return x
    gain = min(TARGET_RMS / rms, MAX_GAIN)
    if gain <= 1.05:
        return x
    return np.clip(x * gain, -1.0, 1.0)


def collapse_repeats(text: str) -> str:
    """Tira loop do tipo 'I think I think I think' e 'hello hello hello'.

    O Whisper (e às vezes o MarianMT) entra em loop em áudio ruim. Sem isso a
    legenda vira a mesma palavra/frase repetida até encher a linha.
    """
    text = " ".join((text or "").split())
    if not text:
        return text

    words = text.split()
    dedup: list[str] = []
    for w in words:
        if not dedup or w.lower() != dedup[-1].lower():
            dedup.append(w)
    words = dedup

    max_n = min(12, max(1, len(words) // 2))
    for n in range(1, max_n + 1):
        out: list[str] = []
        i = 0
        while i < len(words):
            gram = [w.lower() for w in words[i:i + n]]
            if len(gram) < n:
                out.extend(words[i:])
                break
            j = i + n
            while j + n <= len(words) and [w.lower() for w in words[j:j + n]] == gram:
                j += n
            out.extend(words[i:i + n])
            i = j
        words = out

    return " ".join(words)


def is_degenerate(text: str) -> bool:
    """True se o texto é loop/lixo e não deve ir para a tela nem para o tradutor."""
    words = (text or "").split()
    if len(words) < 6:
        return False
    unique = {w.lower() for w in words}
    return len(unique) / len(words) < 0.35


def similar_enough(a: str, b: str) -> bool:
    """Detecta a mesma fala emitida de novo no segmento seguinte."""
    na = " ".join(_norm_re.sub(" ", (a or "").lower()).split())
    nb = " ".join(_norm_re.sub(" ", (b or "").lower()).split())
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        return len(shorter) >= 12 and len(shorter) / len(longer) >= 0.72
    return False


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_s: float
    processing_time_s: float
    realtime_factor: float   # >1 = mais rapido que tempo real


class WhisperEngine:
    def __init__(
        self,
        model_size: str = "medium.en",
        models_dir: str = "./models",
        device: str = "cuda",
        compute_type: str | None = None,
        cpu_threads: int = 4,
    ):
        # float16 só existe na GPU; int8 é o que torna a CPU viável
        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"

        print(f"Carregando Whisper {model_size} ({device}/{compute_type})...", end=" ", flush=True)
        t0 = time.time()

        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=models_dir,
            num_workers=2,
            # na CPU o modelo é o gargalo — usa todos os núcleos disponíveis
            cpu_threads=cpu_threads if device == "cuda" else max(4, (os.cpu_count() or 8) - 2),
        )
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        print(f"OK ({time.time() - t0:.1f}s)")

    def transcribe(self, audio: np.ndarray, language: str | None = "en") -> TranscriptionResult:
        t0 = time.time()
        duration_s = len(audio) / SAMPLE_RATE if audio is not None else 0.0
        empty = TranscriptionResult(
            text="", language=language, duration_s=duration_s,
            processing_time_s=0.0, realtime_factor=0.0,
        )
        if audio is None or len(audio) == 0:
            return empty

        audio = normalize_gain(audio)
        rms = float(np.sqrt(np.mean(np.square(audio))))
        if rms < MIN_RMS_AFTER_GAIN:
            return empty

        kw = dict(
            beam_size=3,
            best_of=3,
            temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            compression_ratio_threshold=MAX_COMPRESSION_RATIO,
            log_prob_threshold=MIN_AVG_LOGPROB,
            no_speech_threshold=MAX_NO_SPEECH_PROB,
            condition_on_previous_text=False,
            vad_filter=False,
            word_timestamps=False,
            without_timestamps=True,
        )
        if language:
            kw["language"] = language
        if language == "en":
            kw["initial_prompt"] = "English conversation from a live video meeting."
        segments, info = self.model.transcribe(audio, **kw)

        kept = [
            s for s in segments
            if s.avg_logprob > MIN_AVG_LOGPROB
            and s.no_speech_prob < MAX_NO_SPEECH_PROB
            and s.compression_ratio < MAX_COMPRESSION_RATIO
            and not _is_hallucination(s.text)
        ]

        text = collapse_repeats(" ".join(s.text.strip() for s in kept).strip())
        if _is_hallucination(text) or is_degenerate(text):
            text = ""
        elapsed = time.time() - t0

        return TranscriptionResult(
            text=text,
            language=info.language,
            duration_s=duration_s,
            processing_time_s=elapsed,
            realtime_factor=duration_s / elapsed if elapsed > 0 else 0,
        )

    def transcribe_partial(self, audio: np.ndarray, language: str | None = "en") -> str:
        """Versao rapida para resultado parcial enquanto a pessoa ainda fala."""
        if audio is None or len(audio) == 0:
            return ""
        audio = normalize_gain(audio)
        kw = dict(
            beam_size=1,
            temperature=0.0,
            no_speech_threshold=MAX_NO_SPEECH_PROB,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        if language:
            kw["language"] = language
        segments, _ = self.model.transcribe(audio, **kw)
        text = collapse_repeats(" ".join(
            s.text.strip() for s in segments
            if s.no_speech_prob < MAX_NO_SPEECH_PROB and not _is_hallucination(s.text)
        ).strip())
        if _is_hallucination(text) or is_degenerate(text):
            return ""
        return text
