"""Testes do BrasilApiService — fallback de geocoding por CEP."""

from __future__ import annotations

import pytest

from app.services import brasilapi_service
from app.services.brasilapi_service import BrasilApiService


class _R:
    def __init__(self, status: int, payload):  # type: ignore[no-untyped-def]
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx
            req = httpx.Request("GET", "https://x")
            raise httpx.HTTPStatusError("err", request=req, response=httpx.Response(self.status_code, request=req))

    def json(self):  # type: ignore[no-untyped-def]
        return self._payload


# =============================================================================
# Normalização e validação básica
# =============================================================================
def test_fetch_cep_rejects_invalid_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """CEP que não tem 8 dígitos não chega a bater na API — retorna None."""
    called = {"n": 0}

    def _fail(*_a, **_kw):  # type: ignore[no-untyped-def]
        called["n"] += 1
        raise AssertionError("não deveria ser chamado")

    monkeypatch.setattr(brasilapi_service.httpx, "get", _fail)
    svc = BrasilApiService()
    assert svc.fetch_cep("123") is None
    assert svc.fetch_cep("") is None
    assert called["n"] == 0


# =============================================================================
# BrasilAPI primário
# =============================================================================
def test_fetch_cep_brasilapi_returns_full_payload_with_coords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "cep": "01310100",
        "state": "SP",
        "city": "São Paulo",
        "neighborhood": "Bela Vista",
        "street": "Avenida Paulista",
        "location": {
            "coordinates": {"latitude": -23.5613, "longitude": -46.6562},
        },
    }
    monkeypatch.setattr(
        brasilapi_service.httpx, "get",
        lambda *a, **kw: _R(200, payload),
    )

    out = BrasilApiService().fetch_cep("01310-100")
    assert out is not None
    assert out["source"] == "brasilapi"
    assert out["cep"] == "01310100"
    assert out["state"] == "SP"
    assert out["city"] == "São Paulo"
    assert out["lat"] == pytest.approx(-23.5613)
    assert out["lng"] == pytest.approx(-46.6562)


def test_fetch_cep_brasilapi_404_falls_back_to_viacep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BrasilAPI devolve 404 → tenta ViaCEP (sem coordenadas)."""
    calls = []

    def _switch(url, *a, **kw):  # type: ignore[no-untyped-def]
        calls.append(url)
        if "brasilapi.com.br" in url:
            return _R(404, {"message": "not found"})
        # ViaCEP
        return _R(
            200,
            {
                "cep": "01310-100",
                "logradouro": "Avenida Paulista",
                "bairro": "Bela Vista",
                "localidade": "São Paulo",
                "uf": "SP",
            },
        )

    monkeypatch.setattr(brasilapi_service.httpx, "get", _switch)

    out = BrasilApiService().fetch_cep("01310-100")
    assert out is not None
    assert out["source"] == "viacep"
    assert out["lat"] is None and out["lng"] is None
    assert out["city"] == "São Paulo"
    assert any("brasilapi.com.br" in u for u in calls)
    assert any("viacep.com.br" in u for u in calls)


def test_fetch_cep_returns_none_when_both_sources_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BrasilAPI 404 + ViaCEP {erro: true} → None (chamador trata)."""
    def _fake(url, *a, **kw):  # type: ignore[no-untyped-def]
        if "brasilapi.com.br" in url:
            return _R(404, {})
        return _R(200, {"erro": True})

    monkeypatch.setattr(brasilapi_service.httpx, "get", _fake)
    assert BrasilApiService().fetch_cep("00000000") is None


# =============================================================================
# Cache (mesmo CEP não bate o backend duas vezes)
# =============================================================================
def test_fetch_cep_caches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    payload = {
        "cep": "01310100", "state": "SP", "city": "São Paulo",
        "neighborhood": "B", "street": "A",
        "location": {"coordinates": {"latitude": -23.5, "longitude": -46.6}},
    }

    def _fake(*a, **kw):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return _R(200, payload)

    monkeypatch.setattr(brasilapi_service.httpx, "get", _fake)
    svc = BrasilApiService()
    svc.fetch_cep("01310-100")
    svc.fetch_cep("01310100")  # mesmo CEP, formato diferente — cache hit
    svc.fetch_cep("01310-100")
    assert calls["n"] == 1
