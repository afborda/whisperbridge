"""Normaliza a saída do tradutor de português europeu para português do Brasil.

Por que aqui e não trocando o modelo: o `opus-mt-tc-big-en-pt` puxa para pt-PT, mas
é o mais FIEL ao sentido que testamos (o `unicamp-dl/translation-en-pt-t5` é mais
brasileiro e 2.4x mais lento, porém inverte sentido — "have a little faith" virou
"tem pouca fé" e "We need you" perdeu o "you"). Sotaque se conserta com regex a
custo ~0ms; erro de significado, não. Números da comparação no CLAUDE.md.
"""

import re

_GERUNDIO = {"ar": "ando", "er": "endo", "ir": "indo"}

# "estamos a falar" -> "estamos falando". Só com o verbo ESTAR: "começar a fazer" e
# "continuar a fazer" também são corretos no Brasil e não podem ser mexidos.
_RE_GERUNDIO = re.compile(
    r"\b(est(?:ou|ás|as|á|a|amos|ão|ava|avas|ávamos|avam)|estive|esteve|estivemos)"
    r"\s+a\s+([a-zà-ÿ]+?)(ar|er|ir)\b",
    re.IGNORECASE,
)

# Ênclise -> próclise: "pedir-me" -> "me pedir", "Digo-te" -> "Te digo".
# Restringir aos pronomes átonos é o que torna isto seguro: palavras compostas
# reais (beija-flor, segunda-feira, guarda-chuva) nunca terminam nesses sufixos.
#
# "lhe"/"lhes" ficam DE FORA de propósito. Com eles a próclise produz coisa pior
# que o original: "Diz-lhe que vou" virava "Lhe diz que vou", que não é português
# de lugar nenhum. O certo em pt-BR seria "Diga a ele", mas isso exige saber o
# gênero do referente — então preferimos deixar a ênclise, que ao menos é correta.
_RE_ENCLISE = re.compile(r"\b([a-zà-ÿ]+)-(me|te|nos)\b", re.IGNORECASE)

# Trocas palavra a palavra. Chave em minúscula; a capitalização do original é mantida.
_TROCAS: dict[str, str] = {
    # 2ª pessoa (tu) -> você
    "tu": "você", "ti": "você", "contigo": "com você", "teu": "seu", "teus": "seus",
    "tua": "sua", "tuas": "suas", "és": "é", "estás": "está", "tens": "tem",
    "foste": "foi", "achas": "acha", "vais": "vai", "podes": "pode",
    "queres": "quer", "sabes": "sabe", "fazes": "faz", "vens": "vem",
    "tiveste": "teve", "fizeste": "fez", "disseste": "disse", "viste": "viu",
    "estiveste": "esteve", "deste": "deu", "vieste": "veio",
    # 2ª pessoa que apareceu nas capturas reais e escapou da primeira versão
    "consegues": "consegue", "percebes": "percebe", "entendes": "entende",
    "gostas": "gosta", "precisas": "precisa", "deves": "deve", "dizes": "diz",
    "pensas": "pensa", "lembras": "lembra", "ouves": "ouve", "vês": "vê",
    "dás": "dá", "ficas": "fica", "vives": "vive", "trabalhas": "trabalha",
    "esperas": "espera", "imaginas": "imagina", "chamas": "chama",
    "eras": "era", "tinhas": "tinha", "estavas": "estava", "farias": "faria",
    "conheces": "conhece", "acreditas": "acredita", "precisavas": "precisava",
    # vocabulário/construções
    "gerir": "administrar", "percebeste": "entendeu",
    # ortografia pré-acordo
    "óptimo": "ótimo", "facto": "fato", "actual": "atual", "actualmente": "atualmente",
    "acção": "ação", "direcção": "direção", "objectivo": "objetivo",
    "contacto": "contato", "eléctrico": "elétrico", "connosco": "conosco",
    # vocabulário
    "telemóvel": "celular", "autocarro": "ônibus", "comboio": "trem",
    "ecrã": "tela", "frigorífico": "geladeira", "sandes": "sanduíche",
    "peúgas": "meias", "rapariga": "garota", "miúdo": "garoto",
    "bilhetes": "ingressos", "bilhete": "ingresso", "boleia": "carona",
    "chávena": "xícara", "casa de banho": "banheiro",
    "pequeno-almoço": "café da manhã", "telemóveis": "celulares",
}

