"""Utilitários internos do Agente 1.

`sanitize_neighborhood` remove prefixos administrativos comuns em endereços
brasileiros (especialmente no portal CEF e leiloeiros) que confundem o
Google Address Validation, fazendo-o fragmentar a linha de endereço e/ou
geocodar para a cidade errada.

Exemplos:

    "LOTEAMENTO JARDIM ANA MARIA"        → "Jardim Ana Maria"
    "CONJUNTO HABITACIONAL VILA NOVA"    → "Vila Nova"
    "Residencial Parque das Árvores"     → "Parque das Árvores"
    "Cond. Residencial Sol Nascente"     → "Sol Nascente"
    "JD. RESIDENCIAL X"                  → "Jardim X"

Não removemos prefixos canônicos do bairro propriamente dito ('Jardim',
'Vila', 'Parque', 'Bairro', etc.).
"""

from __future__ import annotations

import re

# Prefixos a serem REMOVIDOS quando aparecem no início (case-insensitive).
# Ordem importa: prefixos mais longos primeiro para casar antes dos curtos.
_NEIGHBORHOOD_PREFIXES_TO_STRIP: tuple[str, ...] = (
    r"conjunto\s+habitacional",
    r"loteamento\s+residencial",
    r"empreendimento\s+imobili[áa]rio",
    r"empreendimento",
    r"loteamento",
    r"residencial",
    r"condom[íi]nio",
    r"cond\.?",
    r"parque\s+residencial",
    r"jardim\s+residencial",
    r"distrito\s+industrial",
    r"setor\s+habitacional",
    r"n[úu]cleo\s+habitacional",
)

_PREFIX_PATTERN = re.compile(
    r"^\s*(?:" + "|".join(_NEIGHBORHOOD_PREFIXES_TO_STRIP) + r")(?=\s|$|[\-,:.])[\s\-,:.]*",
    flags=re.IGNORECASE,
)

# Abreviações comuns expandidas para o nome canônico. Casam ponto opcional
# seguido de espaço/fim — sem usar \b no final, que falha quando há "."
# (transição non-word → non-word).
_EXPAND_ABBREV: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bjd\.?(?=\s|$)", re.IGNORECASE), "Jardim"),
    (re.compile(r"\bv\.?(?=\s)", re.IGNORECASE), "Vila"),
    (re.compile(r"\bres\.?(?=\s|$)", re.IGNORECASE), "Residencial"),
    (re.compile(r"\bpq\.?(?=\s|$)", re.IGNORECASE), "Parque"),
)

# Palavras "pequenas" que mantemos em minúsculo no Title Case
# (artigos / preposições). Não se aplicam à primeira palavra.
_LOWERCASE_WORDS: frozenset[str] = frozenset(
    {"de", "da", "do", "das", "dos", "e", "a", "o"}
)


def _smart_title(text: str) -> str:
    """Title Case por palavra, mantendo preposições/artigos em minúsculo.

    Cada palavra que está totalmente em maiúsculas é convertida para
    Title Case (ex.: 'PAULISTA' → 'Paulista'). Palavras já em casing
    misto/correto são preservadas (ex.: 'Sol Nascente' fica 'Sol Nascente').
    Preposições/artigos curtos viram minúsculo, exceto se forem a 1ª palavra.
    """
    if not text:
        return text

    parts = text.split()
    out: list[str] = []
    for i, p in enumerate(parts):
        # Palavra em CAPS (≥2 chars) → Title (mantém acentos).
        if len(p) >= 2 and p.isupper():
            converted = p[:1] + p[1:].lower()
        else:
            converted = p
        # Preposição/artigo no meio do nome vai para minúsculo.
        if i > 0 and converted.lower() in _LOWERCASE_WORDS:
            converted = converted.lower()
        out.append(converted)
    return " ".join(out)


# Padrões de quadra do DF / Brasília. Usamos como âncora para detectar
# quando "QUADRA" é redundante (ex.: "QUADRA QN 407" → "QN 407").
_DF_QUADRA_TOKENS: tuple[str, ...] = (
    "qr", "qn", "qi", "qs", "qd", "ql", "qe", "qms",
    "sqn", "sqs", "sqsw", "sqno", "sqso",
    "ces", "ce", "shis", "shig", "smdb", "smpw",
    "epia", "eqs", "eqn",
)

_QUADRA_PREFIX_PATTERN = re.compile(
    # 'QUADRA QR 108', 'Q. QN 407', 'Quadra: QI 5'
    r"^\s*(?:quadra|q)[\s\-,:.]+(?=(?:" + "|".join(_DF_QUADRA_TOKENS) + r")\b)",
    flags=re.IGNORECASE,
)

# Padrões de "sem número": SN, S/N, S.N., s/nº, s/n°
_SEM_NUMERO_PATTERN = re.compile(
    r"^\s*s\.?\s*[/\\]?\s*n[º°]?\.?\s*$",
    flags=re.IGNORECASE,
)


def sanitize_street(value: str | None) -> str | None:
    """Limpa prefixos redundantes do logradouro.

    Hoje cobre apenas o caso do DF: 'QUADRA QR 108' → 'QR 108'.
    Devolve ``None`` para entrada vazia.
    """
    if not value:
        return None
    cleaned = value.strip()
    cleaned = _QUADRA_PREFIX_PATTERN.sub("", cleaned, count=1)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,:.")
    return cleaned or None


def sanitize_number(value: str | None) -> str | None:
    """Normaliza o 'número' do endereço.

    'SN', 'S/N', 's/n°' viram ``None`` (campo realmente sem número).
    """
    if not value:
        return None
    if _SEM_NUMERO_PATTERN.match(value):
        return None
    return value.strip() or None


def sanitize_neighborhood(value: str | None) -> str | None:
    """Limpa prefixos espúrios do nome do bairro.

    Retorna ``None`` se a entrada for falsy ou se o resultado ficar vazio.
    """
    if not value:
        return None

    cleaned = value.strip()

    # 1) Expande abreviações ANTES do strip (assim 'JD. RESIDENCIAL X'
    # vira 'Jardim RESIDENCIAL X' e o strip subsequente remove 'RESIDENCIAL').
    for pattern, replacement in _EXPAND_ABBREV:
        cleaned = pattern.sub(replacement, cleaned)

    # 2) Remove prefixos administrativos repetidamente (lida com aninhamento
    # como 'LOTEAMENTO RESIDENCIAL X').
    while True:
        new_cleaned = _PREFIX_PATTERN.sub("", cleaned, count=1)
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,:.")

    if not cleaned:
        return None

    return _smart_title(cleaned)
