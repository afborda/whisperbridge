"""Preferências do usuário: idiomas + chave da IA.

Ficam em user-settings.json na raiz (gitignore). A chave do .env continua
válida — a UI só grava aqui o que a pessoa colar em Configurações.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

SETTINGS_NAME = "user-settings.json"

LANGUAGES: list[dict[str, str]] = [
    {"id": "en", "label": "Inglês"},
    {"id": "pt", "label": "Português"},
    {"id": "es", "label": "Espanhol"},
    {"id": "th", "label": "Tailandês"},
    {"id": "fr", "label": "Francês"},
    {"id": "de", "label": "Alemão"},
    {"id": "it", "label": "Italiano"},
    {"id": "ja", "label": "Japonês"},
    {"id": "ko", "label": "Coreano"},
    {"id": "zh", "label": "Chinês"},
    {"id": "auto", "label": "Detectar automático"},
]

_VALID_LANG = {x["id"] for x in LANGUAGES}
_VALID_BACKEND = {"gemini", "openai-compat"}


def _root() -> str:
    # src/whisperbridge/config/settings.py -> raiz do repo
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _path() -> str:
    return os.path.join(_root(), SETTINGS_NAME)


@dataclass
class UserSettings:
    source_lang: str = "en"
    target_lang: str = "pt-BR"
    backend: str = "gemini"
    gemini_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    llm_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    def public_dict(self) -> dict:
        """O que a UI pode ver — nunca devolve a chave inteira."""
        return {
            "sourceLang": self.source_lang,
            "targetLang": self.target_lang,
            "backend": self.backend,
            "geminiModel": self.gemini_model,
            "llmBaseUrl": self.llm_base_url,
            "llmModel": self.llm_model,
            "hasGeminiKey": bool(self.effective_gemini_key()),
            "hasLlmKey": bool(self.effective_llm_key()),
            "languages": LANGUAGES,
        }

    def effective_gemini_key(self) -> str:
        return (self.gemini_key or os.getenv("GEMINI_API_KEY") or "").strip()

    def effective_llm_key(self) -> str:
        return (self.llm_key or os.getenv("LLM_API_KEY") or "").strip()

    def whisper_language(self) -> str | None:
        """Código que o faster-whisper entende, ou None = detectar."""
        s = (self.source_lang or "en").lower()
        if s in ("auto", ""):
            return None
        if s.startswith("pt"):
            return "pt"
        if s.startswith("zh"):
            return "zh"
        return s.split("-")[0]


_cache: UserSettings | None = None


def get() -> UserSettings:
    global _cache
    if _cache is None:
        _cache = load()
    return _cache


def load() -> UserSettings:
    global _cache
    data = UserSettings()
    # semente do .env na primeira vez
    env_backend = (os.getenv("TRANSLATOR_BACKEND") or "").strip().lower()
    if env_backend in _VALID_BACKEND:
        data.backend = env_backend
    env_target = (os.getenv("TARGET_LANG") or "").strip()
    if env_target:
        data.target_lang = env_target
    path = _path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            data = _merge(data, raw)
    apply_environ(data)
    _cache = data
    return data


def _merge(base: UserSettings, raw: dict) -> UserSettings:
    d = asdict(base)
    mapping = {
        "source_lang": "source_lang",
        "sourceLang": "source_lang",
        "target_lang": "target_lang",
        "targetLang": "target_lang",
        "backend": "backend",
        "gemini_key": "gemini_key",
        "geminiKey": "gemini_key",
        "gemini_model": "gemini_model",
        "geminiModel": "gemini_model",
        "llm_key": "llm_key",
        "llmKey": "llm_key",
        "llm_base_url": "llm_base_url",
        "llmBaseUrl": "llm_base_url",
        "llm_model": "llm_model",
        "llmModel": "llm_model",
    }
    for src, dst in mapping.items():
        if src in raw and raw[src] is not None:
            d[dst] = raw[src]
    src = str(d["source_lang"] or "en").lower()
    if src not in _VALID_LANG:
        src = "en"
    d["source_lang"] = src
    tgt = str(d["target_lang"] or "pt-BR")
    d["target_lang"] = tgt
    if str(d["backend"]) not in _VALID_BACKEND:
        d["backend"] = "gemini"
    return UserSettings(**d)


def save(data: UserSettings) -> None:
    global _cache
    payload = asdict(data)
    path = _path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    _cache = data
    apply_environ(data)


def apply_environ(data: UserSettings) -> None:
    os.environ["TARGET_LANG"] = data.target_lang
    os.environ["TRANSLATOR_BACKEND"] = data.backend
    if data.gemini_key:
        os.environ["GEMINI_API_KEY"] = data.gemini_key
    if data.gemini_model:
        os.environ["GEMINI_MODEL"] = data.gemini_model
    if data.llm_key:
        os.environ["LLM_API_KEY"] = data.llm_key
    if data.llm_base_url:
        os.environ["LLM_BASE_URL"] = data.llm_base_url
    if data.llm_model:
        os.environ["LLM_MODEL"] = data.llm_model


def update_from_ui(msg: dict) -> tuple[UserSettings, bool]:
    """Aplica o que a UI mandou. Retorna (settings, precisa_recarregar_whisper)."""
    cur = get()
    old_source = cur.source_lang
    d = asdict(cur)

    if "sourceLang" in msg and msg["sourceLang"]:
        s = str(msg["sourceLang"]).lower()
        if s in _VALID_LANG:
            d["source_lang"] = s
    if "targetLang" in msg and msg["targetLang"]:
        d["target_lang"] = str(msg["targetLang"])
    if msg.get("backend") in _VALID_BACKEND:
        d["backend"] = msg["backend"]
    if msg.get("geminiModel"):
        d["gemini_model"] = str(msg["geminiModel"]).strip()
    if msg.get("llmBaseUrl"):
        d["llm_base_url"] = str(msg["llmBaseUrl"]).strip()
    if msg.get("llmModel"):
        d["llm_model"] = str(msg["llmModel"]).strip()
    # chave só atualiza se a pessoa colou uma nova (não reenvia a antiga)
    key = (msg.get("apiKey") or "").strip()
    if key:
        if d["backend"] == "gemini":
            d["gemini_key"] = key
        else:
            d["llm_key"] = key

    nxt = UserSettings(**d)
    save(nxt)
    need_whisper = _whisper_family(old_source) != _whisper_family(nxt.source_lang)
    return nxt, need_whisper


def _whisper_family(source_lang: str) -> str:
    return "en" if (source_lang or "en") in ("en", "en-us") else "multi"


def whisper_model_for(base_model: str, source_lang: str | None = None) -> str:
    """medium.en / small.en só servem para inglês. Outro idioma → medium / small."""
    src = source_lang if source_lang is not None else get().source_lang
    model = base_model
    if _whisper_family(src) == "en":
        if model in ("medium", "small"):
            return model + ".en"
        return model
    return model.replace(".en", "")
