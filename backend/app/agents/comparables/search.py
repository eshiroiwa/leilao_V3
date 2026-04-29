"""Construção de queries de busca e seleção de raio.

Estratégia em 4 camadas — da mais específica para a mais geral. O grafo
escolhe a primeira que produz queries válidas; se a busca não trouxer
candidatos suficientes, o nó de check_minimum sobe um nível e recalcula.

Camadas (do mais para o menos preciso):
    1. ``condo``        : nome do condomínio + cidade
    2. ``street``       : nome da rua + bairro + cidade
    3. ``neighborhood`` : tipo + bairro + cidade (ex.: "apartamento 2 quartos…")
    4. ``radius``       : geografia pura (não monta query — caller usa PostGIS)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

SearchStrategy = Literal["condo", "street", "neighborhood", "radius"]


# ---------------------------------------------------------------------------
# Cidades "densas" — capitais + principais regiões metropolitanas.
# Em SP/RJ/BH/etc. a oferta é alta, então começamos com raio menor (1 km)
# para evitar trazer comparáveis de outro bairro/zona. No interior usamos
# raio maior porque a malha é mais esparsa.
# ---------------------------------------------------------------------------
_DENSE_CITIES: frozenset[tuple[str, str]] = frozenset(
    {
        # (cidade_normalizada, UF)
        ("sao paulo", "SP"),
        ("rio de janeiro", "RJ"),
        ("belo horizonte", "MG"),
        ("salvador", "BA"),
        ("brasilia", "DF"),
        ("fortaleza", "CE"),
        ("recife", "PE"),
        ("porto alegre", "RS"),
        ("curitiba", "PR"),
        ("manaus", "AM"),
        ("belem", "PA"),
        ("goiania", "GO"),
        ("guarulhos", "SP"),
        ("campinas", "SP"),
        ("sao bernardo do campo", "SP"),
        ("santo andre", "SP"),
        ("osasco", "SP"),
        ("santos", "SP"),
        ("sao jose dos campos", "SP"),
        ("ribeirao preto", "SP"),
        ("niteroi", "RJ"),
        ("sao goncalo", "RJ"),
        ("duque de caxias", "RJ"),
        ("nova iguacu", "RJ"),
        ("contagem", "MG"),
        ("uberlandia", "MG"),
        ("vitoria", "ES"),
        ("vila velha", "ES"),
        ("florianopolis", "SC"),
        ("joinville", "SC"),
        ("londrina", "PR"),
        ("maringa", "PR"),
        ("natal", "RN"),
        ("joao pessoa", "PB"),
        ("cuiaba", "MT"),
        ("campo grande", "MS"),
    }
)

# Plano de raios em metros. Cada estratégia tenta os raios em ordem.
_RADIUS_PLAN_DENSE: tuple[int, ...] = (1000, 2000, 3000)
_RADIUS_PLAN_SPARSE: tuple[int, ...] = (2500, 5000, 10000)


def _normalize_city(city: str | None) -> str:
    if not city:
        return ""
    nfkd = unicodedata.normalize("NFKD", city)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def is_dense_city(city: str | None, state: str | None) -> bool:
    """True se a cidade está na whitelist de densidade alta."""
    if not city or not state:
        return False
    return (_normalize_city(city), state.strip().upper()) in _DENSE_CITIES


def radius_plan(city: str | None, state: str | None) -> tuple[int, ...]:
    """Devolve a sequência de raios (m) a tentar, do menor para o maior."""
    return _RADIUS_PLAN_DENSE if is_dense_city(city, state) else _RADIUS_PLAN_SPARSE


# ---------------------------------------------------------------------------
# Detecção de condomínio (heurística leve).
# Procuramos pistas no `complement` ou `title` do imóvel-alvo.
#
# Cuidado: editais de leilão costumam ter texto contratual logo após
# "condomínio" — ex.: "condomínio e Tributos sob responsabilidade do
# comprador". Por isso filtramos:
#   - matches que começam com stopwords (e, do, da, sob, com, ...);
#   - matches longos demais (>5 palavras);
#   - prefixos curtos ("cond.", "res.", "edif.") foram removidos do
#     gatilho — geram muitos falsos positivos em texto livre.
# ---------------------------------------------------------------------------
_CONDO_NAME_RE = re.compile(
    r"\b(?:edif[ií]cio|residencial|condom[íi]nio|conjunto\s+residencial)"
    r"\s+([A-ZÁ-ÚÇ0-9][A-Za-zÀ-úÇç0-9\s\-]+?)(?=\s*[,.;\n]|$)",
    flags=re.IGNORECASE,
)

# Palavras que, se aparecerem como PRIMEIRA palavra do match, sinalizam que
# o regex pegou texto contratual em vez de um nome próprio.
_CONDO_STOPWORDS_HEAD: frozenset[str] = frozenset(
    {
        "e", "ou", "no", "na", "nos", "nas",
        "do", "da", "dos", "das",
        "de", "ao", "aos", "à", "às",
        "com", "sem", "sob", "sobre", "para", "por",
        "que", "se", "tem", "ter", "será", "sera",
        "fica", "ficará", "ficara",
    }
)


def detect_condo_name(target: dict[str, Any]) -> str | None:
    """Tenta extrair o nome do condomínio a partir de title/complement.

    Retorna o nome limpo (sem o prefixo "Edifício/Residencial") ou None.
    """
    haystacks: list[str] = []
    for key in ("title", "complement", "description"):
        v = target.get(key)
        if isinstance(v, str) and v.strip():
            haystacks.append(v)
    if not haystacks:
        return None

    text = " | ".join(haystacks)
    m = _CONDO_NAME_RE.search(text)
    if not m:
        return None

    name = m.group(1).strip(" -,.")

    # Filtros de qualidade:
    if len(name) < 3 or name.lower() in {"sn", "s/n", "n/d"}:
        return None

    words = name.split()
    if not words:
        return None

    # 1ª palavra começando com stopword → falso positivo (texto contratual).
    if words[0].lower() in _CONDO_STOPWORDS_HEAD:
        return None

    # Nomes próprios costumam ter <= 5 palavras. Mais que isso, é frase.
    if len(words) > 5:
        return None

    # Pelo menos uma palavra deve começar com maiúscula no original
    # (evita pegar "ele entrou no condominio antigo do bairro" etc.)
    if not any(w[:1].isupper() for w in words):
        return None

    return name


# ---------------------------------------------------------------------------
# Construção de queries.
# ---------------------------------------------------------------------------
# Filtro de site reusado por todas as estratégias. Sempre anexado por
# ÚLTIMO e nunca é truncado — caso contrário a busca volta sem filtro
# e traz resultados aleatórios (vimos em produção: `(site:vivareal'`).
_SITE_FILTER = "(site:vivareal.com.br OR site:zapimoveis.com.br)"

# Tamanho máx. razoável para o Firecrawl/Google. Antes era 80 — pequeno
# demais e cortava o filtro de site.
_MAX_QUERY_LEN = 256


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _compose_query(prefix: str, *, with_site: bool = True) -> str:
    """Normaliza espaços do prefixo, trunca se passar do limite, então
    anexa o ``_SITE_FILTER`` (que NUNCA é cortado)."""
    prefix = _normalize_spaces(prefix)
    if not with_site:
        return prefix[:_MAX_QUERY_LEN].rstrip()
    # Reserva espaço para " " + filtro completo.
    budget = _MAX_QUERY_LEN - len(_SITE_FILTER) - 1
    if budget < 20:  # caso patológico — devolve só o prefixo
        return prefix[:_MAX_QUERY_LEN].rstrip()
    head = prefix[:budget].rstrip()
    return f"{head} {_SITE_FILTER}"


def build_queries(
    target: dict[str, Any],
    *,
    strategy: SearchStrategy,
) -> list[str]:
    """Monta queries adequadas à estratégia. Cada query é uma string que
    será passada como ``q`` para o Firecrawl ``/search``.

    O caller passa ``strategy=condo`` apenas se ``detect_condo_name(target)``
    retornou um nome (responsabilidade fora desta função).
    """
    city = (target.get("city") or "").strip()
    state = (target.get("state") or "").strip().upper()
    neighborhood = (target.get("neighborhood") or "").strip()
    ptype = (target.get("property_type") or "imóvel").strip().lower()
    bedrooms = target.get("bedrooms")

    if not city or not state:
        return []

    if strategy == "condo":
        condo = detect_condo_name(target)
        if not condo:
            return []
        return [_compose_query(f'venda "{condo}" {city} {state}')]

    if strategy == "street":
        street = (target.get("street") or "").strip()
        if not street:
            return []
        # Sem aspas na rua para o Google relaxar o match (ruas raramente
        # aparecem com nome 100% idêntico no anúncio).
        return [_compose_query(f"venda {street} {neighborhood} {city} {state}")]

    if strategy == "neighborhood":
        if not neighborhood:
            return []
        beds_clause = f"{bedrooms} quartos" if bedrooms else ""
        return [
            _compose_query(
                f"venda {ptype} {beds_clause} {neighborhood} {city} {state}"
            )
        ]

    # 'radius' não monta query: o caller deve consultar PostGIS direto na tabela
    # `listings` (já scrapeadas anteriormente, dentro do raio).
    return []


def next_strategy(current: SearchStrategy) -> SearchStrategy | None:
    """Próxima estratégia (mais genérica) ou None se já estamos na mais ampla."""
    order: tuple[SearchStrategy, ...] = ("condo", "street", "neighborhood", "radius")
    try:
        idx = order.index(current)
    except ValueError:
        return None
    return order[idx + 1] if idx + 1 < len(order) else None


__all__ = [
    "SearchStrategy",
    "is_dense_city",
    "radius_plan",
    "detect_condo_name",
    "build_queries",
    "next_strategy",
]
