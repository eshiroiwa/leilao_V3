"""Nós (nodes) do grafo do AGENTE 2.

Cada função recebe o ``ScraperState`` (dict-like via TypedDict) e devolve um
patch parcial. Erros não-fatais entram em ``warnings``; fatais em ``errors``
(o grafo aborta antes de persistir).

Convenções:
  * funções `_helpers` sem prefixo `node_` são privadas;
  * `node_X` é uma função registrada no LangGraph;
  * I/O externo (Firecrawl, Supabase, OpenAI) entra via factories
    (`get_*_service`) para facilitar mock nos testes.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langchain_openai import ChatOpenAI

from app.agents.comparables.cache import split_cached_vs_fresh
from app.agents.comparables.prompts import (
    build_batch_extraction_messages,
    build_extraction_messages,
)
from app.agents.comparables.schemas import ExtractedListing, ListingBatch
from app.agents.comparables.scoring import (
    RELIABILITY_THRESHOLD,
    condo_match_score,
    haversine_m,
    reliability_score,
    similarity_score,
)
from app.agents.comparables.search import (
    SearchStrategy,
    build_queries,
    detect_condo_name,
    next_strategy,
    radius_plan,
)
from app.agents.comparables.sources import find_adapter
from app.agents.comparables.state import ComparablesState
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.firecrawl_service import FirecrawlScrapeError, get_firecrawl_service
from app.services.google_maps_service import get_google_maps_service
from app.services.supabase_service import get_supabase_service

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _append(state: ComparablesState, key: str, value: str) -> list[str]:
    out = list(state.get(key) or [])
    out.append(value)
    return out


def _location_ewkt(lat: float, lng: float) -> str:
    return f"SRID=4326;POINT({lng} {lat})"


# Stopwords removidas ANTES de comparar nomes de rua (R., Av., etc.).
_STREET_PREFIXES = {
    "rua", "r", "avenida", "av", "alameda", "al", "travessa", "tv",
    "estrada", "est", "rodovia", "rod", "praca", "pca", "pç",
    "largo", "lgo", "viela", "via", "viaduto", "vd",
    "servidao", "passagem", "psg",
}


def _normalize_street(s: str | None) -> str:
    """Normaliza nome de rua para comparação tolerante:

    * remove acentos e pontuação;
    * lowercase;
    * remove o "tipo" no início (Rua, Av., R., etc.).

    Ex.: ``"R. Imperatriz Leopoldina"`` → ``"imperatriz leopoldina"``.
    """
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", no_accents).strip().lower()
    tokens = cleaned.split()
    if tokens and tokens[0] in _STREET_PREFIXES:
        tokens = tokens[1:]
    return " ".join(tokens)


def _same_street(a: str | None, b: str | None) -> bool:
    """True se ``a`` e ``b`` representam a mesma rua (após normalização).

    Comparação é simétrica e exige >= 3 tokens em comum OU igualdade total
    do nome curto (evita matches espúrios em ruas com nomes muito comuns).
    """
    na, nb = _normalize_street(a), _normalize_street(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    # interseção significativa (>=3 palavras OU 100% das palavras de uma)
    inter = ta & tb
    return len(inter) >= 3 or (
        len(inter) >= 2 and (inter == ta or inter == tb)
    )


def _budget_inc(state: ComparablesState, *, firecrawl: int = 0, llm: int = 0) -> dict:
    settings = get_settings()
    fc = state.get("firecrawl_calls", 0) + firecrawl
    lc = state.get("llm_calls", 0) + llm
    cost = fc * settings.cma_brl_per_firecrawl_call + lc * settings.cma_brl_per_llm_call
    return {
        "firecrawl_calls": fc,
        "llm_calls": lc,
        "cost_estimate_brl": round(cost, 4),
    }


# ---------------------------------------------------------------------------
# 1) load_target — carrega o property do banco
# ---------------------------------------------------------------------------
def node_load_target(state: ComparablesState) -> dict[str, Any]:
    sb = get_supabase_service()
    pid = state["property_id"]
    target = sb.get_property_by_id(pid)
    if not target:
        return {"errors": _append(state, "errors", f"property {pid} não encontrado")}
    if not target.get("latitude") or not target.get("longitude"):
        return {
            "errors": _append(
                state,
                "errors",
                "property sem latitude/longitude — rode o AGENTE 1 antes.",
            )
        }
    return {"target": target}


# ---------------------------------------------------------------------------
# 2) build_query — escolhe a estratégia inicial
# ---------------------------------------------------------------------------
def node_build_query(state: ComparablesState) -> dict[str, Any]:
    target = state.get("target") or {}
    plan = radius_plan(target.get("city"), target.get("state"))
    initial_radius = plan[0]

    # Condomínio detectado → começa por 'condo'; senão tenta street.
    if detect_condo_name(target):
        strategy: SearchStrategy = "condo"
    elif (target.get("street") or "").strip():
        strategy = "street"
    else:
        strategy = "neighborhood"

    queries = build_queries(target, strategy=strategy)
    if not queries and strategy != "neighborhood":
        # Fallback imediato para neighborhood sem gastar 0 queries
        strategy = "neighborhood"
        queries = build_queries(target, strategy=strategy)

    logger.info(
        "cma.build_query",
        strategy=strategy,
        n_queries=len(queries),
        initial_radius_m=initial_radius,
    )
    return {
        "search_strategy": strategy,
        "search_radius_m": initial_radius,
        "search_queries": queries,
    }


# ---------------------------------------------------------------------------
# 3) search_listings — Firecrawl /search → URLs candidatas
# ---------------------------------------------------------------------------
def node_search_listings(state: ComparablesState) -> dict[str, Any]:
    settings = get_settings()
    queries = state.get("search_queries") or []
    if not queries:
        return {
            "candidate_urls": [],
            "warnings": _append(
                state, "warnings", "search: sem queries — pulando busca externa."
            ),
        }

    fc = get_firecrawl_service()
    seen: dict[str, None] = {}  # preserva ordem de inserção
    calls_used = 0
    budget = settings.cma_max_firecrawl_searches

    n_seen_total = 0
    n_no_adapter = 0
    n_rejected = 0
    rejected_examples: list[str] = []  # primeiras 3 URLs descartadas (para debug)

    for q in queries:
        if calls_used >= budget:
            break
        results = fc.search(q, limit=10)
        calls_used += 1
        for r in results:
            url = r.get("url")
            if not url:
                continue
            n_seen_total += 1
            adapter = find_adapter(url)
            if not adapter:
                n_no_adapter += 1
                if len(rejected_examples) < 3:
                    rejected_examples.append(f"NO_ADAPTER:{url}")
                continue
            # Aceitamos anúncio individual OU página de listagem rica.
            # is_scrapable() vem do adapter VivaReal/ZAP.
            scrapable = getattr(adapter, "is_scrapable", adapter.is_listing_url)(url)
            if not scrapable:
                n_rejected += 1
                if len(rejected_examples) < 3:
                    rejected_examples.append(f"NOT_SCRAPABLE:{url}")
                continue
            canon = adapter.canonicalize_url(url)
            seen.setdefault(canon, None)

    candidates = list(seen.keys())
    logger.info(
        "cma.search.ok",
        n_candidates=len(candidates),
        n_seen=n_seen_total,
        n_no_adapter=n_no_adapter,
        n_rejected=n_rejected,
        calls=calls_used,
        strategy=state.get("search_strategy"),
        accepted_urls=candidates[:5] or None,  # primeiras 5 para inspeção
        rejected_examples=rejected_examples or None,
    )

    out: dict[str, Any] = {"candidate_urls": candidates}
    out.update(_budget_inc(state, firecrawl=calls_used))
    if not candidates:
        out["warnings"] = _append(
            state, "warnings", f"search: 0 candidatos para '{state.get('search_strategy')}'."
        )
    return out


# ---------------------------------------------------------------------------
# 4) fetch_candidates — Firecrawl /scrape para cada URL nova
# ---------------------------------------------------------------------------
def node_fetch_candidates(state: ComparablesState) -> dict[str, Any]:
    settings = get_settings()
    candidates = state.get("candidate_urls") or []
    if not candidates:
        return {"scraped_listings": []}

    sb = get_supabase_service()
    cached_rows = sb.get_listings_by_urls(candidates)
    cached, fresh = split_cached_vs_fresh(
        candidates, cached_rows, ttl_days=settings.cma_listing_cache_days
    )

    # Hard cap de scrapes por execução.
    fresh = fresh[: settings.cma_max_firecrawl_scrapes]

    fc = get_firecrawl_service()
    scraped: list[dict[str, Any]] = []

    # Cached: já são listings completos no banco — sinalizamos via from_cache.
    for url, row in cached.items():
        scraped.append({"source_url": url, "from_cache": True, "cached_row": row})

    # Scrapes em paralelo (Firecrawl é I/O-bound: cada call leva 5-7s).
    # Threads bastam — não precisamos de asyncio aqui.
    calls_used = 0

    def _scrape_one(url: str) -> dict[str, Any] | None:
        try:
            doc = fc.scrape_to_markdown(url)
        except FirecrawlScrapeError as exc:
            logger.warning("cma.fetch.skip", url=url, error=str(exc))
            return None
        return {
            "source_url": url,
            "from_cache": False,
            "markdown": doc["markdown"],
            "metadata": doc.get("metadata") or {},
        }

    if fresh:
        max_workers = min(len(fresh), 4)  # 4 scrapes em paralelo é seguro
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_scrape_one, u): u for u in fresh}
            for fut in as_completed(futures):
                result = fut.result()
                if result is not None:
                    scraped.append(result)
                    calls_used += 1

    out: dict[str, Any] = {"scraped_listings": scraped}
    out.update(_budget_inc(state, firecrawl=calls_used))
    logger.info(
        "cma.fetch.ok",
        n_total=len(scraped),
        n_cached=len(cached),
        n_fresh=calls_used,
    )
    return out


# ---------------------------------------------------------------------------
# 5) extract_listings — LLM por listing (não-cached)
#
# Detecta o tipo da URL via adapter:
#   * /imovel/...-id-N/   → ExtractedListing (1 chamada LLM = 1 anúncio)
#   * /venda/uf/cidade/.../categoria/ → ListingBatch (1 chamada LLM = N anúncios)
#
# Páginas de RESULTADOS DE BUSCA são MUITO mais frequentes no SEO do
# VivaReal/ZAP do que páginas de anúncio individual — por isso o batch
# é o caminho principal na prática.
# ---------------------------------------------------------------------------
def _synthetic_listing_url(parent_url: str, idx: int, raw: dict[str, Any]) -> str:
    """Gera uma URL única para um item de página de busca quando o LLM NÃO
    conseguiu extrair a URL real do anúncio individual.

    Usado APENAS como fallback. Quando o anunciante incluiu o link direto
    do anúncio no markdown (padrão "[Contatar](.../imovel/...-id-N/)"),
    preferimos esse link — fica clicável para o usuário no frontend.

    Estabilidade: o hash inclui preço/área/rua/título → re-extrair o mesmo
    card gera o mesmo id ⇒ upsert com `UNIQUE(source_url)` deduplica.
    """
    sig_parts = [
        str(raw.get("listed_price") or ""),
        str(raw.get("area_total_m2") or ""),
        (raw.get("street") or ""),
        (raw.get("neighborhood") or ""),
        (raw.get("title") or "")[:40],
        str(idx),
    ]
    sig = hashlib.sha1("|".join(sig_parts).encode("utf-8")).hexdigest()[:10]
    sep = "&" if "?" in parent_url else "#"
    return f"{parent_url.rstrip('/')}{sep}item={sig}"


def _resolve_listing_url(
    *, raw: dict[str, Any], parent_url: str, idx: int
) -> tuple[str, bool]:
    """Decide a `source_url` final do listing extraído de uma página de busca.

    Preferência: usar a URL real que o LLM achou no markdown (campo
    ``raw.source_url``), validada:
      * deve ser absoluta http(s);
      * deve casar com algum `SourceAdapter` conhecido;
      * deve ser um anúncio individual (`is_listing_url`);
      * HOST precisa coincidir EXATAMENTE com o do `parent_url`
        (anti-alucinação: evita "scrapeei vivareal e o LLM devolveu link
        do zap"; embora ambos sejam do mesmo grupo, o card real só
        aponta para o portal de origem).

    Se qualquer validação falhar, cai no `_synthetic_listing_url` (hash).
    Devolve `(url, is_real)` — o flag é só para logging/diagnóstico.
    """
    raw_url = (raw.get("source_url") or "").strip()
    if not raw_url:
        return _synthetic_listing_url(parent_url, idx, raw), False

    if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
        return _synthetic_listing_url(parent_url, idx, raw), False

    adapter = find_adapter(raw_url)
    if adapter is None or not adapter.is_listing_url(raw_url):
        return _synthetic_listing_url(parent_url, idx, raw), False

    if _normalize_host(raw_url) != _normalize_host(parent_url):
        return _synthetic_listing_url(parent_url, idx, raw), False

    return adapter.canonicalize_url(raw_url), True


def _normalize_host(url: str) -> str:
    """Host em lowercase, sem 'www.', usado para comparação exata."""
    from urllib.parse import urlparse

    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def node_extract_listings(state: ComparablesState) -> dict[str, Any]:
    settings = get_settings()
    scraped = state.get("scraped_listings") or []
    extracted: list[dict[str, Any]] = []

    # Cached: payload já extraído num run anterior — reaproveita raw_extraction.
    for item in scraped:
        if item.get("from_cache"):
            row = item["cached_row"]
            raw = row.get("raw_extraction") or {}
            extracted.append(
                {"source_url": item["source_url"], "from_cache": True, "raw": raw}
            )

    fresh_items = [s for s in scraped if not s.get("from_cache")]
    if not fresh_items:
        return {"extracted_listings": extracted}

    base_llm = ChatOpenAI(
        model=settings.openai_extraction_model,
        api_key=settings.openai_api_key,
        timeout=90,
    )
    llm_single = base_llm.with_structured_output(ExtractedListing)
    llm_batch = base_llm.with_structured_output(ListingBatch)

    budget = settings.cma_max_llm_calls
    items_to_process = fresh_items[:budget]
    if len(fresh_items) > budget:
        logger.warning(
            "cma.extract.budget_capped",
            requested=len(fresh_items),
            allowed=budget,
        )

    def _extract_one(
        item: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Processa 1 item e devolve (lista_de_extracted_dicts, log_meta)."""
        url = item["source_url"]
        adapter = find_adapter(url)
        is_search_results = bool(
            adapter and getattr(adapter, "is_search_results_url", lambda _u: False)(url)
        )

        if is_search_results:
            msgs = build_batch_extraction_messages(url=url, markdown=item["markdown"])
            try:
                batch: ListingBatch = llm_batch.invoke(msgs)
            except Exception as exc:
                logger.warning("cma.extract.batch.fail", url=url, error=str(exc))
                return [], {"kind": "batch_fail", "url": url}
            out_items: list[dict[str, Any]] = []
            n_real_url = 0
            for idx, sub in enumerate(batch.listings):
                if sub.listed_price is None or sub.area_total_m2 is None:
                    continue
                raw_dump = sub.model_dump()
                resolved_url, is_real = _resolve_listing_url(
                    raw=raw_dump, parent_url=url, idx=idx
                )
                if is_real:
                    n_real_url += 1
                # Sobrescreve para ficar consistente entre `source_url` do
                # objeto extracted e o `raw_extraction.source_url` salvo
                # no banco (assim o cache também já vê a URL real).
                raw_dump["source_url"] = resolved_url
                out_items.append(
                    {
                        "source_url": resolved_url,
                        "parent_url": url,
                        "from_cache": False,
                        "raw": raw_dump,
                        "markdown": None,
                    }
                )
            return out_items, {
                "kind": "batch",
                "url": url,
                "n_items": len(batch.listings),
                "n_kept": len(out_items),
                "n_real_url": n_real_url,
            }

        # Single (anúncio individual)
        msgs = build_extraction_messages(url=url, markdown=item["markdown"])
        try:
            obj: ExtractedListing = llm_single.invoke(msgs)
        except Exception as exc:
            logger.warning("cma.extract.fail", url=url, error=str(exc))
            return [], {"kind": "single_fail", "url": url}
        return [
            {
                "source_url": url,
                "from_cache": False,
                "raw": obj.model_dump(),
                "markdown": item["markdown"],
            }
        ], {"kind": "single", "url": url}

    # Paralelo: cada chamada LLM leva 20-40s; rodar em paralelo derruba
    # o tempo total para o tempo do mais lento (~30s) em vez da soma.
    calls_used = len(items_to_process)
    n_listings_added = 0
    if items_to_process:
        max_workers = min(len(items_to_process), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_extract_one, it) for it in items_to_process]
            for fut in as_completed(futures):
                results, meta = fut.result()
                extracted.extend(results)
                n_listings_added += len(results)
                if meta.get("kind") == "batch":
                    logger.info(
                        "cma.extract.batch.ok",
                        url=meta["url"],
                        n_items=meta["n_items"],
                        n_kept=meta["n_kept"],
                        n_real_url=meta.get("n_real_url"),
                    )

    out: dict[str, Any] = {"extracted_listings": extracted}
    out.update(_budget_inc(state, llm=calls_used))
    logger.info(
        "cma.extract.ok",
        n_extracted=len(extracted),
        n_added=n_listings_added,
        llm_calls=calls_used,
    )
    return out


