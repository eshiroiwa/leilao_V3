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

import math
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

    def update_property(
        self, property_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Aplica um patch (dict) num imóvel. Retorna a row atualizada ou None.

        Use para edições do usuário no UI (ex.: definir ``condo_name``
        manualmente, corrigir áreas ocultadas pelo edital). Mantemos o
        contrato simples — o caller é responsável por sanitizar o payload
        e remover chaves não permitidas.
        """
        if not payload:
            return self.get_property_by_id(property_id)
        logger.info(
            "supabase.property.update", id=property_id, fields=list(payload)
        )
        try:
            res = (
                self._client.table("properties")
                .update(payload)
                .eq("id", property_id)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao atualizar property {property_id}: {exc}"
            ) from exc
        rows = res.data or []
        return rows[0] if rows else None

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
        """Upsert idempotente de um listing.

        Estratégia de dedup (em ordem de preferência):

        1. ``(source, external_id)`` — quando o anúncio tem id canônico no
           portal (ex.: ``id-12345`` no path do VivaReal/ZAP). Esse é o
           caso PRINCIPAL: previne duplicatas mesmo quando o ``source_url``
           muda entre runs (synthetic → URL real, canonicalização, etc.).
           Faz SELECT para achar a row existente; se achar, faz UPDATE; se
           não, faz INSERT.

        2. ``source_url`` — fallback para casos sem ``external_id``
           (geralmente cards sem URL real, com source_url synthetic).
           Usa ``upsert(on_conflict="source_url")`` direto.

        Ambos os caminhos garantem que o backend é o único que decide
        a granularidade de "anúncio" — o índice único parcial criado na
        migration 004 protege a tabela mesmo se a aplicação errar.
        """
        source = payload.get("source")
        external_id = payload.get("external_id")
        source_url = payload.get("source_url")
        logger.info(
            "supabase.listing.upsert",
            source_url=source_url,
            external_id=external_id,
            source=source,
        )

        # ---- Caminho 1: dedup por (source, external_id) -------------------
        if source and external_id:
            try:
                existing = (
                    self._client.table("listings")
                    .select("id, source_url")
                    .eq("source", source)
                    .eq("external_id", external_id)
                    .limit(1)
                    .execute()
                )
            except Exception as exc:
                raise SupabaseError(
                    f"Falha ao buscar listing existente: {exc}"
                ) from exc

            rows_existing = existing.data or []
            if rows_existing:
                row_id = rows_existing[0]["id"]
                old_url = rows_existing[0].get("source_url")
                # Atualiza tudo (inclusive source_url, para "promover" um
                # synthetic antigo à URL real quando o novo run achar o link).
                update_payload = {k: v for k, v in payload.items() if k != "id"}
                try:
                    res = (
                        self._client.table("listings")
                        .update(update_payload)
                        .eq("id", row_id)
                        .execute()
                    )
                except Exception as exc:
                    raise SupabaseError(
                        f"Falha ao atualizar listing existente: {exc}"
                    ) from exc
                rows = res.data or []
                if not rows:
                    raise SupabaseError("Update de listing não retornou registros.")
                if old_url and old_url != source_url:
                    logger.info(
                        "supabase.listing.url_promoted",
                        external_id=external_id,
                        old_url=old_url,
                        new_url=source_url,
                    )
                return rows[0]
            # Não achou — cai no caminho 2 (INSERT via upsert por source_url).

        # ---- Caminho 2: upsert por source_url -----------------------------
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

    def get_latest_valuation_for_property(
        self, property_id: str
    ) -> dict[str, Any] | None:
        """Atalho: a valuation mais recente associada a um property_id."""
        try:
            res = (
                self._client.table("valuations")
                .select("*")
                .eq("property_id", property_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao consultar última valuation: {exc}"
            ) from exc
        rows = res.data or []
        return rows[0] if rows else None

    # ------------------------------------------------------------------ #
    # Opportunity analyses (AGENTE 3)
    # ------------------------------------------------------------------ #
    def insert_opportunity_analysis(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Insere uma análise de oportunidade. Retorna a row criada."""
        logger.info(
            "supabase.opportunity.insert",
            property_id=payload.get("property_id"),
            verdict=payload.get("verdict"),
        )
        try:
            res = (
                self._client.table("opportunity_analyses")
                .insert(payload)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao inserir opportunity_analysis: {exc}"
            ) from exc
        rows = res.data or []
        if not rows:
            raise SupabaseError(
                "Insert de opportunity_analysis não retornou registros."
            )
        return rows[0]

    def list_opportunity_analyses(
        self, property_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        try:
            res = (
                self._client.table("opportunity_analyses")
                .select("*")
                .eq("property_id", property_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao listar opportunity_analyses: {exc}"
            ) from exc
        return res.data or []

    def get_opportunity_analysis(
        self, analysis_id: str
    ) -> dict[str, Any] | None:
        try:
            res = (
                self._client.table("opportunity_analyses")
                .select("*")
                .eq("id", analysis_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao consultar opportunity_analysis {analysis_id}: {exc}"
            ) from exc
        rows = res.data or []
        return rows[0] if rows else None

    # ------------------------------------------------------------------ #
    # Dashboard helpers — agregações leves para a home
    # ------------------------------------------------------------------ #
    def list_property_ids_with_valuations(self) -> set[str]:
        """Conjunto de ``property_id`` que possuem ao menos uma valuation.

        Faz um único select projetando só o ``property_id`` para reduzir
        payload — útil para calcular "pendentes de avaliação" no dashboard.
        """
        try:
            res = (
                self._client.table("valuations")
                .select("property_id")
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao listar property_ids de valuations: {exc}"
            ) from exc
        rows = res.data or []
        return {r["property_id"] for r in rows if r.get("property_id")}

    def list_recent_opportunity_analyses(
        self, *, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Últimas N opportunity_analyses (todas as propriedades).

        Usado pelo dashboard para calcular "pendentes" e ranquear top
        oportunidades. Como cada análise é razoavelmente pequena (sem
        joins) o limite default é generoso.
        """
        try:
            res = (
                self._client.table("opportunity_analyses")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao listar opportunity_analyses globais: {exc}"
            ) from exc
        return res.data or []

    # ------------------------------------------------------------------ #
    # FipeZAP — preço médio R$/m² por cidade (alimentada por
    # ``scripts/update_fipezap.py``).
    # ------------------------------------------------------------------ #
    def upsert_city_ppm2_stats(self, rows: list[dict[str, Any]]) -> int:
        """Upsert em batch na ``city_ppm2_stats``.

        Conflito em ``(city, state, asof_year, asof_month)`` atualiza o
        valor. Linhas inválidas (sem ``city`` ou ``mean_ppm2_brl``) são
        descartadas com warning — não levanta para que o script CLI
        possa popular o mês inteiro mesmo com 1-2 linhas problemáticas.
        Devolve o número de linhas que foram para o upsert.
        """
        clean = [
            r for r in rows
            if r.get("city") and r.get("mean_ppm2_brl") and r.get("asof_year")
            and r.get("asof_month")
        ]
        if not clean:
            return 0
        try:
            (
                self._client.table("city_ppm2_stats")
                .upsert(clean, on_conflict="city,state,asof_year,asof_month")
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(f"Falha no upsert city_ppm2_stats: {exc}") from exc
        return len(clean)

    def get_latest_city_ppm2(
        self, *, city: str, state: str | None = None
    ) -> dict[str, Any] | None:
        """Devolve a leitura FipeZAP mais recente para ``(city, state)``.

        Quando ``state`` é informado, filtra também por UF (importante para
        cidades homônimas — ex.: Campinas SP vs Campinas RJ). Retorna
        ``None`` quando não há leitura para a cidade. NÃO levanta — uma
        falha de consulta vira ``None`` para que o caller siga sem
        depender de FipeZAP estar populado.

        Resultado normalizado:
            {
              "city": str, "state": str | None,
              "mean_ppm2_brl": float,
              "asof_year": int, "asof_month": int,
            }
        """
        if not city:
            return None
        try:
            q = self._client.table("city_ppm2_stats").select(
                "city,state,mean_ppm2_brl,asof_year,asof_month"
            ).eq("city", city)
            if state:
                q = q.eq("state", state)
            res = (
                q.order("asof_year", desc=True)
                .order("asof_month", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            # Tabela inexistente, RLS bloqueando, conexão fora — em todos
            # os casos é "fallback ausente", não erro do balisador.
            logger.warning("supabase.city_ppm2.fetch_failed", error=str(exc))
            return None
        rows = res.data or []
        return rows[0] if rows else None

    # ------------------------------------------------------------------ #
    # Listings vizinhos (AGENTE 4 — busca por raio)
    # ------------------------------------------------------------------ #
    def find_listings_near(
        self,
        *,
        lat: float,
        lng: float,
        radius_m: int,
        property_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Retorna listings num raio aproximado em torno de (lat, lng).

        O cliente supabase-py não expõe PostGIS direto, então usamos um
        bounding-box em latitude/longitude (índice ``idx_listings_lat_lng``
        cobre a query) e refinamos por distância haversine no Python.

        Para os usos do AGENTE 4 (estatísticas de bairro) essa precisão
        é mais que suficiente — não estamos calculando distâncias para
        rota ou cobrança.
        """
        if radius_m <= 0:
            return []
        # 1° de latitude ≈ 111_320 m. Para longitude, multiplicar por cos(lat).
        dlat = radius_m / 111_320.0
        cos_lat = max(math.cos(math.radians(lat)), 1e-6)
        dlng = radius_m / (111_320.0 * cos_lat)

        try:
            q = (
                self._client.table("listings")
                .select("*")
                .gte("latitude", lat - dlat)
                .lte("latitude", lat + dlat)
                .gte("longitude", lng - dlng)
                .lte("longitude", lng + dlng)
            )
            if property_type:
                q = q.eq("property_type", property_type)
            res = q.limit(limit).execute()
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao buscar listings vizinhos: {exc}"
            ) from exc

        rows = res.data or []
        # Refina por haversine (filtra os cantos do bbox).
        out: list[dict[str, Any]] = []
        for r in rows:
            rlat = r.get("latitude")
            rlng = r.get("longitude")
            if rlat is None or rlng is None:
                continue
            if _haversine_m(lat, lng, float(rlat), float(rlng)) <= radius_m:
                out.append(r)
        return out

    # ------------------------------------------------------------------ #
    # Deep analyses (AGENTE 4)
    # ------------------------------------------------------------------ #
    def insert_deep_analysis_pending(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Cria a row da análise com ``status='pending'``."""
        body = {**payload, "status": "pending"}
        try:
            res = (
                self._client.table("deep_analyses").insert(body).execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao criar deep_analysis pending: {exc}"
            ) from exc
        rows = res.data or []
        if not rows:
            raise SupabaseError(
                "Insert de deep_analysis não retornou registros."
            )
        return rows[0]

    def update_deep_analysis(
        self, analysis_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            res = (
                self._client.table("deep_analyses")
                .update(fields)
                .eq("id", analysis_id)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao atualizar deep_analysis {analysis_id}: {exc}"
            ) from exc
        rows = res.data or []
        if not rows:
            raise SupabaseError(
                f"Update de deep_analysis {analysis_id} não retornou registros."
            )
        return rows[0]

    def list_deep_analyses(
        self, property_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        try:
            res = (
                self._client.table("deep_analyses")
                .select("*")
                .eq("property_id", property_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao listar deep_analyses: {exc}"
            ) from exc
        return res.data or []

    def get_deep_analysis(
        self, analysis_id: str
    ) -> dict[str, Any] | None:
        try:
            res = (
                self._client.table("deep_analyses")
                .select("*")
                .eq("id", analysis_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao consultar deep_analysis {analysis_id}: {exc}"
            ) from exc
        rows = res.data or []
        return rows[0] if rows else None

    def get_latest_completed_deep_analysis(
        self, property_id: str
    ) -> dict[str, Any] | None:
        """Última análise *completada* (usada como cache)."""
        try:
            res = (
                self._client.table("deep_analyses")
                .select("*")
                .eq("property_id", property_id)
                .eq("status", "completed")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseError(
                f"Falha ao buscar última deep_analysis: {exc}"
            ) from exc
        rows = res.data or []
        return rows[0] if rows else None


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância haversine em metros (raio da Terra = 6 371 000 m)."""
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def get_supabase_service() -> SupabaseService:
    settings = get_settings()
    return SupabaseService(
        url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key.get_secret_value(),
    )
