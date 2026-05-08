"""Testes do `SupabaseService.upsert_listing`.

Foco: a estratégia de dedup por ``(source, external_id)`` introduzida na
migration 004 + refactor do método. O cliente PostgREST é mockado — não
exercitamos a rede.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.supabase_service import SupabaseError, SupabaseService


def _make_service() -> tuple[SupabaseService, MagicMock]:
    """Instancia o serviço com `_client` mockado (skip do __init__)."""
    svc = SupabaseService.__new__(SupabaseService)
    client = MagicMock(name="supabase_client")
    svc._client = client  # type: ignore[attr-defined]
    return svc, client


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "source": "vivareal_zap",
        "source_url": "https://www.vivareal.com.br/imovel/apto-id-12345",
        "external_id": "12345",
        "property_type": "apartamento",
        "city": "São Paulo",
        "state": "SP",
        "listed_price": 700_000.0,
        "area_total_m2": 70.0,
    }
    base.update(overrides)
    return base


def _build_chain(
    client: MagicMock,
    *,
    execute_results: list[list[dict[str, Any]] | None],
) -> MagicMock:
    """Monta um builder fluente único que aceita todas as chamadas que o
    supabase-py faz: ``.select / .eq / .limit / .update / .upsert``.

    ``execute_results`` é a sequência ordenada do que cada ``execute()``
    deve devolver — segue a ordem das chamadas do código sob teste:
      [0] SELECT existing (caminho 1)
      [1] UPDATE       OU UPSERT (caminho 2)
    """
    builder = MagicMock(name="builder")
    for method in ("select", "eq", "limit", "update", "upsert"):
        getattr(builder, method).return_value = builder

    builder.execute.side_effect = [MagicMock(data=r) for r in execute_results]
    client.table.return_value = builder
    return builder


# =============================================================================
# Caso 1 — primeira vez com (source, external_id): cai no INSERT (caminho 2)
# =============================================================================
def test_upsert_listing_inserts_when_no_existing_pair() -> None:
    svc, client = _make_service()
    inserted_row = {**_payload(), "id": "list-1"}
    builder = _build_chain(
        client,
        execute_results=[
            [],            # SELECT existing → nada
            [inserted_row],  # UPSERT → row criada
        ],
    )

    result = svc.upsert_listing(_payload())

    assert result["id"] == "list-1"
    # Houve um SELECT + um UPSERT (sem UPDATE).
    builder.select.assert_called()
    builder.upsert.assert_called_once()
    builder.update.assert_not_called()


# =============================================================================
# Caso 2 — segunda vez com mesmo (source, external_id) mas source_url
# diferente (synthetic → URL real): UPDATE da row existente, sem criar
# duplicata.
# =============================================================================
def test_upsert_listing_updates_when_external_id_already_exists() -> None:
    svc, client = _make_service()
    existing_row = {
        "id": "list-existing",
        "source_url": "https://www.vivareal.com.br/venda/sp/x#item=oldhash",
    }
    updated_row = {
        **_payload(source_url="https://www.vivareal.com.br/imovel/apto-id-12345"),
        "id": "list-existing",
    }
    builder = _build_chain(
        client,
        execute_results=[
            [existing_row],  # SELECT existing → achou
            [updated_row],   # UPDATE → row atualizada
        ],
    )

    result = svc.upsert_listing(
        _payload(source_url="https://www.vivareal.com.br/imovel/apto-id-12345")
    )

    # Mantém o MESMO id da row antiga (não duplicou).
    assert result["id"] == "list-existing"
    # Foi UPDATE, NÃO upsert (o caminho 2 não foi acionado).
    builder.update.assert_called_once()
    builder.upsert.assert_not_called()
    # O update recebeu o source_url novo (URL real promovendo o synthetic).
    update_call = builder.update.call_args
    assert (
        update_call.args[0]["source_url"]
        == "https://www.vivareal.com.br/imovel/apto-id-12345"
    )


# =============================================================================
# Caso 3 — sem external_id: cai direto no caminho 2 (upsert por source_url)
# =============================================================================
def test_upsert_listing_falls_back_when_no_external_id() -> None:
    svc, client = _make_service()
    inserted_row = {**_payload(external_id=None), "id": "list-synth"}
    builder = _build_chain(
        client,
        execute_results=[
            [inserted_row],  # único execute: o UPSERT do caminho 2
        ],
    )

    result = svc.upsert_listing(_payload(external_id=None))

    assert result["id"] == "list-synth"
    # SEM select prévio — caiu direto no upsert.
    builder.select.assert_not_called()
    builder.upsert.assert_called_once()


# =============================================================================
# Caso 4 — sem source: também cai no caminho 2 (defesa)
# =============================================================================
def test_upsert_listing_falls_back_when_no_source() -> None:
    svc, client = _make_service()
    inserted_row = {**_payload(source=None), "id": "list-x"}
    builder = _build_chain(
        client,
        execute_results=[[inserted_row]],
    )

    result = svc.upsert_listing(_payload(source=None))
    assert result["id"] == "list-x"
    builder.select.assert_not_called()
    builder.upsert.assert_called_once()


# =============================================================================
# Caso 5 — supabase devolve lista vazia em UPDATE → erro explícito
# =============================================================================
def test_upsert_listing_raises_when_update_returns_empty() -> None:
    svc, client = _make_service()
    _build_chain(
        client,
        execute_results=[
            [{"id": "list-existing", "source_url": "old"}],  # SELECT achou
            [],                                              # UPDATE retornou vazio
        ],
    )

    with pytest.raises(SupabaseError, match="Update de listing"):
        svc.upsert_listing(_payload())
