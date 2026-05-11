"""Nós do grafo do Agente 1.

Cada nó:
- recebe ``ScraperState`` (dict-like)
- realiza UMA responsabilidade
- retorna um dict parcial que será mesclado ao state

Erros não-fatais são adicionados em ``state['warnings']`` e o pipeline segue.
Erros fatais levantam exceção, e o roteamento decide se aborta.
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from app.agents.scraper.prompts import build_extraction_messages
from app.agents.scraper.schemas import ExtractedAuctionData
from app.agents.scraper.state import ScraperState
from app.agents.scraper.utils import (
    sanitize_image_url,
    sanitize_neighborhood,
    sanitize_number,
    sanitize_street,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.firecrawl_service import FirecrawlScrapeError, get_firecrawl_service
from app.services.google_maps_service import GoogleMapsError, get_google_maps_service
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _append(state: ScraperState, key: str, value: str) -> list[str]:
    bucket = list(state.get(key, []) or [])
    bucket.append(value)
    return bucket


def _ewkt_point(lng: float, lat: float) -> str:
    """Converte (lng, lat) em EWKT — formato aceito pelo PostGIS via PostgREST."""
    return f"SRID=4326;POINT({lng} {lat})"


# --------------------------------------------------------------------------- #
# Nó 1 — scrape_url
# --------------------------------------------------------------------------- #
def node_scrape_url(state: ScraperState) -> dict[str, Any]:
    url = state["url"]
    logger.info("agent.scraper.node.scrape_url", url=url)

    try:
        result = get_firecrawl_service().scrape_to_markdown(url)
    except FirecrawlScrapeError as exc:
        return {"errors": _append(state, "errors", f"firecrawl: {exc}")}

    return {
        "raw_markdown": result["markdown"],
        "page_metadata": result.get("metadata") or {},
    }


# --------------------------------------------------------------------------- #
# Nó 2 — extract_data (LLM com structured output)
# --------------------------------------------------------------------------- #
def node_extract_data(state: ScraperState) -> dict[str, Any]:
    if not state.get("raw_markdown"):
        return {"errors": _append(state, "errors", "extract: markdown ausente")}

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key.get_secret_value(),
        temperature=0,
    ).with_structured_output(ExtractedAuctionData)

    messages = build_extraction_messages(url=state["url"], markdown=state["raw_markdown"])
    logger.info("agent.scraper.node.extract_data", model=settings.openai_model)

    try:
        extracted: ExtractedAuctionData = llm.invoke(messages)  # type: ignore[assignment]
    except Exception as exc:
        return {"errors": _append(state, "errors", f"openai: {exc}")}

    return {"extracted": extracted}


# --------------------------------------------------------------------------- #
# Nó 3 — validate_address
# --------------------------------------------------------------------------- #
# Verdicts do Address Validation que tornam o `formattedAddress` não confiável
# para alimentar o Geocoding diretamente (caímos no fallback por CEP).
_REJECTED_NEXT_ACTIONS: frozenset[str] = frozenset({"FIX"})
_REJECTED_GRANULARITIES: frozenset[str] = frozenset({"OTHER"})


def _is_validation_rejected(verdict: dict[str, Any]) -> bool:
    next_action = (verdict or {}).get("possibleNextAction") or ""
    granularity = (verdict or {}).get("validationGranularity") or ""
    return (
        next_action in _REJECTED_NEXT_ACTIONS
        or granularity in _REJECTED_GRANULARITIES
    )


def node_validate_address(state: ScraperState) -> dict[str, Any]:
    extracted = state.get("extracted")
    if not extracted:
        return {"errors": _append(state, "errors", "validate: sem extracted")}

    addr = extracted.address

    # 1) Sanitização DEFENSIVA do bairro: mesmo que a LLM retorne o nome com
    # prefixos espúrios (LOTEAMENTO, CONJUNTO HABITACIONAL, etc.), removemos
    # antes de mandar pro Google. Isso evita o bug do Pindamonhangaba/Sorocaba.
    clean_neighborhood = sanitize_neighborhood(addr.neighborhood)

    # Sanitização de logradouro (DF: 'QUADRA QN 407' → 'QN 407') e de número
    # ('S/N', 'SN' → None — campos realmente sem número).
    clean_street = sanitize_street(addr.street)
    clean_number = sanitize_number(addr.number)

    # 2) NUNCA enviamos `complement` (apto/bloco/andar/edifício) ao Google.
    # Strings tipo "Apartamento 33, 3º andar, Edifício X" confundem o
    # Address Validation, que pode atribuir CEP/cidade errados. O complemento
    # fica preservado em `extracted.address.complement` e vai para a coluna
    # `complement` do banco no nó de persistência.
    address_lines: list[str] = []
    line1_parts = [p for p in [clean_street, clean_number] if p]
    if line1_parts:
        address_lines.append(", ".join(line1_parts))
    if clean_neighborhood:
        address_lines.append(clean_neighborhood)

    if not address_lines and addr.full_address:
        address_lines.append(addr.full_address)

    if not address_lines:
        return {
            "warnings": _append(state, "warnings", "validate: endereço extraído vazio"),
            "validation_rejected": True,
        }

    try:
        result = get_google_maps_service().validate_address(
            address_lines=address_lines,
            postal_code=addr.postal_code,
            locality=addr.city,
            administrative_area=addr.state,
        )
    except GoogleMapsError as exc:
        return {
            "warnings": _append(state, "warnings", f"validate: {exc}"),
            "validation_rejected": True,
        }

    # 3) Avalia o veredito ANTES de confiar na resposta.
    verdict = result.get("verdict") or {}
    rejected = _is_validation_rejected(verdict)

    # Extrai endereço normalizado (mesmo se rejected, é útil pra auditoria)
    address = result.get("address", {})
    components = {
        c.get("componentType"): c.get("componentName", {}).get("text")
        for c in address.get("addressComponents", [])
    }
    normalized: dict[str, Any] = {
        "formatted": address.get("formattedAddress"),
        "street": components.get("route"),
        "number": components.get("street_number"),
        "neighborhood": components.get("sublocality") or components.get("sublocality_level_1"),
        "city": components.get("locality") or components.get("administrative_area_level_2"),
        "state": components.get("administrative_area_level_1"),
        "postal_code": components.get("postal_code"),
        "country": components.get("country") or "BR",
    }

    update: dict[str, Any] = {
        "address_validation": result,
        "normalized_address": normalized,
        "validation_rejected": rejected,
        "validation_granularity": verdict.get("validationGranularity") or "",
    }
    if rejected:
        next_action = verdict.get("possibleNextAction")
        granularity = verdict.get("validationGranularity")
        update["warnings"] = _append(
            state,
            "warnings",
            f"validate: verdict ruim "
            f"(possibleNextAction={next_action}, validationGranularity={granularity}); "
            "tentaremos fallback por CEP no geocode.",
        )

    return update


# --------------------------------------------------------------------------- #
# Nó 4 — geocode
# --------------------------------------------------------------------------- #
_CONFIDENCE_MAP: dict[str, str] = {
    "ROOFTOP": "HIGH",
    "RANGE_INTERPOLATED": "MEDIUM",
    "GEOMETRIC_CENTER": "MEDIUM",
    "APPROXIMATE": "LOW",
}

# Granularidades do Address Validation que indicam endereço de "rua/quadra"
# legítimo — quando o Geocoding devolve APPROXIMATE para esses, é o melhor
# que se consegue (DF e similares). Não é "deu errado": é "esse endereço
# não tem número de casa".
_ROUTE_LEVEL_GRANULARITIES: frozenset[str] = frozenset({"ROUTE", "BLOCK"})


def _classify_confidence(location_type: str, validation_granularity: str) -> str:
    """Decide o `geocoding_confidence` final do caminho A.

    Refinamento sobre `_CONFIDENCE_MAP`:
        APPROXIMATE + ROUTE/BLOCK  → MEDIUM  (endereço de quadra; DF, áreas rurais)
        APPROXIMATE + outros        → LOW    (geocoding genuinamente impreciso)
    """
    base = _CONFIDENCE_MAP.get(location_type, "LOW")
    if base == "LOW" and validation_granularity in _ROUTE_LEVEL_GRANULARITIES:
        return "MEDIUM"
    return base


def _try_geocode(query: str) -> tuple[dict[str, Any], tuple[float, float]] | None:
    """Geocodifica e retorna ``(result, (lat, lng))`` ou ``None`` se nada usável."""
    if not query or not query.strip():
        return None
    try:
        gres = get_google_maps_service().geocode(query)
    except GoogleMapsError as exc:
        logger.warning("geocode.exception", query=query, error=str(exc))
        return None
    if not gres:
        return None
    coords = get_google_maps_service().extract_lat_lng(gres)
    if not coords:
        return None
    return gres, coords


def _build_postal_query(extracted: ExtractedAuctionData) -> str | None:
    """Monta uma query 'CEP X, Cidade, UF, Brasil' (fallback seguro)."""
    addr = extracted.address
    if not addr.postal_code:
        return None
    parts = [f"CEP {addr.postal_code}"]
    if addr.city:
        parts.append(addr.city)
    if addr.state:
        parts.append(addr.state)
    parts.append("Brasil")
    return ", ".join(parts)


def node_geocode(state: ScraperState) -> dict[str, Any]:
    extracted = state.get("extracted")
    normalized = state.get("normalized_address") or {}
    rejected = bool(state.get("validation_rejected"))

    # ------------------------------------------------------------------ #
    # CAMINHO A — Address Validation aprovou: usa o `formatted` normalizado
    # ------------------------------------------------------------------ #
    if not rejected:
        primary = (
            normalized.get("formatted")
            or (extracted.address.full_address if extracted else None)
        )
        attempt = _try_geocode(primary or "")
        if attempt is not None:
            gres, (lat, lng) = attempt
            location_type = (gres.get("geometry") or {}).get("location_type", "APPROXIMATE")
            confidence = _classify_confidence(
                location_type,
                state.get("validation_granularity") or "",
            )
            return {
                "geocode_result": gres,
                "latitude": lat,
                "longitude": lng,
                "google_place_id": gres.get("place_id"),
                "geocoding_confidence": confidence,
            }
        # se o caminho A falhou, ainda tentamos o B (fallback por CEP)

    # ------------------------------------------------------------------ #
    # CAMINHO B — fallback por CEP (não vai pra cidade errada)
    # ------------------------------------------------------------------ #
    if extracted is None:
        return {
            "warnings": _append(state, "warnings", "geocode: sem extracted para fallback"),
        }

    postal_query = _build_postal_query(extracted)
    if not postal_query:
        return {
            "warnings": _append(
                state,
                "warnings",
                "geocode: validação rejeitada e sem CEP para fallback — "
                "location ficará nulo.",
            ),
        }

    attempt = _try_geocode(postal_query)
    if attempt is not None:
        gres, (lat, lng) = attempt
        return {
            "geocode_result": gres,
            "latitude": lat,
            "longitude": lng,
            "google_place_id": gres.get("place_id"),
            # Sempre POSTAL_CODE quando viemos do fallback, independente do
            # location_type que o Google retornar para o CEP.
            "geocoding_confidence": "POSTAL_CODE",
            "warnings": _append(
                state,
                "warnings",
                f"geocode: usando fallback por CEP ({postal_query}); confidence=POSTAL_CODE",
            ),
        }

    # ------------------------------------------------------------------ #
    # CAMINHO C — último recurso: BrasilAPI / ViaCEP.
    # Quando Google falha em A e B, ainda dá pra ancorar o imóvel a uma
    # cidade/UF via consulta gratuita do CEP. BrasilAPI v2 às vezes traz
    # coordenadas via OpenStreetMap; ViaCEP é fallback só com endereço.
    # Confidence rebaixada para POSTAL_CODE (idem caminho B).
    # ------------------------------------------------------------------ #
    from app.services.brasilapi_service import get_brasilapi_service

    cep_data = get_brasilapi_service().fetch_cep(extracted.address.postal_code or "")
    if cep_data is None:
        return {
            "warnings": _append(
                state,
                "warnings",
                f"geocode: fallback por CEP falhou ({postal_query}) e "
                "BrasilAPI/ViaCEP também — location ficará nulo.",
            ),
        }

    update: dict[str, Any] = {
        "warnings": _append(
            state,
            "warnings",
            f"geocode: usando BrasilAPI/ViaCEP ({cep_data['source']}) — "
            "confidence=POSTAL_CODE",
        ),
        "geocoding_confidence": "POSTAL_CODE",
    }
    if cep_data.get("lat") is not None and cep_data.get("lng") is not None:
        update["latitude"] = cep_data["lat"]
        update["longitude"] = cep_data["lng"]
    return update


# --------------------------------------------------------------------------- #
# Nó 5 — persist
# --------------------------------------------------------------------------- #
def node_persist(state: ScraperState) -> dict[str, Any]:
    extracted = state.get("extracted")
    if not extracted:
        return {"errors": _append(state, "errors", "persist: sem dados extraídos")}

    sb = get_supabase_service()

    auctioneer_id: str | None = None
    if extracted.auctioneer_slug:
        try:
            auctioneer_id = sb.get_auctioneer_id_by_slug(extracted.auctioneer_slug)
        except SupabaseError as exc:
            logger.warning("persist.auctioneer.lookup_failed", error=str(exc))

    normalized = state.get("normalized_address") or {}
    addr = extracted.address

    payload: dict[str, Any] = {
        "source_url": state["url"],
        "auctioneer_id": auctioneer_id,
        "auctioneer_lot_id": extracted.auctioneer_lot_id,
        "auctioneer_name": (extracted.auctioneer_name or "").strip() or None,
        "title": extracted.title,
        "description": extracted.description,
        "property_type": extracted.property_type,
        "image_url": sanitize_image_url(extracted.image_url),
        # endereço (preferindo o normalizado; fallback no extraído)
        "address_full": normalized.get("formatted") or addr.full_address,
        "street": normalized.get("street") or addr.street,
        "number": normalized.get("number") or addr.number,
        "complement": addr.complement,
        "neighborhood": normalized.get("neighborhood") or addr.neighborhood,
        "city": normalized.get("city") or addr.city,
        "state": (normalized.get("state") or addr.state or "")[:2].upper() or None,
        "postal_code": normalized.get("postal_code") or addr.postal_code,
        "country": normalized.get("country") or "BR",
        # geo
        "google_place_id": state.get("google_place_id"),
        "geocoding_confidence": state.get("geocoding_confidence"),
        "address_validation": state.get("address_validation"),
        # físico
        "area_total_m2": extracted.area_total_m2,
        "area_built_m2": extracted.area_built_m2,
        "bedrooms": extracted.bedrooms,
        "bathrooms": extracted.bathrooms,
        "parking_spaces": extracted.parking_spaces,
        # valores
        "appraisal_value": extracted.appraisal_value,
        "minimum_bid_first": extracted.minimum_bid_first,
        "minimum_bid_second": extracted.minimum_bid_second,
        "current_bid": extracted.current_bid,
        # custos do edital (alimentam o Agente 3)
        "iptu_arrears": extracted.iptu_arrears,
        "condo_arrears": extracted.condo_arrears,
        "auctioneer_fee_pct": extracted.auctioneer_fee_pct,
        # datas
        "first_auction_at": (
            extracted.first_auction_at.isoformat() if extracted.first_auction_at else None
        ),
        "second_auction_at": (
            extracted.second_auction_at.isoformat() if extracted.second_auction_at else None
        ),
        # jurídico
        "legal_status": extracted.legal_status,
        "occupancy_status": extracted.occupancy_status,
        "encumbrances": (
            {"summary": extracted.encumbrances_summary}
            if extracted.encumbrances_summary
            else None
        ),
        # auditoria
        "raw_markdown": state.get("raw_markdown"),
        "raw_extraction": extracted.model_dump(mode="json"),
        "errors": state.get("errors") or None,
    }

    has_geo = (
        state.get("latitude") is not None and state.get("longitude") is not None
    )
    if has_geo:
        payload["location"] = _ewkt_point(state["longitude"], state["latitude"])
        payload["status"] = "scraped"
    else:
        # Address Validation rejeitou + fallback por CEP falhou → não salvamos
        # `location` nem `geocoding_confidence` espúrios. Marcamos com status
        # explícito para que pipelines downstream possam filtrar.
        payload["geocoding_confidence"] = "REJECTED"
        payload["status"] = "geo_unconfirmed"

    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        saved = sb.upsert_property(payload)
    except SupabaseError as exc:
        return {"errors": _append(state, "errors", f"persist: {exc}")}

    return {"property_id": saved["id"], "saved_property": saved}
