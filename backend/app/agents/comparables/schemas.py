"""Schemas Pydantic do AGENTE 2.

``ExtractedListing`` é o que pedimos ao LLM (structured output) ao processar
o markdown de um anúncio. Mantemos os campos PROPOSITALMENTE simples — o
objetivo é alimentar a função de scoring/pricing, não reproduzir o anúncio.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PropertyType = Literal[
    "apartamento", "casa", "terreno", "comercial", "rural", "galpao", "outro"
]
AdvertiserType = Literal["imobiliaria", "autonomo", "construtora", "desconhecido"]


class ExtractedListing(BaseModel):
    """Um anúncio de venda, extraído por LLM a partir do markdown.

    Todos os campos opcionais: o LLM deve devolver ``null`` quando não houver
    informação clara — NUNCA inventar.
    """

    # Identificação
    title: str | None = Field(default=None)
    property_type: PropertyType | None = Field(default=None)
    condo_name: str | None = Field(
        default=None,
        description=(
            "Nome do condomínio/edifício, se mencionado. Ex.: 'Edifício "
            "Jardim das Acácias', 'Residencial Vila Verde'. Sem prefixos "
            "ruidosos como 'LOTEAMENTO', 'CONJUNTO HABITACIONAL'."
        ),
    )

    # Endereço
    street: str | None = Field(default=None)
    number: str | None = Field(default=None)
    neighborhood: str | None = Field(default=None)
    city: str | None = Field(default=None)
    state: str | None = Field(default=None, description="UF, 2 letras maiúsculas.")
    postal_code: str | None = Field(default=None, description="CEP no formato 99999-999.")

    # Características físicas
    area_total_m2: float | None = Field(default=None, ge=0)
    area_useful_m2: float | None = Field(default=None, ge=0)
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    parking_spaces: int | None = Field(default=None, ge=0)
    amenities: list[str] | None = Field(default=None)

    # Valores
    listed_price: float | None = Field(default=None, ge=0)
    monthly_condo_fee: float | None = Field(default=None, ge=0)
    iptu: float | None = Field(default=None, ge=0)

    # Sinais de qualidade do anúncio (úteis para reliability_score).
    photos_count: int | None = Field(default=None, ge=0)
    advertiser_type: AdvertiserType | None = Field(default=None)


class ListingBatch(BaseModel):
    """Batch usado quando o LLM extrai vários anúncios em uma chamada só.

    O índice em ``listings`` deve casar com a ordem em que mandamos os
    markdowns no prompt (preservar paridade é responsabilidade do caller).
    """

    listings: list[ExtractedListing]