# ---------------------------------------------------------------------------
# 6) enrich_geo — geocoda os novos, persiste em listings
# ---------------------------------------------------------------------------
def node_enrich_geo(state: ComparablesState) -> dict[str, Any]:
    extracted = state.get("extracted_listings") or []
    if not extracted:
        return {"enriched_listings": []}

    sb = get_supabase_service()
    gm = get_google_maps_service()
    enriched: list[dict[str, Any]] = []

    for item in extracted:
        if item["from_cache"]:
            # Já vem do banco com lat/lng; recarregamos a row se precisar.
            cached_row = next(
                (
                    s["cached_row"]
                    for s in state.get("scraped_listings", [])
                    if s.get("from_cache") and s.get("source_url") == item["source_url"]
                ),
                None,
            )
            if cached_row:
                enriched.append(cached_row)
            continue

        raw = item["raw"]
        adapter = find_adapter(item["source_url"])

        # Geocoding: tentamos street+number+neighborhood+city,state. Se não
        # tiver street, cai no fallback por CEP. Se mesmo assim falhar,
        # persistimos com geocoding_confidence=REJECTED (não vira comparável).
        lat, lng, confidence = _safe_geocode(gm, raw)

        payload: dict[str, Any] = {
            "source": adapter.name if adapter else "unknown",
            "source_url": item["source_url"],
            "external_id": adapter.extract_external_id(item["source_url"]) if adapter else None,
            "property_type": raw.get("property_type"),
            "area_total_m2": raw.get("area_total_m2"),
            "area_useful_m2": raw.get("area_useful_m2"),
            "bedrooms": raw.get("bedrooms"),
            "bathrooms": raw.get("bathrooms"),
            "parking_spaces": raw.get("parking_spaces"),
            "condo_name": raw.get("condo_name"),
            "amenities": raw.get("amenities"),
            "street": raw.get("street"),
            "number": raw.get("number"),
            "neighborhood": raw.get("neighborhood"),
            "city": raw.get("city"),
            "state": raw.get("state"),
            "postal_code": raw.get("postal_code"),
            "geocoding_confidence": confidence,
            "listed_price": raw.get("listed_price"),
            "monthly_condo_fee": raw.get("monthly_condo_fee"),
            "iptu": raw.get("iptu"),
            "photos_count": raw.get("photos_count"),
            "advertiser_type": raw.get("advertiser_type") or "desconhecido",
            "raw_markdown": item.get("markdown"),
            "raw_extraction": raw,
        }
        if lat is not None and lng is not None:
            payload["location"] = _location_ewkt(lat, lng)

        # Score de confiabilidade para o filtro a seguir.
        # Calculamos com lat/lng "esperadas" — depois enriched terá os valores reais
        # do banco (com columns geradas).
        for_score = {**payload, "latitude": lat, "longitude": lng}
        payload["reliability_score"] = round(reliability_score(for_score), 3)

        try:
            row = sb.upsert_listing(payload)
        except Exception as exc:
            logger.warning("cma.persist.listing.fail", url=item["source_url"], error=str(exc))
            continue
        enriched.append(row)

    # Deduplica por listing.id (PK no banco). O mesmo anúncio pode aparecer
    # em duas páginas de busca diferentes (mesma URL real) — o `upsert_listing`
    # com `on_conflict=source_url` resolve para a MESMA row, e dois entries
    # apontando para o mesmo id quebrariam a PK composta de
    # `valuation_comparables (valuation_id, listing_id)` no `node_persist`.
    # Mantemos a primeira ocorrência (ordem de extração).
    seen_ids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    n_dups = 0
    for row in enriched:
        rid = row.get("id")
        if not rid:
            deduped.append(row)
            continue
        if rid in seen_ids:
            n_dups += 1
            continue
        seen_ids.add(rid)
        deduped.append(row)

    if n_dups:
        logger.info(
            "cma.enrich.dedup",
            n_total=len(enriched),
            n_unique=len(deduped),
            n_dups=n_dups,
        )

    return {"enriched_listings": deduped}