_RE_TROCAS = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_TROCAS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Locuções que precisam sair antes das trocas palavra a palavra
_FRASES = [
    (re.compile(r"\btem\s+de\b", re.IGNORECASE), "tem que"),
    (re.compile(r"\btenho\s+de\b", re.IGNORECASE), "tenho que"),
    (re.compile(r"\btemos\s+de\b", re.IGNORECASE), "temos que"),
    (re.compile(r"\btêm\s+de\b", re.IGNORECASE), "têm que"),
    (re.compile(r"\btinha\s+de\b", re.IGNORECASE), "tinha que"),
    # "não tem de o fazer" -> "não tem que fazer" (o clítico antes do infinitivo)
    (re.compile(r"\bque\s+(?:o|a)\s+fazer\b", re.IGNORECASE), "que fazer"),
    (re.compile(r"\btoda\s+a\s+gente\b", re.IGNORECASE), "todo mundo"),
    (re.compile(r"\b(?:era|é)\s+suposto\b", re.IGNORECASE), "era pra"),
    # "Está bem." / "Está bem, Frank." -> "Tudo bem". Só antes de pontuação ou fim,
    # senão "Está bem escrito" viraria "Tudo bem escrito".
    (re.compile(r"\bestá\s+bem\b(?=\s*[.,!?]|$)", re.IGNORECASE), "tudo bem"),
]

# Palavras que o modelo entrega MUTILADAS: "Ó" e "Ú" maiúsculos são <unk> no
# SentencePiece do opus-mt (verificado: "Ótimo" -> "timo", "Único" -> "nico";
# "Á" e "É" passam normal). Só reparamos em início de frase, que é onde a
# maiúscula acontece — evita mexer em "timo" (glândula) no meio do texto.
_MUTILADAS = {
    "ptimo": "Ótimo", "timo": "Ótimo", "ptima": "Ótima", "tima": "Ótima",
    "nico": "Único", "nica": "Única", "ltimo": "Último", "ltima": "Última",
    "ltimos": "Últimos", "ltimas": "Últimas", "nicos": "Únicos", "nicas": "Únicas",
}

_RE_MUTILADAS = re.compile(
    r"(^|(?<=[.!?])\s+)(" + "|".join(_MUTILADAS) + r")\b"
)


def _casar_caixa(original: str, novo: str) -> str:
    """Aplica a capitalização do original na substituição."""
    if original.isupper() and len(original) > 1:
        return novo.upper()
    if original[:1].isupper():
        return novo[:1].upper() + novo[1:]
    return novo


def to_ptbr(text: str) -> str:
    if not text:
        return text

    for regex, novo in _FRASES:
        text = regex.sub(lambda m: _casar_caixa(m.group(0), novo), text)

    def _ger(m: re.Match) -> str:
        verbo, raiz, term = m.group(1), m.group(2), m.group(3)
        return f"{verbo} {raiz}{_GERUNDIO[term.lower()]}"

    text = _RE_GERUNDIO.sub(_ger, text)

    def _proclise(m: re.Match) -> str:
        verbo, pron = m.group(1), m.group(2).lower()
        # "Digo-te" -> "Te digo": a maiúscula segue o pronome, que passa a ser 1º
        if verbo[:1].isupper():
            return f"{pron[:1].upper()}{pron[1:]} {verbo[:1].lower()}{verbo[1:]}"
        return f"{pron} {verbo}"

    text = _RE_ENCLISE.sub(_proclise, text)
    text = _RE_TROCAS.sub(
        lambda m: _casar_caixa(m.group(0), _TROCAS[m.group(0).lower()]), text
    )
    text = _RE_MUTILADAS.sub(lambda m: m.group(1) + _MUTILADAS[m.group(2)], text)
    return text
