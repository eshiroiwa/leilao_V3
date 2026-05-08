"""Testes das rotas REST do AGENTE 4.

Foco no contrato HTTP: status codes, fluxo cache vs run, polling.
O pipeline em si é testado em `test_deep_pure_nodes.py` (parte pura) —
aqui mockamos o ``enqueue_deep_analysis`` para NÃO disparar Firecrawl/LLM.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import supabase_service as ss

PROP_ID = str(uuid4())
ANALYSIS_ID = str(uuid4())


# =============================================================================
# Fixture: mock do SupabaseService
# =============================================================================
@pytest.fixture
def mock_supabase(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock(name="supabase_deep")
    fake.get_property_by_id.return_value = {"id": PROP_ID, "city": "Sorocaba", "state": "SP"}

    fake.get_latest_completed_deep_analysis.return_value = None  # cache miss por padrão
    fake.insert_deep_analysis_pending.side_effect = lambda payload: {
        "id": ANALYSIS_ID,
        "status": "pending",
        **payload,
    }
    fake.get_deep_analysis.return_value = {
        "id": ANALYSIS_ID,
        "property_id": PROP_ID,
        "status": "running",
    }
    fake.list_deep_analyses.return_value = [
        {"id": ANALYSIS_ID, "property_id": PROP_ID, "status": "completed"}
    ]

    ss.get_supabase_service.cache_clear()
    monkeypatch.setattr(ss, "get_supabase_service", lambda: fake)
    from app.api.routes import deep as deep_route
    from app.agents.deep import service as deep_service
    monkeypatch.setattr(deep_route, "get_supabase_service", lambda: fake)
    monkeypatch.setattr(deep_service, "get_supabase_service", lambda: fake)
    return fake


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Garante que o background task NÃO toca rede.
    from app.api.routes import deep as deep_route
    monkeypatch.setattr(
        deep_route, "enqueue_deep_analysis", MagicMock(name="enqueue_noop")
    )
    return TestClient(app)


# =============================================================================
# POST — cache miss → cria pending e enfileira
# =============================================================================
def test_post_cache_miss_creates_pending(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/deep-analyses",
        json={"force_refresh": False},
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["id"] == ANALYSIS_ID
    assert body["status"] == "pending"
    assert body["from_cache"] is False
    mock_supabase.insert_deep_analysis_pending.assert_called_once()


# =============================================================================
# POST — cache hit (< 7 dias) → retorna a row sem enfileirar
# =============================================================================
def test_post_cache_hit_skips_enqueue(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    fresh = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    mock_supabase.get_latest_completed_deep_analysis.return_value = {
        "id": ANALYSIS_ID,
        "property_id": PROP_ID,
        "status": "completed",
        "created_at": fresh,
    }
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/deep-analyses",
        json={"force_refresh": False},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["from_cache"] is True
    assert body["row"] is not None
    mock_supabase.insert_deep_analysis_pending.assert_not_called()


def test_post_force_refresh_ignores_cache(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    fresh = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    mock_supabase.get_latest_completed_deep_analysis.return_value = {
        "id": ANALYSIS_ID,
        "property_id": PROP_ID,
        "status": "completed",
        "created_at": fresh,
    }
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/deep-analyses",
        json={"force_refresh": True},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["from_cache"] is False
    mock_supabase.insert_deep_analysis_pending.assert_called_once()


def test_post_property_not_found(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    mock_supabase.get_property_by_id.return_value = None
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/deep-analyses",
        json={},
    )
    assert res.status_code == 404


# =============================================================================
# Cache stale (> 7 dias) → cache miss
# =============================================================================
def test_post_cache_stale_creates_pending(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    mock_supabase.get_latest_completed_deep_analysis.return_value = {
        "id": ANALYSIS_ID,
        "property_id": PROP_ID,
        "status": "completed",
        "created_at": stale,
    }
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/deep-analyses",
        json={},
    )
    assert res.status_code == 202
    assert res.json()["from_cache"] is False


# =============================================================================
# GET (detalhe — usado pelo polling do frontend)
# =============================================================================
def test_get_detail(mock_supabase: MagicMock, client: TestClient) -> None:
    res = client.get(f"/api/v1/deep-analyses/{ANALYSIS_ID}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == ANALYSIS_ID
    assert body["status"] == "running"


def test_get_detail_404(mock_supabase: MagicMock, client: TestClient) -> None:
    mock_supabase.get_deep_analysis.return_value = None
    res = client.get(f"/api/v1/deep-analyses/{ANALYSIS_ID}")
    assert res.status_code == 404


# =============================================================================
# GET (lista) — também passa pelo reaper de stale-running
# =============================================================================
def test_get_list_calls_reaper(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    # Coloca um running antigo (>10min) → deve ser marcado como failed.
    stale_started = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    ).isoformat()
    mock_supabase.list_deep_analyses.return_value = [
        {
            "id": ANALYSIS_ID,
            "property_id": PROP_ID,
            "status": "running",
            "started_at": stale_started,
        }
    ]
    res = client.get(f"/api/v1/properties/{PROP_ID}/deep-analyses")
    assert res.status_code == 200
    # O reaper chama update_deep_analysis para marcar como failed.
    mock_supabase.update_deep_analysis.assert_called_once()
    args, _ = mock_supabase.update_deep_analysis.call_args
    assert args[0] == ANALYSIS_ID
    assert args[1]["status"] == "failed"


# =============================================================================
# GET latest
# =============================================================================
def test_get_latest_passthrough(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    mock_supabase.get_latest_completed_deep_analysis.return_value = {
        "id": ANALYSIS_ID,
        "property_id": PROP_ID,
        "status": "completed",
    }
    res = client.get(f"/api/v1/properties/{PROP_ID}/deep-analyses/latest")
    assert res.status_code == 200
    assert res.json()["id"] == ANALYSIS_ID
