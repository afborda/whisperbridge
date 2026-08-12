# 05 — Motor de Tradução (Helsinki-NLP)

Traduz o texto transcrito de inglês para português localmente, sem nenhuma API externa.

---

## Modelo escolhido

**Helsinki-NLP/opus-mt-tc-big-en-pt**

- Treinado especificamente para inglês → português
- ~300 MB no disco
- Roda bem em CPU ou GPU
- Qualidade superior aos modelos genéricos para esse par de idiomas
- Suporta português do Brasil e europeu

---

## 5.1 Instalação

```powershell
pip install transformers sentencepiece sacremoses
```

---

## 5.2 Download do modelo

```python
from transformers import MarianMTModel, MarianTokenizer

MODEL_NAME = "Helsinki-NLP/opus-mt-tc-big-en-pt"

print("Baixando modelo de tradução...")
tokenizer = MarianTokenizer.from_pretrained(MODEL_NAME, cache_dir="./models")
model = MarianMTModel.from_pretrained(MODEL_NAME, cache_dir="./models")
print("Modelo de tradução baixado")
```

---

## 5.3 Motor de tradução

```python
# services/speech-engine/translation/translator.py

import torch
from transformers import MarianMTModel, MarianTokenizer
from dataclasses import dataclass
import time

MODEL_NAME = "Helsinki-NLP/opus-mt-tc-big-en-pt"

@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    processing_time_s: float

class Translator:
    def __init__(self, models_dir: str = "./models"):
        print("Carregando modelo de tradução...")
        start = time.time()

        self.tokenizer = MarianTokenizer.from_pretrained(
            MODEL_NAME, cache_dir=models_dir
        )
        self.model = MarianMTModel.from_pretrained(
            MODEL_NAME, cache_dir=models_dir
        )

        if torch.cuda.is_available():
            self.model = self.model.cuda()
            self.device = "cuda"
        else:
            self.device = "cpu"

        self.model.eval()

        load_time = time.time() - start
        print(f"Tradutor carregado em {load_time:.1f}s ({self.device})")

    def translate(self, text: str, context: list[str] | None = None) -> TranslationResult:
        start = time.time()

        # Adiciona contexto das frases anteriores para melhorar coerência
        if context:
            input_text = " ".join(context[-2:]) + " " + text
        else:
            input_text = text

        inputs = self.tokenizer(
            [input_text],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )

        if self.device == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                num_beams=4,
                max_length=512,
                early_stopping=True,
            )

        translated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        processing_time = time.time() - start

        return TranslationResult(
            source_text=text,
            translated_text=translated,
            processing_time_s=processing_time,
        )
```

---

## 5.4 Glossário personalizado

Termos técnicos que não devem ser traduzidos ou precisam de tradução específica.

```python
# services/speech-engine/translation/glossary.py

GLOSSARY = {
    "dashboard": "dashboard",
    "deployment": "implantação",
    "deploy": "deploy",
    "pull request": "pull request",
    "PR": "PR",
    "data pipeline": "pipeline de dados",
    "pipeline": "pipeline",
    "BFF": "BFF",
    "Databricks": "Databricks",
    "widget": "widget",
    "success plan": "plano de sucesso",
    "sprint": "sprint",
    "backlog": "backlog",
    "stakeholder": "stakeholder",
    "roadmap": "roadmap",
    "feature flag": "feature flag",
    "rollback": "rollback",
    "hotfix": "hotfix",
    "on call": "de plantão",
    "on-call": "de plantão",
}

def apply_glossary(text: str) -> str:
    result = text
    for en, pt in GLOSSARY.items():
        # substituição case-insensitive
        import re
        result = re.sub(re.escape(en), pt, result, flags=re.IGNORECASE)
    return result
```

---

## 5.5 Teste de tradução — Fase 2

```python
# services/speech-engine/translation/test_translation.py

from translator import Translator
from glossary import apply_glossary

translator = Translator()

test_phrases = [
    "We need to review the dashboard before the deploy.",
    "The pull request is ready for code review.",
    "Let's discuss the roadmap for next sprint.",
    "The data pipeline is failing in production.",
    "We should add a feature flag for this change.",
    "The on-call engineer will handle the hotfix.",
]

context = []
for phrase in test_phrases:
    result = translator.translate(phrase, context=context)
    translated = apply_glossary(result.translated_text)
    print(f"[EN] {phrase}")
    print(f"[PT] {translated}")
    print(f"     ({result.processing_time_s:.2f}s)\n")
    context.append(phrase)
```

```powershell
python services/speech-engine/translation/test_translation.py
```

Saída esperada:

```
[EN] We need to review the dashboard before the deploy.
[PT] Precisamos revisar o dashboard antes do deploy.
     (0.12s)

[EN] The pull request is ready for code review.
[PT] O pull request está pronto para revisão de código.
     (0.09s)
```

---

## 5.6 Métricas esperadas

| Métrica | Valor esperado |
|---|---|
| Primeira tradução (modelo carregando) | ~3–5s |
| Tradução subsequente (frase de ~10 palavras) | ~80–150ms |
| Tradução subsequente (frase de ~30 palavras) | ~150–300ms |
| VRAM usada pelo modelo | ~300 MB |

---

**Próximo passo:** [06-realtime-pipeline.md](./06-realtime-pipeline.md)
