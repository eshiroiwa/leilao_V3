"""Testes do BacenService — sem HTTP real (mock httpx.get)."""

from __future__ import annotations

import pytest

from app.services import bacen_service
from app.services.bacen_service import (
    BUSINESS_DAYS_PER_YEAR,
    BacenService,
    BacenServiceError,
)


# =============================================================================
# get_cdi_annual — anualização correta da taxa overnight
# =============================================================================
def test_cdi_annual_compounds_daily_rate_over_252_business_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Taxa diária de 0,05% (% ao dia) → (1.0005)^252 - 1 ≈ 13,46% a.a."""

    class _FakeResponse:
        @staticmethod
        def raise_for_status() -> None: ...
        @staticmethod
        def json() -> list[dict]:
            return [{"data": "10/05/2026", "valor": "0,05"}]

    def _fake_get(*_a, **_kw):  # type: ignore[no-untyped-def]
        return _FakeResponse()

    # Bypass do fixture global (que substitui get_cdi_annual diretamente).
    monkeypatch.setattr(bacen_service.httpx, "get", _fake_get)

    svc = BacenService()
    cdi = svc.get_cdi_annual()
    expected = (1 + 0.0005) ** BUSINESS_DAYS_PER_YEAR - 1
    assert cdi == pytest.approx(expected, rel=1e-6)


def test_cdi_annual_caches_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Segunda chamada não bate o endpoint (cache em memória)."""
    calls = {"n": 0}

    class _R:
        @staticmethod
        def raise_for_status() -> None: ...
        @staticmethod
        def json() -> list[dict]:
            return [{"data": "10/05/2026", "valor": "0,05"}]

    def _fake_get(*_a, **_kw):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return _R()

    monkeypatch.setattr(
        BacenService,
        "get_cdi_annual",
        BacenService.__dict__["get_cdi_annual"],
    )
    monkeypatch.setattr(bacen_service.httpx, "get", _fake_get)

    svc = BacenService()
    svc.get_cdi_annual()
    svc.get_cdi_annual()
    svc.get_cdi_annual()
    assert calls["n"] == 1


def test_fetch_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Erro de rede vira BacenServiceError (não vaza httpx)."""
    import httpx

    def _boom(*_a, **_kw):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(bacen_service.httpx, "get", _boom)

    svc = BacenService()
    with pytest.raises(BacenServiceError):
        svc.get_cdi_annual()


def test_fetch_raises_on_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class _R:
        @staticmethod
        def raise_for_status() -> None: ...
        @staticmethod
        def json() -> list[dict]:
            return []

    def _fake_get(*_a, **_kw):  # type: ignore[no-untyped-def]
        return _R()

    monkeypatch.setattr(bacen_service.httpx, "get", _fake_get)
    with pytest.raises(BacenServiceError):
        BacenService().get_cdi_annual()


# =============================================================================
# get_ipca_12m — composição multiplicativa de 12 leituras mensais
# =============================================================================
def test_ipca_12m_compounds_monthly_readings(monkeypatch: pytest.MonkeyPatch) -> None:
    """12 leituras de 0,3% mensais → (1.003)^12 - 1 ≈ 3,66%."""
    class _R:
        @staticmethod
        def raise_for_status() -> None: ...
        @staticmethod
        def json() -> list[dict]:
            return [{"data": f"01/0{m % 12 + 1}/2025", "valor": "0,30"} for m in range(12)]

    def _fake_get(*_a, **_kw):  # type: ignore[no-untyped-def]
        return _R()

    monkeypatch.setattr(bacen_service.httpx, "get", _fake_get)

    svc = BacenService()
    ipca = svc.get_ipca_12m()
    expected = (1.003) ** 12 - 1
    assert ipca == pytest.approx(expected, rel=1e-6)
