"""Tradução/revisão de legenda por LLM na nuvem.

Por que httpx cru em vez dos SDKs oficiais: (1) httpx já vem com o FastAPI, então
não há dependência nova para instalar na máquina fraca; (2) os SDKs trazem retry
com backoff por padrão, que briga com o orçamento de latência daqui — se a
resposta não chegou em ~2.5s ela não serve mais, e queremos desistir, não tentar
de novo; (3) um caminho de código só atende Gemini e todos os OpenAI-compatíveis.

O valor do LLM aqui NÃO é o sotaque — é que ele recebe contexto e conserta o que
o Whisper errou. "The money is the McMension in Sarasota" o MarianMT traduz
fielmente e vira lixo; o LLM reconhece "mansion" e reescreve coerente.

Falha SEMPRE devolve None. Quem chama mantém a legenda local — nunca é aceitável
uma legenda sumir porque a internet oscilou.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

import httpx

# 2.5s era curto demais: flash-lite em horário cheio estourava e a revisão era
# descartada — a tela ficava só com o MarianMT (que é quem repete palavra).
DEFAULT_TIMEOUT_S = 5.0

# USD por milhão de tokens (entrada, saída). Só entram aqui preços que foram
# conferidos na página oficial do provedor — modelo fora da tabela reporta os
# tokens e deixa o custo como None, porque um número errado na tela é pior que
# nenhum número. LLM_PRICE_IN / LLM_PRICE_OUT no .env sobrescrevem, para o dia
# em que o provedor mudar o preço sem que este arquivo mude junto.
_PRICES: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40),   # ai.google.dev/gemini-api/docs/pricing, 07/08/2026
    "gemini-3.5-flash-lite": (0.30, 2.50),
}


def _price_for(model: str) -> Optional[tuple[float, float]]:
    env_in, env_out = os.getenv("LLM_PRICE_IN"), os.getenv("LLM_PRICE_OUT")
    if env_in and env_out:
        try:
            return float(env_in), float(env_out)
        except ValueError:
            pass
    m = model.lower()
    for key, price in _PRICES.items():
        if m.startswith(key):
            return price
    return None

# Idioma de destino da nuvem. O Whisper daqui é só inglês (.en); a nuvem é que
# pode ir para PT, tailandês, espanhol, etc. MarianMT local só cobre EN→PT.
_LANG_LABELS = {
    "pt": "português do Brasil",
    "pt-br": "português do Brasil",
    "ptbr": "português do Brasil",
    "th": "tailandês",
    "thai": "tailandês",
    "es": "espanhol",
    "fr": "francês",
    "de": "alemão",
    "it": "italiano",
    "ja": "japonês",
    "ko": "coreano",
    "zh": "chinês (simplificado)",
    "en": "inglês",
}


def target_lang() -> str:
    return (os.getenv("TARGET_LANG") or "pt-BR").strip() or "pt-BR"


def target_lang_label() -> str:
    return _LANG_LABELS.get(target_lang().lower(), target_lang())


def is_portuguese_target() -> bool:
    return target_lang().lower().startswith("pt")


def _system_prompt() -> str:
    label = target_lang_label()
    extra = ""
    if is_portuguese_target():
        extra = (
            '- Português do Brasil natural e falado: "você" (nunca "tu"), gerúndio '
            '("está fazendo", nunca "está a fazer"), próclise ("me diz", nunca "diz-me").\n'
        )
    return f"""Você traduz legendas de reunião em tempo real do inglês para {label}.

O texto em inglês veio de reconhecimento automático de fala e PODE CONTER ERROS de
transcrição — palavras trocadas por outras de som parecido (ex.: "cattle" em vez de
"catalog", "work" em vez de "workspace"), nomes próprios errados, frases truncadas.
Use o contexto das falas anteriores para inferir o que a pessoa realmente disse e
traduza o sentido correto, não o erro literal.

Regras:
{extra}- Mantenha em inglês os termos técnicos de trabalho: deploy, pipeline, sprint, backlog,
  pull request, feature flag, rollback, hotfix, dashboard, API, code review, catalog, workspace.
- Uma saída para cada entrada, na mesma ordem. Não junte, não divida, não numere.
- Não explique, não comente, não adicione nada que não foi dito.
- Nunca repita a mesma palavra ou o mesmo trecho em loop. Se o inglês vier repetido, traduza uma vez só.
- Se um trecho for curto ou ambíguo demais, traduza literalmente em vez de inventar.

