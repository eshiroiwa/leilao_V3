"""Testes das rotas REST do AGENTE 3.

Mockamos `SupabaseService` via dependency override para evitar I/O com
o banco. A regra: testar o contrato HTTP — status codes, formato de
saída e propagação de erros.
"""

from __future__ import annotations

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
    fake = MagicMock(name="supabase_fake")
    fake.get_property_by_id.return_value = {
        "id": PROP_ID,
        "city": "São Paulo",
        "state": "SP",
        "total_area_m2": 60,
        "occupancy_status": "desocupado",
        "has_liens_or_debts": False,
        "auctioneer_fee_pct": None,
        "auctioneer_slug": None,
        "iptu_arrears": None,
        "condo_arrears": None,
    }
    fake.get_latest_valuation_for_property.return_value = {
        "id": str(uuid4()),
        "price_low": 350_000,
        "price_estimated": 400_000,
        "price_high": 450_000,
        "confidence": "HIGH",
        "n_used": 12,
    }
    fake.insert_opportunity_analysis.side_effect = lambda payload: {
        **payload,
        "id": ANALYSIS_ID,
    }
    fake.list_opportunity_analyses.return_value = [
        {"id": ANALYSIS_ID, "property_id": PROP_ID, "verdict": "BOA_OPORTUNIDADE"}
    ]
    fake.get_opportunity_analysis.return_value = {
        "id": ANALYSIS_ID,
        "property_id": PROP_ID,
        "verdict": "BOA_OPORTUNIDADE",
    }

    # cache do get_supabase_service é lru_cache → limpo
    ss.get_supabase_service.cache_clear()
    # Patcheia tanto a fonte quanto a referência local do router (já importada).
    monkeypatch.setattr(ss, "get_supabase_service", lambda: fake)
    from app.api.routes import opportunity as opp_route
    monkeypatch.setattr(opp_route, "get_supabase_service", lambda: fake)

    return fake


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# =============================================================================
# POST preview
# =============================================================================
def test_preview_returns_three_scenarios(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/opportunity-analyses/preview",
        json={"bid_amount": 200_000},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pessimista"]["sale_price"] < body["realista"]["sale_price"]
    assert body["realista"]["sale_price"] < body["otimista"]["sale_price"]
    assert "verdict" in body
    assert isinstance(body["warnings"], list)
    # NÃO chamou insert (preview = stateless).
    mock_supabase.insert_opportunity_analysis.assert_not_called()


def test_preview_404_when_property_missing(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    mock_supabase.get_property_by_id.return_value = None
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/opportunity-analyses/preview",
        json={"bid_amount": 200_000},
    )
    assert res.status_code == 404


# =============================================================================
# POST save
# =============================================================================
def test_save_persists_and_returns_id(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/opportunity-analyses",
        json={"bid_amount": 200_000, "buyer_type": "PF"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["id"] == ANALYSIS_ID
    assert "result" in body
    mock_supabase.insert_opportunity_analysis.assert_called_once()
    # O payload persistido deve carregar `input_overrides` (mesmo que com
    # valores `None`) — é o que permite restaurar o formulário a partir
    # do histórico no frontend.
    payload = mock_supabase.insert_opportunity_analysis.call_args.args[0]
    assert "input_overrides" in payload
    assert set(payload["input_overrides"].keys()) == {
        "itbi_pct_override",
        "registration_pct_override",
        "auctioneer_fee_pct_override",
        "sale_price_override",
    }


def test_save_persists_input_overrides_when_provided(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    """Quando o usuário envia overrides, eles devem chegar até o insert."""
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/opportunity-analyses",
        json={
            "bid_amount": 200_000,
            "buyer_type": "PF",
            "itbi_pct_override": 0.025,
            "auctioneer_fee_pct_override": 0.04,
            "sale_price_override": 480_000,
        },
    )
    assert res.status_code == 201, res.text
    payload = mock_supabase.insert_opportunity_analysis.call_args.args[0]
    overrides = payload["input_overrides"]
    assert overrides["itbi_pct_override"] == 0.025
    assert overrides["auctioneer_fee_pct_override"] == 0.04
    assert overrides["sale_price_override"] == 480_000
    assert overrides["registration_pct_override"] is None


def test_save_pj_warns_about_estimativa(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/opportunity-analyses",
        json={"bid_amount": 200_000, "buyer_type": "PJ"},
    )
    assert res.status_code == 201
    warnings = res.json()["result"]["warnings"]
    assert any("estimativa" in w.lower() for w in warnings)


def test_save_404_when_property_missing(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    mock_supabase.get_property_by_id.return_value = None
    res = client.post(
        f"/api/v1/properties/{PROP_ID}/opportunity-analyses",
        json={"bid_amount": 200_000},
    )
    assert res.status_code == 404


# =============================================================================
# GET list / detail
# =============================================================================
def test_list_returns_history(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.get(f"/api/v1/properties/{PROP_ID}/opportunity-analyses")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert res.json()[0]["id"] == ANALYSIS_ID


def test_get_detail_404_when_property_mismatch(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    other_prop = str(uuid4())
    res = client.get(
        f"/api/v1/properties/{other_prop}/opportunity-analyses/{ANALYSIS_ID}"
    )
    assert res.status_code == 404


def test_get_detail_returns_row(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.get(
        f"/api/v1/properties/{PROP_ID}/opportunity-analyses/{ANALYSIS_ID}"
    )
    assert res.status_code == 200
    assert res.json()["id"] == ANALYSIS_ID
