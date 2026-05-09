"""Testes da rota PATCH /properties/{id} (edição manual de campos).

Mockamos ``SupabaseService`` para validar apenas o contrato HTTP:
status codes, sanitização do payload (whitelist + trim) e propagação
de erros 404/502.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import supabase_service as ss


PROP_ID = str(uuid4())


@pytest.fixture
def mock_supabase(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock(name="supabase_fake")

    # Por padrão, update devolve a row "atualizada" com o payload aplicado.
    def _update(_id: str, payload: dict) -> dict:
        return {"id": _id, "city": "Pindamonhangaba", **payload}

    fake.update_property.side_effect = _update

    ss.get_supabase_service.cache_clear()
    monkeypatch.setattr(ss, "get_supabase_service", lambda: fake)
    from app.api.routes import properties as prop_route
    monkeypatch.setattr(prop_route, "get_supabase_service", lambda: fake)
    return fake


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_patch_condo_name_persists_value(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.patch(
        f"/api/v1/properties/{PROP_ID}",
        json={"condo_name": "Park Crispim"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["condo_name"] == "Park Crispim"
    args = mock_supabase.update_property.call_args
    assert args.args[0] == PROP_ID
    assert args.args[1] == {"condo_name": "Park Crispim"}


def test_patch_strips_whitespace(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.patch(
        f"/api/v1/properties/{PROP_ID}",
        json={"condo_name": "  Edifício X  "},
    )
    assert res.status_code == 200
    payload = mock_supabase.update_property.call_args.args[1]
    assert payload["condo_name"] == "Edifício X"


def test_patch_empty_string_clears_value(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    """String vazia/só-espaço grava ``None`` (limpa o campo)."""
    res = client.patch(
        f"/api/v1/properties/{PROP_ID}",
        json={"condo_name": "   "},
    )
    assert res.status_code == 200
    payload = mock_supabase.update_property.call_args.args[1]
    assert payload["condo_name"] is None


def test_patch_empty_body_returns_400(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.patch(f"/api/v1/properties/{PROP_ID}", json={})
    assert res.status_code == 400


def test_patch_unknown_field_ignored(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    """Campos fora da whitelist (PropertyPatch) são silenciosamente ignorados."""
    res = client.patch(
        f"/api/v1/properties/{PROP_ID}",
        json={"condo_name": "X", "source_url": "http://hacker.example"},
    )
    assert res.status_code == 200
    payload = mock_supabase.update_property.call_args.args[1]
    assert "source_url" not in payload
    assert payload["condo_name"] == "X"


def test_patch_too_long_returns_422(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    res = client.patch(
        f"/api/v1/properties/{PROP_ID}",
        json={"condo_name": "x" * 500},
    )
    assert res.status_code == 422  # Pydantic max_length


def test_patch_404_when_property_missing(
    mock_supabase: MagicMock, client: TestClient
) -> None:
    mock_supabase.update_property.side_effect = lambda *a, **kw: None
    res = client.patch(
        f"/api/v1/properties/{PROP_ID}",
        json={"condo_name": "Park"},
    )
    assert res.status_code == 404
