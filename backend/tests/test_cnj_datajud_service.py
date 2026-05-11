"""Testes do DataJudService — mock httpx.post."""

from __future__ import annotations

import pytest

from app.services import cnj_datajud_service
from app.services.cnj_datajud_service import (
    DataJudService,
    DataJudServiceError,
)


class _Resp:
    def __init__(self, status: int, payload):  # type: ignore[no-untyped-def]
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                "err",
                request=httpx.Request("POST", "https://x"),
                response=httpx.Response(self.status_code),
            )

    def json(self):  # type: ignore[no-untyped-def]
        return self._payload


def _payload(*classes_codes: int) -> dict:
    """Constrói um payload Elasticsearch-like com N hits."""
    hits = [
        {
            "_source": {
                "numeroProcesso": f"0001234-56.2024.8.26.0{i:03d}",
                "classe": {"codigo": code, "nome": f"Classe {code}"},
                "orgaoJulgador": {"nome": f"{i}ª Vara Cível"},
                "dataAjuizamento": "2024-06-15T10:00:00.000Z",
            }
        }
        for i, code in enumerate(classes_codes)
    ]
    return {"hits": {"total": {"value": len(hits)}, "hits": hits}}


# =============================================================================
# Mapeamento UF → TJ
# =============================================================================
def test_tribunal_for_state_returns_slug_for_known_uf() -> None:
    svc = DataJudService()
    assert svc.tribunal_for_state("SP") == "tjsp"
    assert svc.tribunal_for_state("RJ") == "tjrj"
    assert svc.tribunal_for_state("sp") == "tjsp"  # case-insensitive


def test_tribunal_for_state_returns_none_for_unknown() -> None:
    svc = DataJudService()
    assert svc.tribunal_for_state("XX") is None
    assert svc.tribunal_for_state("") is None
    assert svc.tribunal_for_state(None) is None


# =============================================================================
# search_by_document
# =============================================================================
def test_search_by_document_rejects_invalid_lengths() -> None:
    svc = DataJudService()
    with pytest.raises(DataJudServiceError, match="CPF/CNPJ inválido"):
        svc.search_by_document("123", tribunal="tjsp")
    with pytest.raises(DataJudServiceError):
        svc.search_by_document("1234567890", tribunal="tjsp")  # 10 dígitos


def test_search_by_document_normalizes_punctuation(monkeypatch: pytest.MonkeyPatch) -> None:
    """CPF com pontuação é aceito (normalizamos para dígitos)."""
    monkeypatch.setattr(
        cnj_datajud_service.httpx, "post",
        lambda *a, **kw: _Resp(200, _payload()),
    )
    svc = DataJudService()
    out = svc.search_by_document("123.456.789-00", tribunal="tjsp")
    assert out.cpf_cnpj == "12345678900"
    assert out.total_hits == 0


def test_search_by_document_classifies_critical_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Classes 159 (Execução Fiscal) e 1116 (Execução Extrajudicial) viram críticas;
    50 (Procedimento Comum) NÃO — é genérica e geraria falsos positivos."""
    monkeypatch.setattr(
        cnj_datajud_service.httpx, "post",
        lambda *a, **kw: _Resp(200, _payload(159, 1116, 50)),
    )
    svc = DataJudService()
    out = svc.search_by_document("12345678900", tribunal="tjsp")
    assert out.total_hits == 3
    # Apenas 159 e 1116 são críticas — 50 (Procedimento Comum) é descartada
    # como sinal porque cobre muitos tipos de ação sem indicar ônus
    # patrimonial específico.
    assert out.critical_hits == 2
    assert "Execução Fiscal" in out.critical_labels
    assert "Execução de Título Extrajudicial" in out.critical_labels


def test_search_by_document_legacy_total_int_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ES legado devolve total como int, não dict {'value': N}."""
    payload = {"hits": {"total": 5, "hits": []}}
    monkeypatch.setattr(
        cnj_datajud_service.httpx, "post",
        lambda *a, **kw: _Resp(200, payload),
    )
    out = DataJudService().search_by_document("12345678900", tribunal="tjsp")
    assert out.total_hits == 5


def test_search_by_document_caches_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Segunda chamada com mesmo (doc, tribunal) não bate na rede."""
    calls = {"n": 0}

    def _fake(*a, **kw):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return _Resp(200, _payload(159))

    monkeypatch.setattr(cnj_datajud_service.httpx, "post", _fake)

    svc = DataJudService()
    svc.search_by_document("12345678900", tribunal="tjsp")
    svc.search_by_document("12345678900", tribunal="tjsp")
    svc.search_by_document("12345678900", tribunal="tjsp")
    assert calls["n"] == 1


def test_search_by_document_http_error_raises_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    def _boom(*a, **kw):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(cnj_datajud_service.httpx, "post", _boom)
    with pytest.raises(DataJudServiceError):
        DataJudService().search_by_document("12345678900", tribunal="tjsp")
