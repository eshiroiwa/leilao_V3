"""Schemas Pydantic para o Agente 1.

A LLM é forçada a retornar exatamente este JSON via *structured output*.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ExtractedAddress(BaseModel):
    """Endereço como aparece no anúncio (ainda NÃO normalizado pelo Google)."""

    street: str | None = Field(None, description="Logradouro (rua/av./travessa).")
    number: str | None = Field(None, description="Número, ex.: '123', 's/n', '123-A'.")
    complement: str | None = Field(None, description="Apto, bloco, sala, etc.")
    neighborhood: str | None = Field(None, description="Bairro.")
    city: str | None = Field(None, description="Município.")
    state: str | None = Field(
        None,
        description="UF em 2 letras maiúsculas (ex.: 'SP', 'RJ').",
        max_length=2,
    )
    postal_code: str | None = Field(
        None,
        description="CEP no formato 99999-999 (ou apenas dígitos).",
    )
    full_address: str | None = Field(
        None,
        description="Endereço completo em uma única linha, como apresentado.",
    )


class ExtractedAuctionData(BaseModel):
    """Estrutura mínima esperada de cada lote de leilão."""

    auctioneer_slug: str | None = Field(
        None,
        description=(
            "Slug do leiloeiro deduzido do domínio (ex.: 'zuk', 'mega-leiloes', "
            "'sodre-santoro')."
        ),
    )
    auctioneer_lot_id: str | None = Field(
        None, description="Número/identificador do lote no leiloeiro."
    )
    auctioneer_name: str | None = Field(
        None,
        description=(
            "Nome do leiloeiro tal como aparece no edital (texto livre, sem "
            "limpeza). Em editais Caixa o padrão típico é 'Leiloeiro(a): "
            "FULANO DE TAL'. Devolva apenas o nome próprio, sem o rótulo "
            "'Leiloeiro(a):'. Quando o markdown indica explicitamente "
            "'Compra Direta' ou 'Venda Online' (Caixa) e NÃO aparece nome, "
            "devolva null — sinal de que não há leiloeiro/comissão."
        ),
    )

    title: str | None = Field(None, description="Título do anúncio.")
    description: str | None = Field(None, description="Descrição livre do imóvel.")
    property_type: str | None = Field(
        None,
        description=(
            "Tipo do imóvel normalizado em minúsculas: 'apartamento', 'casa', "
            "'terreno', 'comercial', 'rural', 'galpão', 'outro'."
        ),
    )
    image_url: str | None = Field(
        None,
        description=(
            "URL ABSOLUTA (https://...) da PRIMEIRA fotografia do imóvel "
            "encontrada no markdown. Imagens aparecem no formato ![alt](url). "
            "IGNORE logos do leiloeiro, ícones de UI, banners, ads, mapas "
            "estáticos e thumbnails de outros lotes. PRIORIZE URLs que pareçam "
            "fotografias do imóvel — geralmente em CDN com sufixos .jpg/.jpeg/"
            ".png/.webp e tamanhos grandes (palavras como 'large', 'big', "
            "ou path com 'imovel', 'lote', 'foto', 'image'). "
            "Se nada parecer foto do imóvel, devolva null."
        ),
    )

    address: ExtractedAddress = Field(default_factory=ExtractedAddress)

    area_total_m2: float | None = Field(None, description="Área total em m².")
    area_built_m2: float | None = Field(None, description="Área construída em m².")
    bedrooms: int | None = Field(None, ge=0, le=50)
    bathrooms: int | None = Field(None, ge=0, le=50)
    parking_spaces: int | None = Field(None, ge=0, le=50)

    appraisal_value: float | None = Field(None, description="Valor de avaliação em BRL.")
    minimum_bid_first: float | None = Field(None, description="Lance mínimo da 1ª praça em BRL.")
    minimum_bid_second: float | None = Field(None, description="Lance mínimo da 2ª praça em BRL.")
    current_bid: float | None = Field(None, description="Lance atual, se exibido, em BRL.")

    first_auction_at: datetime | None = Field(
        None, description="Data/hora da 1ª praça (ISO 8601 com timezone se possível)."
    )
    second_auction_at: datetime | None = Field(
        None, description="Data/hora da 2ª praça (ISO 8601 com timezone se possível)."
    )

    legal_status: str | None = Field(
        None,
        description="'judicial', 'extrajudicial' ou 'particular'.",
    )
    occupancy_status: str | None = Field(
        None,
        description="'desocupado', 'ocupado' ou 'desconhecido'.",
    )
    encumbrances_summary: str | None = Field(
        None,
        description="Resumo de ônus, dívidas, ações ou observações jurídicas relevantes.",
    )

    # ---- Custos do edital (alimentam o Agente 3 — Análise de Oportunidade) ----
    iptu_arrears: float | None = Field(
        None,
        ge=0,
        description=(
            "IPTU em atraso EXPLICITAMENTE mencionado no edital, em BRL. "
            "Procure por trechos como 'IPTU em atraso', 'débitos de IPTU', "
            "'tributos municipais devidos', 'IPTU vencido'. NÃO inclua o IPTU "
            "do exercício corrente; só o atrasado/vencido. Se o edital diz "
            "apenas 'sob responsabilidade do arrematante' SEM valor, devolva null."
        ),
    )
    condo_arrears: float | None = Field(
        None,
        ge=0,
        description=(
            "Condomínio em atraso EXPLICITAMENTE mencionado no edital, em BRL. "
            "Procure por 'condomínio em atraso', 'débitos condominiais', "
            "'taxas de condomínio em aberto'. Se o valor não está informado, "
            "devolva null (NUNCA chute)."
        ),
    )
    auctioneer_fee_pct: float | None = Field(
        None,
        ge=0,
        le=0.20,
        description=(
            "Comissão do leiloeiro como FRAÇÃO (0.05 = 5%). Padrão histórico "
            "do mercado: 5% para PF/PJ. Em VENDA DIRETA / ONLINE da CAIXA "
            "geralmente não há comissão (devolva 0.0). Se o edital cita um "
            "percentual diferente (ex.: 5%, 6%, 3%), devolva esse valor como "
            "fração. Se nada for dito, devolva null para usarmos o default."
        ),
    )
