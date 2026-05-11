"""Testes do Agente Legal — nodes + orquestrador."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.legal.nodes.check_matricula import check_matricula
from app.agents.legal.nodes.check_processes import check_processes
from app.agents.legal.service import run_legal_check
from app.services.cnj_datajud_service import DataJudQueryResult, ProcessHit


def _mk_datajud(query_result: DataJudQueryResult) -> MagicMock:
    dj = MagicMock()
    dj.tribunal_for_state.side_effect = lambda s: {"SP": "tjsp", "RJ": "tjrj"}.get(
        (s or "").upper()
    )
    dj.search_by_document.return_value = query_result
    return dj


def _query_result(critical: int = 0, total: int = 0) -> DataJudQueryResult:
    processes = [
        ProcessHit(
            numero_processo=f"0001234-56.2024.8.26.{i:03d}",
            classe_codigo=159 if i < critical else 50,
            classe_nome="Execução Fiscal" if i < critical else "Outro",
            orgao_julgador="1ª Vara",
            data_ajuizamento="2024-06-01",
            tribunal="tjsp",
            is_critical=i < critical,
        )
        for i in range(total)
    ]
    return DataJudQueryResult(
        cpf_cnpj="12345678900",
        tribunal="tjsp",
        total_hits=total,
        critical_hits=critical,
        processes=processes,
        critical_labels=["Execução Fiscal"] if critical else [],
    )


# =============================================================================
# check_processes
# =============================================================================
def test_check_processes_skipped_when_no_cpf_cnpj() -> None:
    out = check_processes(property_row={"id": "p1", "state": "SP"}, datajud=MagicMock())
    assert out.status == "skipped"
    assert "owner_cpf_cnpj" in (out.skipped_reason or "")


def test_check_processes_skipped_when_state_unmapped() -> None:
    dj = _mk_datajud(_query_result())
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "XX"},
        datajud=dj,
    )
    assert out.status == "skipped"
    assert "tribunal" in (out.skipped_reason or "").lower()
    dj.search_by_document.assert_not_called()


def test_check_processes_completed_with_no_critical() -> None:
    dj = _mk_datajud(_query_result(critical=0, total=3))
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.status == "completed"
    assert out.total_hits == 3
    assert out.critical_hits == 0
    assert out.tribunal == "tjsp"


def test_check_processes_completed_with_critical_findings() -> None:
    dj = _mk_datajud(_query_result(critical=2, total=5))
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.status == "completed"
    assert out.critical_hits == 2
    assert "Execução Fiscal" in out.critical_labels
    # Sample começa com os críticos (priorização).
    assert out.sample_processes[0].is_critical is True


def test_check_processes_failed_on_datajud_error() -> None:
    from app.services.cnj_datajud_service import DataJudServiceError

    dj = MagicMock()
    dj.tribunal_for_state.return_value = "tjsp"
    dj.search_by_document.side_effect = DataJudServiceError("network down")
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.status == "failed"
    assert "network down" in (out.skipped_reason or "")


# =============================================================================
# check_matricula (stub)
# =============================================================================
def test_check_matricula_skipped_when_missing() -> None:
    out = check_matricula(property_row={})
    assert out.status == "skipped"
    assert "matricula" in (out.skipped_reason or "")


def test_check_matricula_skipped_with_matricula_pending_onr() -> None:
    """Há matrícula no property mas ONR é stub — ainda retorna skipped."""
    out = check_matricula(property_row={"matricula": "12345", "registry_office": "CRI SP"})
    assert out.status == "skipped"
    assert out.matricula == "12345"
    assert out.registry_office == "CRI SP"
    assert "ONR" in (out.skipped_reason or "")


# =============================================================================
# run_legal_check (orquestrador)
# =============================================================================
def test_run_legal_check_aggregates_results_no_critical() -> None:
    dj = _mk_datajud(_query_result(critical=0, total=2))
    out = run_legal_check(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.owner_processes.status == "completed"
    assert out.matricula_check.status == "skipped"
    assert out.has_critical_findings is False
    assert out.critical_findings == []
    assert out.duration_ms is not None


def test_run_legal_check_flags_critical_processes_in_summary() -> None:
    dj = _mk_datajud(_query_result(critical=3, total=4))
    out = run_legal_check(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.has_critical_findings is True
    assert len(out.critical_findings) == 1
    assert "3 processo" in out.critical_findings[0]
    assert "Execução Fiscal" in out.critical_findings[0]


def test_run_legal_check_flags_datajud_failure_as_critical() -> None:
    """Falha do DataJud é tratada como red flag — usuário precisa saber
    que o risco jurídico NÃO foi verificado."""
    from app.services.cnj_datajud_service import DataJudServiceError

    dj = MagicMock()
    dj.tribunal_for_state.return_value = "tjsp"
    dj.search_by_document.side_effect = DataJudServiceError("timeout")
    out = run_legal_check(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.has_critical_findings is True
    assert any("DataJud" in f for f in out.critical_findings)
