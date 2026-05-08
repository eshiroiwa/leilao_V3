"""Testes para os utilitários do Agente 1."""

from __future__ import annotations

import pytest

from app.agents.scraper.utils import (
    sanitize_image_url,
    sanitize_neighborhood,
    sanitize_number,
    sanitize_street,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Caso do bug original (Pindamonhangaba/Sorocaba)
        ("LOTEAMENTO JARDIM ANA MARIA", "Jardim Ana Maria"),
        # Outros prefixos administrativos
        ("CONJUNTO HABITACIONAL VILA NOVA", "Vila Nova"),
        ("Residencial Parque das Árvores", "Parque das Árvores"),
        ("Cond. Residencial Sol Nascente", "Sol Nascente"),
        ("EMPREENDIMENTO IMOBILIÁRIO ALPHA", "Alpha"),
        ("Distrito Industrial Centro", "Centro"),
        # Prefixos canônicos do nome do bairro DEVEM ser preservados
        ("Jardim Paulista", "Jardim Paulista"),
        ("Vila Mariana", "Vila Mariana"),
        ("Centro", "Centro"),
        ("Bela Vista", "Bela Vista"),
        # Abreviação JD → Jardim
        ("JD. PAULISTA", "Jardim Paulista"),
        ("JD PAULISTA", "Jardim Paulista"),
        # "JD. RESIDENCIAL X" expande JD→Jardim e em seguida o strip de
        # 'jardim residencial' elimina o sufixo 'Residencial', sobrando o
        # nome real do bairro ('X'). Mesmo comportamento de
        # 'Jardim Residencial X' → 'X' (não é um nome de bairro real,
        # é um nome de loteamento).
        ("JD. RESIDENCIAL X", "X"),
        ("Jardim Residencial X", "X"),
        # Prefixos aninhados
        ("LOTEAMENTO RESIDENCIAL PARQUE DOS PINHEIROS", "Parque dos Pinheiros"),
        # Edge cases
        ("", None),
        (None, None),
        ("   ", None),
        ("LOTEAMENTO", None),  # só o prefixo, vira vazio
    ],
)
def test_sanitize_neighborhood(raw: str | None, expected: str | None) -> None:
    assert sanitize_neighborhood(raw) == expected


# =============================================================================
# sanitize_street
# =============================================================================
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # DF: remove 'QUADRA' redundante antes de QR/QN/QI/QS/etc.
        ("QUADRA QN 407", "QN 407"),
        ("Quadra QR 108", "QR 108"),
        ("QUADRA: QI 5", "QI 5"),
        ("Q. QS 21", "QS 21"),
        ("SQN 308", "SQN 308"),  # já limpo, preserva
        # Logradouros normais NÃO são afetados
        ("Rua das Flores", "Rua das Flores"),
        ("Avenida Paulista", "Avenida Paulista"),
        # Edge cases
        ("", None),
        (None, None),
        ("   ", None),
        ("QUADRA", "QUADRA"),  # 'QUADRA' isolado é o próprio nome — preserva
    ],
)
def test_sanitize_street(raw: str | None, expected: str | None) -> None:
    assert sanitize_street(raw) == expected


# =============================================================================
# sanitize_number
# =============================================================================
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 'sem número' em variantes → None
        ("SN", None),
        ("S/N", None),
        ("S.N.", None),
        ("s/n", None),
        ("S/Nº", None),
        ("s/n°", None),
        # números reais ficam intactos
        ("123", "123"),
        ("123-A", "123-A"),
        ("0", "0"),  # não consideramos 0 como sem-número
        # edge cases
        ("", None),
        (None, None),
    ],
)
def test_sanitize_number(raw: str | None, expected: str | None) -> None:
    assert sanitize_number(raw) == expected


# =============================================================================
# sanitize_image_url
# =============================================================================
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # válidas
        (
            "https://cdn.leiloeiro.com/imovel/12345/foto1-large.jpg",
            "https://cdn.leiloeiro.com/imovel/12345/foto1-large.jpg",
        ),
        (
            "https://resizer.glbimg.com/imovel/abc.jpeg",
            "https://resizer.glbimg.com/imovel/abc.jpeg",
        ),
        # CDN sem extensão (imgix-style) — aceito
        (
            "https://imgix.example/foo?w=1280&h=720",
            "https://imgix.example/foo?w=1280&h=720",
        ),
        # logo/ícone/banner → rejeita
        ("https://www.zuk.com.br/static/logo.png", None),
        ("https://example.com/favicon.ico", None),
        ("https://example.com/sprite.svg", None),
        ("https://cdn.x/banners/promo.jpg", None),
        ("https://cdn.x/icons/whatsapp.png", None),
        # mapa estático → rejeita
        ("https://maps.googleusercontent.com/maps?...", None),
        # thumbnails → rejeita
        ("https://cdn.x/imovel/123/thumb_50x50.jpg", None),
        ("https://cdn.x/thumbs/foto.jpg", None),
        # url relativa / vazia / não http → rejeita
        ("/media/foto.jpg", None),
        ("", None),
        (None, None),
        ("javascript:alert(1)", None),
        # extensão errada (PDF, vídeo) → rejeita
        ("https://cdn.x/imovel/123/edital.pdf", None),
        ("https://cdn.x/imovel/123/walkthrough.mp4", None),
    ],
)
def test_sanitize_image_url(raw: str | None, expected: str | None) -> None:
    assert sanitize_image_url(raw) == expected
