"""Testes dos identificadores jurídicos extraídos pelo Scraper.

Cobre:
* schema (``ExtractedAuctionData`` aceita os campos);
* normalização de CPF/CNPJ (``_normalize_cpf_cnpj``);
* persistência (campos vão pro payload do upsert).
"""

from __future__ import annotations

import pytest

from app.agents.scraper.nodes import _normalize_cpf_cnpj
from app.agents.scraper.schemas import ExtractedAuctionData


# =============================================================================
# _normalize_cpf_cnpj
# =============================================================================
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("123.456.789-00", "12345678900"),     # CPF com pontuação
        ("12345678900", "12345678900"),         # CPF já limpo
        ("12.345.678/0001-90", "12345678000190"),  # CNPJ com pontuação
        ("12345678000190", "12345678000190"),   # CNPJ limpo
        ("CPF 111.222.333-44", "11122233344"),  # com prefixo de texto
    ],
)
def test_normalize_cpf_cnpj_strips_punctuation(raw: str, expected: str) -> None:
    assert _normalize_cpf_cnpj(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "123", "1234567890", "1234567890123", "abc.def.ghi-jk"],
)
def test_normalize_cpf_cnpj_returns_none_for_invalid_lengths(raw: str | None) -> None:
    """Tamanhos fora de {11, 14} viram None (não persistem documento inválido)."""
    assert _normalize_cpf_cnpj(raw) is None


# =============================================================================
# Schema
# =============================================================================
def test_extracted_schema_accepts_all_new_legal_fields() -> None:
    """Schema aceita os 4 campos novos como opcionais."""
    e = ExtractedAuctionData(
        owner_cpf_cnpj="12345678900",
        registry_matricula="12345",
        registry_office="1º CRI de São Paulo",
        inscricao_municipal="123.456.7890-1",
    )
    assert e.owner_cpf_cnpj == "12345678900"
    assert e.registry_matricula == "12345"
    assert e.registry_office == "1º CRI de São Paulo"
    assert e.inscricao_municipal == "123.456.7890-1"


def test_extracted_schema_legal_fields_default_to_none() -> None:
    """Campos opcionais — schema vazio é válido."""
    e = ExtractedAuctionData()
    assert e.owner_cpf_cnpj is None
    assert e.registry_matricula is None
    assert e.registry_office is None
    assert e.inscricao_municipal is None
