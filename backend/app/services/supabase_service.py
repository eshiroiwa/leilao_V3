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


@lru_cache(maxsize=1)
def get_supabase_service() -> SupabaseService:
    settings = get_settings()
    return SupabaseService(
        url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key.get_secret_value(),
    )
