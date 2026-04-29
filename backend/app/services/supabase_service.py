"""Wrapper para o cliente Supabase (PostgREST + Auth).

Usamos a ``service_role_key`` no backend para bypass de RLS em escritas.
Para escrever um ``geography(Point, 4326)`` via REST, usamos o helper
``ST_SetSRID(ST_MakePoint(lng, lat), 4326)`` através de uma RPC dedicada
ou enviamos como WKT/EWKT em um update SQL bruto.

Aqui adotamos uma abordagem pragmática: persistimos lat/lng como colunas
auxiliares no JSON ``raw_extraction`` e, para o ponto PostGIS, usamos a
RPC ``upsert_property_with_location`` (ver schema.sql) — opcional.

Caso a RPC não exista, o serviço faz upsert na tabela ``properties`` sem
o campo ``location`` e em seguida atualiza ``location`` via ``rpc('exec_sql', …)``
NÃO, melhor mantermos simples: salvamos o ponto como WKT EWKT string, que
o PostgREST converte se a coluna for ``geography``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SupabaseError(RuntimeError):
    """Erro ao falar com Supabase."""


class SupabaseService:
    """Camada de acesso a dados orientada a casos de uso do projeto."""

    def __init__(self, url: str, service_role_key: str) -> None:
        self._client: Client = create_client(url, service_role_key)

    # ------------------------------------------------------------------ #
    # Auctioneers
    # ------------------------------------------------------------------ #
    def get_auctioneer_id_by_slug(self, slug: str) -> str | None:
        try:
            res = (
                self._client.table("auctioneers")
                .select("id")
                .eq("slug", slug)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha ao consultar auctioneers: {exc}") from exc

        rows = res.data or []
        return rows[0]["id"] if rows else None

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #
    def upsert_property(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Upsert por ``source_url`` (constraint UNIQUE).

        Espera ``payload['location']`` como string EWKT, ex.:
        ``'SRID=4326;POINT(-46.6333 -23.5505)'`` — o PostgREST aceita esse formato
        para colunas ``geography``.
        """
        logger.info("supabase.property.upsert", source_url=payload.get("source_url"))
        try:
            res = (
                self._client.table("properties")
                .upsert(payload, on_conflict="source_url")
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha no upsert de properties: {exc}") from exc

        rows = res.data or []
        if not rows:
            raise SupabaseError("Upsert não retornou registros.")
        return rows[0]

    def delete_property(self, property_id: str) -> bool:
        """Deleta um imóvel por ID. Retorna True se algo foi deletado.

        Os ``agent_runs`` que apontam para este imóvel ficam preservados
        com ``property_id = NULL`` (configurado via ``ON DELETE SET NULL``
        no schema), mantendo a auditoria histórica.
        """
        logger.info("supabase.property.delete", id=property_id)
        try:
            res = (
                self._client.table("properties")
                .delete()
                .eq("id", property_id)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha ao deletar property {property_id}: {exc}") from exc
        return bool(res.data)

    def get_property_by_id(self, property_id: str) -> dict[str, Any] | None:
        """Lê um property por ID. Retorna None se não existe."""
        try:
            res = (
                self._client.table("properties")
                .select("*")
                .eq("id", property_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha ao consultar property {property_id}: {exc}") from exc
        rows = res.data or []
        return rows[0] if rows else None

    def list_properties(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            query = (
                self._client.table("properties")
                .select("*")
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
            )
            if status:
                query = query.eq("status", status)
            res = query.execute()
        except Exception as exc:
            raise SupabaseError(f"Falha ao listar properties: {exc}") from exc
        return res.data or []

    # ------------------------------------------------------------------ #
    # Agent runs (auditoria)
    # ------------------------------------------------------------------ #
    def insert_agent_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            res = self._client.table("agent_runs").insert(payload).execute()
        except Exception as exc:
            raise SupabaseError(f"Falha ao inserir agent_run: {exc}") from exc
        rows = res.data or []
        return rows[0] if rows else {}

    def update_agent_run(self, run_id: str, payload: dict[str, Any]) -> None:
        try:
            self._client.table("agent_runs").update(payload).eq("id", run_id).execute()
        except Exception as exc:
            raise SupabaseError(f"Falha ao atualizar agent_run: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Listings (AGENTE 2 — comparáveis-candidatos)
    # ------------------------------------------------------------------ #
    def get_listings_by_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        """Carrega listings já scrapeados (cache do AGENTE 2)."""
        if not urls:
            return []
        try:
            res = (
                self._client.table("listings")
                .select("*")
                .in_("source_url", urls)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha ao consultar listings: {exc}") from exc
        return res.data or []

    def upsert_listing(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Upsert por ``source_url``. ``location`` em EWKT como em properties."""
        logger.info("supabase.listing.upsert", source_url=payload.get("source_url"))
        try:
            res = (
                self._client.table("listings")
                .upsert(payload, on_conflict="source_url")
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha no upsert de listings: {exc}") from exc
        rows = res.data or []
        if not rows:
            raise SupabaseError("Upsert de listing não retornou registros.")
        return rows[0]

    # ------------------------------------------------------------------ #
    # Valuations (AGENTE 2 — resultado da CMA)
    # ------------------------------------------------------------------ #
    def insert_valuation(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            res = self._client.table("valuations").insert(payload).execute()
        except Exception as exc:
            raise SupabaseError(f"Falha ao inserir valuation: {exc}") from exc
        rows = res.data or []
        if not rows:
            raise SupabaseError("Insert de valuation não retornou registros.")
        return rows[0]

    def insert_valuation_comparables(
        self, valuation_id: str, comparables: list[dict[str, Any]]
    ) -> None:
        """Insere o join valuation_comparables em batch (não-fatal se vazio)."""
        if not comparables:
            return
        rows = [{"valuation_id": valuation_id, **c} for c in comparables]
        try:
            self._client.table("valuation_comparables").insert(rows).execute()
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao inserir valuation_comparables: {exc}"
            ) from exc

    def list_valuations_by_property(
        self, property_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        try:
            res = (
                self._client.table("valuations")
                .select("*")
                .eq("property_id", property_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha ao listar valuations: {exc}") from exc
        return res.data or []

    def get_valuation_with_comparables(self, valuation_id: str) -> dict[str, Any] | None:
        """Devolve a valuation + lista de comparáveis com dados básicos do listing."""
        try:
            val_res = (
                self._client.table("valuations")
                .select("*")
                .eq("id", valuation_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha ao consultar valuation: {exc}") from exc
        rows = val_res.data or []
        if not rows:
            return None
        valuation = rows[0]

        try:
            comp_res = (
                self._client.table("valuation_comparables")
                .select(
                    "distance_m, similarity_score, weight, used, rejection_reason, "
                    "listings(id, source, source_url, title:condo_name, "
                    "property_type, area_total_m2, bedrooms, bathrooms, "
                    "parking_spaces, neighborhood, city, state, latitude, "
                    "longitude, listed_price, geocoding_confidence)"
                )
                .eq("valuation_id", valuation_id)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao listar comparables da valuation {valuation_id}: {exc}"
            ) from exc
        valuation["comparables"] = comp_res.data or []
        return valuation


@lru_cache(maxsize=1)
def get_supabase_service() -> SupabaseService:
    settings = get_settings()
    return SupabaseService(
        url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key.get_secret_value(),
    )
