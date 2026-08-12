"""Perfis de execução do WhisperBridge.

O ponto do perfil não é só "onde traduz" — é O QUE SOBE NA MEMÓRIA. Quem come a
GPU é o Whisper (~2.5 GB em medium.en float16), não o tradutor (0.44 GB). Então
mandar só a tradução para a nuvem NÃO libera a placa; para isso o Whisper precisa
sair da GPU também. Daí os perfis serem combinações das duas coisas.

Transcrição nunca vai para a nuvem, de propósito: medido nesta máquina, o Whisper
local resolve um segmento de 6s em ~336ms, enquanto só a ida e volta de rede para
qualquer API de transcrição custa 400-900ms. Na GPU a nuvem seria 2-5x mais lenta,
custaria por minuto e mandaria o áudio para fora. A nuvem só entra na tradução,
onde ela ganha de verdade (contexto, e conserta erro do Whisper).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict

# ── backends de tradução ──────────────────────────────────────────────────────
LOCAL = "local"
GEMINI = "gemini"
OPENAI_COMPAT = "openai-compat"  # GPT, DeepSeek, Kimi, MiniMax — todos falam o mesmo dialeto

CLOUD_BACKENDS = {GEMINI, OPENAI_COMPAT}


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    description: str
    whisper_device: str       # "cuda" | "cpu"
    whisper_model: str        # medium.en na GPU; small.en na CPU
    whisper_compute: str      # float16 na GPU; int8 na CPU
    translator: str           # LOCAL | GEMINI | OPENAI_COMPAT
    translator_device: str    # onde roda o MarianMT quando translator == LOCAL
    approx_vram_gb: float
    needs_key: bool
    needs_cuda: bool

    def to_dict(self) -> dict:
        return asdict(self)


PROFILES: dict[str, Profile] = {
    "gpu": Profile(
        id="gpu",
        label="Neste PC (rápido)",
        description="Ouve e traduz neste computador. Sem internet. Só inglês → português.",
        whisper_device="cuda",
        whisper_model="medium.en",
        whisper_compute="float16",
        translator=LOCAL,
        translator_device="cuda",
        approx_vram_gb=3.2,
        needs_key=False,
        needs_cuda=True,
    ),
    "gpu-nuvem": Profile(
        id="gpu-nuvem",
        label="Recomendado (IA)",
        description="Ouve neste PC e traduz com a sua IA. Melhor qualidade. Você escolhe os idiomas.",
        whisper_device="cuda",
        whisper_model="medium.en",
        whisper_compute="float16",
        translator=OPENAI_COMPAT,  # sobrescrito pelo settings/env (gemini etc.)
        translator_device="cuda",
        approx_vram_gb=2.8,
        needs_key=True,
        needs_cuda=True,
    ),
    "leve": Profile(
        id="leve",
        label="IA sem placa de vídeo",
        description="Libera o jogo ou outro app. Ouvir fica mais lento. Traduz com a IA.",
        whisper_device="cpu",
        whisper_model="small.en",
        whisper_compute="int8",
        translator=OPENAI_COMPAT,
        translator_device="cpu",
        approx_vram_gb=0.0,
        needs_key=True,
        needs_cuda=False,
    ),
    "leve-offline": Profile(
        id="leve-offline",
        label="Neste PC (sem internet)",
        description="Tudo no processador. Mais lento, funciona offline. Só inglês → português.",
        whisper_device="cpu",
        whisper_model="small.en",
        whisper_compute="int8",
        translator=LOCAL,
        translator_device="cpu",
        approx_vram_gb=0.0,
        needs_key=False,
        needs_cuda=False,
    ),
}

DEFAULT_PROFILE = "gpu"


def _cloud_backend_from_env() -> str:
    """Qual provedor de nuvem usar quando o perfil pede nuvem."""
    raw = (os.getenv("TRANSLATOR_BACKEND") or "").strip().lower()
    return raw if raw in CLOUD_BACKENDS else OPENAI_COMPAT


def resolve(profile_id: str | None = None) -> Profile:
    """Resolve o perfil pedido, aplicando o provedor de nuvem e o idioma de entrada."""
    from shared.user_settings import get as get_settings, whisper_model_for

    pid = (profile_id or os.getenv("PROFILE") or DEFAULT_PROFILE).strip().lower()
    profile = PROFILES.get(pid) or PROFILES[DEFAULT_PROFILE]
    fields = profile.to_dict()

    if profile.translator in CLOUD_BACKENDS:
        chosen = _cloud_backend_from_env()
        fields["translator"] = chosen

    fields["whisper_model"] = whisper_model_for(profile.whisper_model, get_settings().source_lang)
    return Profile(**fields)


def has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def has_cloud_key(backend: str) -> bool:
    from shared.user_settings import get as get_settings

    s = get_settings()
    if backend == GEMINI:
        return bool(s.effective_gemini_key())
    if backend == OPENAI_COMPAT:
        return bool(s.effective_llm_key())
    return True


def availability(profile: Profile) -> tuple[bool, str]:
    """(pode_usar, motivo). Sem chave a pessoa AINDA pode escolher o modo IA —
    a UI abre o campo da key. Só bloqueia se faltar GPU."""
    if profile.needs_cuda and not has_cuda():
        return False, "Sem placa NVIDIA nesta máquina"
    return True, ""


def list_profiles() -> list[dict]:
    out = []
    for p in PROFILES.values():
        resolved = resolve(p.id)
        ok, reason = availability(resolved)
        setup = resolved.needs_key and not has_cloud_key(resolved.translator)
        out.append({
            **resolved.to_dict(),
            "available": ok,
            "unavailable_reason": reason,
            "setupNeeded": setup,
        })
    return out
