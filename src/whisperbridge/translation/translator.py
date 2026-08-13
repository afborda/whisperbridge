import time
import torch
from dataclasses import dataclass
from transformers import MarianMTModel, MarianTokenizer
from ..transcription.whisper_engine import collapse_repeats

MODEL_NAME = "Helsinki-NLP/opus-mt-tc-big-en-pt"


@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    processing_time_s: float


class Translator:
    def __init__(self, models_dir: str = "./models", device: str | None = None):
        print("Carregando tradutor Helsinki EN->PT...", end=" ", flush=True)
        t0 = time.time()

        self.tokenizer = MarianTokenizer.from_pretrained(MODEL_NAME, cache_dir=models_dir)
        self.model = MarianMTModel.from_pretrained(MODEL_NAME, cache_dir=models_dir)

        # o perfil manda; sem perfil, cai no que a máquina tiver
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device if (device != "cuda" or torch.cuda.is_available()) else "cpu"
        self.model = self.model.to(self.device)
        self.model.eval()

        print(f"OK ({time.time() - t0:.1f}s, {self.device})")

    def translate(self, text: str) -> TranslationResult:
        results = self.translate_batch([text])
        return results[0]

    def translate_batch(self, texts: list[str]) -> list[TranslationResult]:
        """Traduz todos os textos em uma única chamada à GPU — muito mais rápido que N chamadas.

        NÃO existe prefixo de contexto aqui, de propósito. A versão anterior colava as
        2 frases anteriores na entrada do primeiro item para "dar contexto", mas o
        MarianMT é sentence-level: ele não sabe o que é contexto e o que é texto novo,
        e o decode devolvia contexto + texto novo fundidos. O resultado era a legenda
        repetindo as duas linhas anteriores a cada nova linha (janela deslizante).
        Se um dia entrar um modelo com prompt de verdade (T5/NLLB), o contexto volta lá.
        """
        if not texts:
            return []

        t0 = time.time()

        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256,  # chunks curtos — 256 é suficiente
        ).to(self.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                num_beams=4,
                max_length=256,
                early_stopping=True,
            )

        elapsed = time.time() - t0

        return [
            TranslationResult(
                source_text=texts[i],
                translated_text=collapse_repeats(
                    self.tokenizer.decode(ids, skip_special_tokens=True)
                ),
                processing_time_s=elapsed / len(texts),  # tempo médio por item
            )
            for i, ids in enumerate(output_ids)
        ]