Responda APENAS com um array JSON de strings, sem cercas de código."""


_SYSTEM = _system_prompt()  # default no import; CloudTranslator relê se o .env mudar


def _build_user(chunks_en: list[str], drafts_pt: Optional[list[str]], context: Optional[list[str]]) -> str:
    parts: list[str] = []
    if context:
        parts.append("Falas anteriores (só para contexto, não traduza):")
        parts.extend(f"- {c}" for c in context[-4:])
        parts.append("")

    if drafts_pt:
        parts.append("Revise estas traduções automáticas. Corrija sentido, erros de")
        parts.append("transcrição e português europeu:")
        parts.append("")
        for en, pt in zip(chunks_en, drafts_pt):
            parts.append(f"EN: {en}")
            parts.append(f"PT: {pt}")
            parts.append("")
    else:
        parts.append(f"Traduza para {target_lang_label()}:")
        parts.append("")
        parts.extend(f"EN: {c}" for c in chunks_en)
        parts.append("")

    parts.append(f"Responda com um array JSON de exatamente {len(chunks_en)} strings.")
    return "\n".join(parts)


def _parse(raw: str, expected: int) -> Optional[list[str]]:
    """Extrai o array JSON. Contagem errada = descarta tudo — meia legenda
    revisada e meia não é pior que nenhuma revisão."""
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(data, list) or len(data) != expected:
        return None
    if not all(isinstance(item, str) and item.strip() for item in data):
        return None
    return [item.strip() for item in data]


class CloudTranslator:
    """Base. Subclasses implementam _request()."""

    name = "cloud"

    def __init__(self, timeout_s: float | None = None):
        self.timeout_s = timeout_s or float(os.getenv("LLM_TIMEOUT_S", DEFAULT_TIMEOUT_S))
        self._client = httpx.Client(timeout=self.timeout_s)
        self._fail_streak = 0
        self._last_report = 0.0
        # contadores de consumo — alimentados por _note_usage() dentro de _request()
        self.model = ""
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def _request(self, system: str, user: str) -> str:  # pragma: no cover - abstrato
        raise NotImplementedError

    def _note_usage(self, tokens_in: int, tokens_out: int) -> None:
        """Contabiliza DENTRO de _request, não no translate(): a chamada já foi
        cobrada mesmo quando a resposta vem num formato que não conseguimos usar."""
        self.calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def stats(self) -> dict:
        price = _price_for(self.model)
        usd = None
        if price:
            usd = (self.tokens_in / 1e6) * price[0] + (self.tokens_out / 1e6) * price[1]
        return {
            "model": self.model,
            "calls": self.calls,
            "tokensIn": self.tokens_in,
            "tokensOut": self.tokens_out,
            "usd": usd,                       # None = preço desconhecido para este modelo
            "pricedPerMillion": price,        # (entrada, saída) ou None
        }

    def translate(
        self,
        chunks_en: list[str],
        drafts_pt: Optional[list[str]] = None,
        context: Optional[list[str]] = None,
    ) -> Optional[list[str]]:
        if not chunks_en:
            return None
        try:
            raw = self._request(_system_prompt(), _build_user(chunks_en, drafts_pt, context))
            out = _parse(raw, len(chunks_en))
            if out is None:
                self._note_failure("resposta em formato inesperado")
                return None
            self._fail_streak = 0
            return out
        except httpx.TimeoutException:
            self._note_failure(f"timeout ({self.timeout_s}s)")
            return None
        except Exception as e:
            self._note_failure(f"{type(e).__name__}: {e}")
            return None

    def _note_failure(self, reason: str) -> None:
        """Loga com throttle. Sem isso, internet caída vira milhares de linhas."""
        self._fail_streak += 1
        now = time.time()
        if self._fail_streak == 1 or now - self._last_report > 30:
            print(
                f"[{self.name}] falhou ({self._fail_streak}x): {reason} "
                f"— mantendo a legenda local",
                flush=True,
            )
            self._last_report = now

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


class GeminiTranslator(CloudTranslator):
    name = "gemini"

    def __init__(self, timeout_s: float | None = None):
        super().__init__(timeout_s)
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada no .env")
        # flash-lite é o encaixe: tarefa simples, volume alto, latência crítica.
        # gemini-3.6-flash se quiser mais qualidade por ~5x o preço.
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        print(f"Tradutor Gemini ({self.model}) pronto.", flush=True)

    def _request(self, system: str, user: str) -> str:
        resp = self._client.post(
            self.url,
            headers={"x-goog-api-key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        u = data.get("usageMetadata") or {}
        # thoughtsTokenCount é cobrado como saída. No flash-lite vem 0-2, mas num
        # modelo de raciocínio ele domina a conta — por isso entra aqui.
        self._note_usage(
            u.get("promptTokenCount", 0),
            u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0),
        )
        return data["candidates"][0]["content"]["parts"][0]["text"]


class OpenAICompatTranslator(CloudTranslator):
    """Cobre GPT, DeepSeek, Kimi e MiniMax — todos expõem /chat/completions."""

    name = "openai-compat"

    def __init__(self, timeout_s: float | None = None):
        super().__init__(timeout_s)
        self.api_key = os.getenv("LLM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY não configurada no .env")
        base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base}/chat/completions"
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        print(f"Tradutor {self.model} via {base} pronto.", flush=True)

    def _request(self, system: str, user: str) -> str:
        resp = self._client.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 800,
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        u = data.get("usage") or {}
        self._note_usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        return data["choices"][0]["message"]["content"]


def load_cloud_translator(backend: str) -> Optional[CloudTranslator]:
    """Nunca levanta: perfil de nuvem sem chave deve degradar para o local,
    não impedir o engine de subir."""
    try:
        if backend == "gemini":
            return GeminiTranslator()
        if backend == "openai-compat":
            return OpenAICompatTranslator()
    except Exception as e:
        print(f"[nuvem] indisponível: {e}", flush=True)
    return None