def _safe_geocode(gm, raw: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    """Geocoding mais simples que o do AGENTE 1: se street+postal_code temos,
    usa formattedAddress; caso contrário tenta só CEP+cidade."""
    parts: list[str] = []
    line1 = ", ".join(p for p in [raw.get("street"), raw.get("number")] if p)
    if line1:
        parts.append(line1)
    if raw.get("neighborhood"):
        parts.append(raw["neighborhood"])
    city = raw.get("city")
    state_uf = raw.get("state")
    pc = raw.get("postal_code")
    tail = ", ".join(p for p in [city, state_uf, "Brasil"] if p)
    query = ", ".join(parts + ([tail] if tail else []))

    if not query.strip():
        if pc and city and state_uf:
            query = f"CEP {pc}, {city}, {state_uf}, Brasil"
        else:
            return None, None, "REJECTED"

    try:
        gres = gm.geocode(query)
    except Exception:
        return None, None, "REJECTED"
    lat_lng = gm.extract_lat_lng(gres)
    if not lat_lng:
        # tenta fallback CEP
        if pc and city and state_uf:
            try:
                gres = gm.geocode(f"CEP {pc}, {city}, {state_uf}, Brasil")
                lat_lng = gm.extract_lat_lng(gres)
                if lat_lng:
                    return lat_lng[0], lat_lng[1], "POSTAL_CODE"
            except Exception:
                pass
        return None, None, "REJECTED"

    location_type = (gres.get("geometry") or {}).get("location_type", "APPROXIMATE")
    confidence = {
        "ROOFTOP": "HIGH",
        "RANGE_INTERPOLATED": "MEDIUM",
        "GEOMETRIC_CENTER": "MEDIUM",
        "APPROXIMATE": "LOW",
    }.get(location_type, "LOW")

    # Anúncios de mercado raramente têm número exato → Google devolve
    # APPROXIMATE para MUITAS ruas residenciais. Isso por si só não torna
    # o comparável inútil: saber a RUA já basta para o CMA. Por isso
    # promovemos APPROXIMATE → MEDIUM quando temos rua + cidade + UF
    # estruturados (sinal de endereço razoavelmente identificado).
    if (
        confidence == "LOW"
        and (raw.get("street") or "").strip()
        and (raw.get("city") or "").strip()
        and (raw.get("state") or "").strip()
    ):
        confidence = "MEDIUM"

    return lat_lng[0], lat_lng[1], confidence


# ---------------------------------------------------------------------------
# 7) score_similarity — calcula peso e distância
# ---------------------------------------------------------------------------
def node_score_similarity(state: ComparablesState) -> dict[str, Any]:
    target = state.get("target") or {}
    enriched = state.get("enriched_listings") or []
    radius_m = state.get("search_radius_m") or 2000

    scored: list[dict[str, Any]] = []
    for listing in enriched:
        rel = listing.get("reliability_score") or reliability_score(listing)
        rel = float(rel)

        # Hard filter: tipo igual
        same_type = (
            (listing.get("property_type") or "").lower()
            == (target.get("property_type") or "").lower()
        )

        # Hard filter: dentro do raio (se ambos têm geo)
        distance_m = None
        if (
            listing.get("latitude") is not None
            and listing.get("longitude") is not None
            and target.get("latitude") is not None
            and target.get("longitude") is not None
        ):
            distance_m = haversine_m(
                float(target["latitude"]),
                float(target["longitude"]),
                float(listing["latitude"]),
                float(listing["longitude"]),
            )

        sim = similarity_score(target, listing)
        weight = round(sim * rel, 4)

        # Override "mesma rua": geocoding APPROXIMATE para anúncios sem
        # número costuma cair no centroide do BAIRRO. Se a rua extraída
        # bate com a rua do alvo, esse anúncio É um comparable legítimo
        # — não importa se o ponto APPROXIMATE caiu fora do raio.
        on_same_street = _same_street(listing.get("street"), target.get("street"))

        # Override "mesmo condomínio": prédio é o sinal mais forte.
        # Quando os nomes batem, o anúncio é um comparable legítimo MESMO
        # que a geocodificação seja ruim ou caia fora do raio (cada
        # apartamento do mesmo prédio é literalmente o melhor comparable
        # possível pro alvo).
        same_condo = (
            condo_match_score(
                target.get("condo_name"), listing.get("condo_name")
            )
            == 1.0
        )

        used = True
        reason = None
        if not listing.get("listed_price") or not listing.get("area_total_m2"):
            used, reason = False, "sem preço ou área"
        elif rel < RELIABILITY_THRESHOLD and not same_condo:
            used, reason = False, f"reliability={rel:.2f} < {RELIABILITY_THRESHOLD}"
        elif not same_type:
            used, reason = False, f"property_type≠{target.get('property_type')}"
        elif (
            distance_m is not None
            and distance_m > radius_m
            and not on_same_street
            and not same_condo
        ):
            used, reason = False, f"distance={distance_m:.0f}m > {radius_m}m"

        scored.append(
            {
                "listing_id": listing["id"],
                "distance_m": round(distance_m, 2) if distance_m is not None else None,
                "similarity_score": round(sim, 3),
                "weight": weight,
                "used": used,
                "rejection_reason": reason,
                "_same_street_override": (
                    used
                    and on_same_street
                    and distance_m is not None
                    and distance_m > radius_m
                ),
                "_same_condo": same_condo,
                # extra para o pricing logo abaixo
                "_listed_price": listing.get("listed_price"),
                "_area_total_m2": listing.get("area_total_m2"),
                "_condo_name": listing.get("condo_name"),
            }
        )

    n_used = sum(1 for s in scored if s["used"])
    n_same_street_rescued = sum(1 for s in scored if s.get("_same_street_override"))
    # Breakdown por categoria do motivo de rejeição (útil para tuning).
    rej_buckets: dict[str, int] = {}
    for s in scored:
        if s["used"]:
            continue
        reason = s["rejection_reason"] or "outro"
        # Agrupa por prefixo (ex.: "distance=3200m > 2500m" → "distance>radius").
        if "sem preço" in reason or "sem area" in reason:
            key = "sem_preco_ou_area"
        elif reason.startswith("reliability="):
            key = "baixa_reliability"
        elif reason.startswith("property_type"):
            key = "tipo_diferente"
        elif reason.startswith("distance="):
            key = "fora_do_raio"
        else:
            key = "outro"
        rej_buckets[key] = rej_buckets.get(key, 0) + 1

    logger.info(
        "cma.score.ok",
        n_total=len(scored),
        n_used=n_used,
        n_rejected=len(scored) - n_used,
        radius_m=radius_m,
        n_same_street_rescued=n_same_street_rescued or None,
        rejection_breakdown=rej_buckets or None,
    )
    return {"scored_comparables": scored}


# ---------------------------------------------------------------------------
# 8) check_minimum_or_expand — decide se precisa abrir raio / mudar estratégia
# ---------------------------------------------------------------------------
def node_check_minimum(state: ComparablesState) -> dict[str, Any]:
    """Se não há comparáveis suficientes, expande raio (mesma estratégia)
    OU passa para a próxima estratégia.

    Retorna DOIS flags possíveis (lidos por ``_route_after_check``):

    * ``should_retry_score``  → só re-roda `score_similarity` com novo raio
      (mesma estratégia, ZERO custo externo). Caminho preferido enquanto
      o plano de raios não acabou.
    * ``should_retry_search`` → refaz busca/scrape/LLM porque trocamos
      para uma estratégia mais ampla. Custo: nova chamada Firecrawl + LLM.

    Quando os dois são False, o pipeline vai para `estimate_price`.
    """
    settings = get_settings()
    scored = state.get("scored_comparables") or []
    n_used = sum(1 for s in scored if s["used"])
    target = state.get("target") or {}

    # Reset explícito (importante: TypedDict carrega valor anterior entre
    # iterações do loop; sem reset, um True velho contaminaria o próximo passo).
    base_reset = {"should_retry_score": False, "should_retry_search": False}

    if n_used >= settings.cma_min_comparables_acceptable:
        return base_reset

    # 1) Tenta expandir raio na mesma estratégia. NADA muda exceto radius_m
    # → o conditional edge nos manda direto para `score_similarity`.
    plan = radius_plan(target.get("city"), target.get("state"))
    cur_radius = state.get("search_radius_m") or plan[0]
    bigger = next((r for r in plan if r > cur_radius), None)

    if bigger:
        logger.info(
            "cma.expand.radius",
            from_=cur_radius,
            to=bigger,
            n_used=n_used,
            min_required=settings.cma_min_comparables_acceptable,
        )
        return {**base_reset, "search_radius_m": bigger, "should_retry_score": True}

    # 2) Esgotou o plano de raios → troca de estratégia (full search).
    cur_strategy = state.get("search_strategy") or "neighborhood"
    nxt = next_strategy(cur_strategy)
    if nxt and nxt != "radius":
        new_queries = build_queries(target, strategy=nxt)
        if new_queries:
            logger.info(
                "cma.expand.strategy",
                from_=cur_strategy,
                to=nxt,
                n_used=n_used,
            )
            return {
                **base_reset,
                "search_strategy": nxt,
                "search_radius_m": plan[0],
                "search_queries": new_queries,
                "should_retry_search": True,
            }

    # 3) Sem mais cartas: segue para o pricing com o que tiver (vai
    # provavelmente cair em INSUFFICIENT, mas o usuário verá o motivo).
    logger.info("cma.expand.exhausted", n_used=n_used)
    return base_reset


# ---------------------------------------------------------------------------
# 9) estimate_price — calcula valuation final
# ---------------------------------------------------------------------------
def node_estimate_price(state: ComparablesState) -> dict[str, Any]:
    from app.agents.comparables.pricing import (
        Comparable,
        detect_bimodal_ppm2,
        effective_target_area_m2,
        estimate_price,
    )

    settings = get_settings()
    scored = state.get("scored_comparables") or []
    target = state.get("target") or {}

    used = [s for s in scored if s["used"]]

    comps: list[Comparable] = []
    for s in used:
        price = float(s["_listed_price"])
        area = float(s["_area_total_m2"])
        if area <= 0:
            continue
        comps.append(
            Comparable(
                listing_id=s["listing_id"],
                ppm2=price / area,
                weight=float(s["weight"]),
                same_building=bool(s.get("_same_condo")),
            )
        )

    target_area_m2, area_source = effective_target_area_m2(target)
    legacy_area = target.get("area_total_m2")
    logger.info(
        "cma.area.effective",
        property_type=(target.get("property_type") or "").lower() or None,
        area_source=area_source,
        target_area_m2=target_area_m2,
        legacy_area_total_m2=legacy_area,
        diverged=(
            area_source not in (None, "area_total_m2")
            and legacy_area is not None
            and target_area_m2 is not None
            and abs(float(legacy_area) - float(target_area_m2)) > 0.5
        ),
    )

    val = estimate_price(
        target_area_m2=target_area_m2,
        comparables=comps,
        min_acceptable=settings.cma_min_comparables_acceptable,
        min_confident=settings.cma_min_comparables_confident,
        property_type=target.get("property_type"),
    )

    # Bimodalidade — sinal de que a amostra mistura prédios distintos.
    # Não rebaixa a confidence aqui (já é responsabilidade do classifier),
    # mas deixa um warning humano-legível na valuation. O AGENTE 3 lê esse
    # warning e o usuário vê na UI da CMA.
    extra_warnings: list[str] = []
    target_condo = (target.get("condo_name") or "").strip()
    same_building_count = sum(1 for c in comps if c.same_building)
    if (
        same_building_count < 3
        and detect_bimodal_ppm2(comps, gap_pct=0.30, min_each_side=2)
    ):
        if target_condo:
            extra_warnings.append(
                f"Comparáveis vêm de prédios com perfis de preço distintos — "
                f"verifique se '{target_condo}' bate com o prédio do alvo "
                f"ou refine o nome."
            )
        else:
            extra_warnings.append(
                "Comparáveis vêm de prédios com perfis de preço distintos — "
                "informe o nome do condomínio do imóvel-alvo (campo "
                "'Nome do prédio') para uma estimativa mais precisa."
            )
        logger.info(
            "cma.bimodal.detected",
            n=len(comps),
            same_building_count=same_building_count,
            target_condo=target_condo or None,
        )

    if val.method == "same_building_median_ppm2":
        logger.info(
            "cma.same_building.applied",
            n=val.comparables_used,
            confidence=val.confidence,
            target_condo=target_condo or None,
        )

    # Cap de comparáveis salvos no join (mantém top-N por peso).
    sorted_used = sorted(used, key=lambda s: s["weight"], reverse=True)
    capped_used_ids = {s["listing_id"] for s in sorted_used[: settings.cma_max_comparables_kept]}
    for s in scored:
        if s["used"] and s["listing_id"] not in capped_used_ids:
            s["used"] = False
            s["rejection_reason"] = "trim: fora do top-N por peso"

    out_warnings = list(state.get("warnings") or []) + extra_warnings
    return {
        "estimated_price": val.estimated_price,
        "price_lower_bound": val.price_lower_bound,
        "price_upper_bound": val.price_upper_bound,
        "ppm2_estimated": val.ppm2_estimated,
        "confidence": val.confidence,
        "scored_comparables": scored,
        "warnings": out_warnings,
        "pricing_method": val.method,
    }


# ---------------------------------------------------------------------------
# 10) persist_valuation — grava na tabela valuations + valuation_comparables
# ---------------------------------------------------------------------------
def node_persist(state: ComparablesState) -> dict[str, Any]:
    sb = get_supabase_service()
    scored = state.get("scored_comparables") or []
    n_used = sum(1 for s in scored if s["used"])
    n_rejected = len(scored) - n_used

    payload = {
        "property_id": state["property_id"],
        "agent_run_id": state.get("agent_run_id"),
        "estimated_price": state.get("estimated_price"),
        "price_lower_bound": state.get("price_lower_bound"),
        "price_upper_bound": state.get("price_upper_bound"),
        "ppm2_estimated": state.get("ppm2_estimated"),
        "confidence": state.get("confidence", "INSUFFICIENT"),
        "method": state.get("pricing_method") or "weighted_median_ppm2",
        "comparables_used": n_used,
        "comparables_rejected": n_rejected,
        "search_radius_m": state.get("search_radius_m"),
        "search_strategy": state.get("search_strategy"),
        "firecrawl_calls": state.get("firecrawl_calls", 0),
        "llm_calls": state.get("llm_calls", 0),
        "cost_estimate_brl": state.get("cost_estimate_brl"),
        "metadata": {
            "warnings": state.get("warnings"),
            "candidates_total": len(state.get("candidate_urls") or []),
        },
        "errors": state.get("errors") or None,
    }
    val = sb.insert_valuation(payload)
    valuation_id = val["id"]

    # Join com pesos. Strip dos prefixos privados antes de gravar.
    # Defesa em profundidade: dedup por listing_id (a PK composta da tabela
    # `valuation_comparables` é (valuation_id, listing_id) — duplicatas
    # quebrariam o INSERT inteiro, perdendo TODOS os comparáveis dessa run).
    # A dedup primária está em `node_enrich_geo`; aqui é só rede de segurança.
    seen_listing_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    n_skipped = 0
    for s in scored:
        lid = s["listing_id"]
        if lid in seen_listing_ids:
            n_skipped += 1
            continue
        seen_listing_ids.add(lid)
        rows.append(
            {
                "listing_id": lid,
                "distance_m": s["distance_m"],
                "similarity_score": s["similarity_score"],
                "weight": s["weight"],
                "used": s["used"],
                "rejection_reason": s["rejection_reason"],
            }
        )
    if n_skipped:
        logger.warning(
            "cma.persist.dedup_safety_net",
            n_skipped=n_skipped,
            valuation_id=valuation_id,
        )
    sb.insert_valuation_comparables(valuation_id, rows)

    return {"valuation_id": valuation_id}
