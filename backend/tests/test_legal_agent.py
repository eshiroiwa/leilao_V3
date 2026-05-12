"""Testes do Agente Legal — nodes + orquestrador."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.legal.nodes.check_matricula import check_matricula
from app.agents.legal.nodes.check_processes import check_processes
from app.agents.legal.service import run_legal_check
from app.services.cnj_datajud_service import DataJudQueryResult, ProcessHit


def _mk_datajud(
    query_result: DataJudQueryResult,
    *,
    extra_tribunals: dict[str, DataJudQueryResult] | None = None,
) -> MagicMock:
    """Mock datajud que devolve [tjsp] para SP por default. Use
    ``extra_tribunals`` para simular TRT respondendo também (key=slug)."""
    dj = MagicMock()
    dj.tribunal_for_state.side_effect = lambda s: {"SP": "tjsp", "RJ": "tjrj"}.get(
        (s or "").upper()
    )
    extras = extra_tribunals or {}

    def _tribunals(s: str | None) -> list[str]:
        uf = (s or "").upper()
        if uf == "SP":
            return ["tjsp", *extras.keys()] if extras else ["tjsp"]
        if uf == "RJ":
            return ["tjrj"]
        return []

    dj.tribunals_for_state.side_effect = _tribunals

    by_tribunal = {"tjsp": query_result, **extras}

    def _search(cpf, *, tribunal, size=20):  # type: ignore[no-untyped-def]
        return by_tribunal[tribunal]

    dj.search_by_document.side_effect = _search
    return dj


def _query_result(
    critical: int = 0, total: int = 0, *, tribunal: str = "tjsp"
) -> DataJudQueryResult:
    processes = [
        ProcessHit(
            numero_processo=f"0001234-56.2024.8.26.{i:03d}",
            classe_codigo=159 if i < critical else 50,
            classe_nome="Execução Fiscal" if i < critical else "Outro",
            orgao_julgador="1ª Vara",
            data_ajuizamento="2024-06-01",
            tribunal=tribunal,
            is_critical=i < critical,
        )
        for i in range(total)
    ]
    return DataJudQueryResult(
        cpf_cnpj="12345678900",
        tribunal=tribunal,
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


def test_check_processes_normalizes_punctuation_from_user_input() -> None:
    """Usuário digita '123.456.789-00' no frontend → check normaliza para 11 dígitos."""
    dj = _mk_datajud(_query_result(critical=0, total=2))
    out = check_processes(
        property_row={
            "id": "p1",
            "owner_cpf_cnpj": "123.456.789-00",
            "state": "SP",
        },
        datajud=dj,
    )
    assert out.status == "completed"
    assert out.cpf_cnpj == "12345678900"  # só dígitos
    dj.search_by_document.assert_called_once_with(
        "12345678900", tribunal="tjsp", size=100,
    )


def test_check_processes_skipped_on_invalid_length() -> None:
    """Documento com tamanho ≠ {11, 14} é rejeitado com mensagem clara."""
    out = check_processes(
        property_row={
            "id": "p1",
            "owner_cpf_cnpj": "12345",
            "state": "SP",
        },
        datajud=MagicMock(),
    )
    assert out.status == "skipped"
    assert "5 dígito" in (out.skipped_reason or "")


def test_check_processes_skipped_when_state_unmapped() -> None:
    dj = _mk_datajud(_query_result())
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "XX"},
        datajud=dj,
    )
    assert out.status == "skipped"
    assert "tribuna" in (out.skipped_reason or "").lower()
    dj.search_by_document.assert_not_called()


def test_check_processes_queries_multiple_tribunals_in_sp() -> None:
    """Em SP, o mock devolve TJSP + TRT2 + TRT15 — todos devem ser consultados."""
    trt2_result = DataJudQueryResult(
        cpf_cnpj="12345678900", tribunal="trt2",
        total_hits=2, critical_hits=2,
        processes=[
            ProcessHit(
                numero_processo="0009999-99.2024.5.02.0001",
                classe_codigo=985, classe_nome="Cumprimento Provisório",
                orgao_julgador="1ª Vara do Trabalho",
                data_ajuizamento="2024-08-01",
                tribunal="trt2", is_critical=True,
            ),
            ProcessHit(
                numero_processo="0008888-88.2024.5.02.0002",
                classe_codigo=1660, classe_nome="Reclamação Trabalhista",
                orgao_julgador="3ª Vara do Trabalho",
                data_ajuizamento="2024-09-15",
                tribunal="trt2", is_critical=True,
            ),
        ],
        critical_labels=["Processo trabalhista"],
    )
    dj = _mk_datajud(_query_result(critical=1, total=2), extra_tribunals={"trt2": trt2_result})
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.status == "completed"
    assert "tjsp" in out.tribunals_queried
    assert "trt2" in out.tribunals_queried
    assert out.total_hits == 4  # 2 TJSP + 2 TRT2
    assert out.critical_hits == 3  # 1 TJSP crítico + 2 TRT2
    assert "Execução Fiscal" in out.critical_labels
    assert "Processo trabalhista" in out.critical_labels


def test_check_processes_continues_when_one_tribunal_fails() -> None:
    """Falha em TRT não derruba o resultado — só registra em tribunals_failed."""
    from app.services.cnj_datajud_service import DataJudServiceError

    dj = MagicMock()
    dj.tribunals_for_state.return_value = ["tjsp", "trt2"]

    def _search(cpf, *, tribunal, size=20):  # type: ignore[no-untyped-def]
        if tribunal == "tjsp":
            return _query_result(critical=1, total=1)
        raise DataJudServiceError("trt2 down")

    dj.search_by_document.side_effect = _search
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.status == "completed"
    assert out.tribunals_queried == ["tjsp"]
    assert out.tribunals_failed == ["trt2"]
    assert out.total_hits == 1


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


def test_check_processes_failed_when_all_tribunals_error() -> None:
    """Falha em TODOS os tribunais consultados → status FAILED."""
    from app.services.cnj_datajud_service import DataJudServiceError

    dj = MagicMock()
    dj.tribunals_for_state.return_value = ["tjsp", "trt2"]
    dj.search_by_document.side_effect = DataJudServiceError("network down")
    out = check_processes(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.status == "failed"
    assert set(out.tribunals_failed) == {"tjsp", "trt2"}
    assert "tjsp" in (out.skipped_reason or "")
    assert "trt2" in (out.skipped_reason or "")


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
    dj.tribunals_for_state.return_value = ["tjsp", "trt2"]
    dj.search_by_document.side_effect = DataJudServiceError("timeout")
    out = run_legal_check(
        property_row={"id": "p1", "owner_cpf_cnpj": "12345678900", "state": "SP"},
        datajud=dj,
    )
    assert out.has_critical_findings is True
    assert any("DataJud" in f for f in out.critical_findings)
