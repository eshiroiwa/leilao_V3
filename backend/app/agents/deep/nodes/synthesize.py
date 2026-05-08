"""Nó SYNTHESIZE — LLM consolidador.

Junta todos os sub-resultados num parecer unificado:

* ``overall_score`` 1-5 (média ponderada dos sinais)
* parágrafo de resumo em português, conciso, sem "achismo"
* ``red_flags`` (atenção)
* ``green_flags`` (pontos a favor)
* ``recommendations`` (passos de diligência)

Decisão importante: o **LLM não inventa números**. O prompt é explícito
em só consolidar/parafrasear o que recebeu como input estruturado. Se um
sub-resultado vem com ``confidence: LOW``, isso DEVE ficar refletido no
parecer.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_openai import ChatOpenAI

from app.agents.deep.schemas import (
    AmenitiesResult,
    DemographicsResult,
    FlippingResult,
    LiquidityResult,
    OutlierResult,
    PriceTrendResult,
    PriorAuctionResult,
    SynthesisOutput,
    UrbanRisksResult,
)
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _bundle_to_dict(
    *,
    demographics: DemographicsResult | None,
    liquidity: LiquidityResult | None,
    outlier: OutlierResult | None,
    flipping: FlippingResult | None,
    price_trend: PriceTrendResult | None,
    amenities: AmenitiesResult | None,
    urban_risks: UrbanRisksResult | None,
    prior_auction: PriorAuctionResult | None,
) -> dict[str, Any]:
    """Reúne os sub-resultados num dict serializado para alimentar o LLM."""

    def _dump(model: Any) -> Any:
        return model.model_dump(exclude_none=True) if model is not None else None

    return {
        "demographics": _dump(demographics),
        "liquidity": _dump(liquidity),
        "outlier": _dump(outlier),
        "flipping": _dump(flipping),
        "price_trend": _dump(price_trend),
        "amenities": _dump(amenities),
        "urban_risks": _dump(urban_risks),
        "prior_auction": _dump(prior_auction),
    }


_SYSTEM = """Você é um analista sênior do mercado imobiliário brasileiro,
especialista em leilões judiciais e extrajudiciais. Você está consolidando
um relatório de DUE DILIGENCE de bairro/imóvel para um investidor.

REGRAS RÍGIDAS:
1. NÃO invente números. Use APENAS os dados estruturados que você recebeu.
2. Se um sub-resultado tem confidence='LOW', isso DEVE aparecer no resumo
   ("dados insuficientes para concluir X").
3. Tom: direto, técnico, sem floreios. Português do Brasil.
4. Red flags = pontos que o investidor PRECISA olhar com cuidado.
5. Green flags = pontos genuinamente favoráveis (não inflar para "balancear").
6. Recommendations = ações concretas de diligência (visitar matrícula,
   confirmar IPTU, etc.). Máximo 5.
7. overall_score: 1-5. Use a regra:
   - 5: contexto claramente favorável (alta liquidez, sem outlier ruim,
        teto de mercado interessante, nenhum red flag duro).
   - 4: bom, com 1-2 ressalvas operacionais.
   - 3: misto. Há sinais bons e ruins equilibrados.
   - 2: cenário desfavorável (vários red flags ou amostra muito rasa).
   - 1: claramente arriscado (outlier extremo, riscos urbanos confirmados,
        liquidez muito baixa).
"""


async def synthesize(
    *,
    property_summary: dict[str, Any],
    demographics: DemographicsResult | None,
    liquidity: LiquidityResult | None,
    outlier: OutlierResult | None,
    flipping: FlippingResult | None,
    price_trend: PriceTrendResult | None,
    amenities: AmenitiesResult | None,
    urban_risks: UrbanRisksResult | None,
    prior_auction: PriorAuctionResult | None,
) -> SynthesisOutput:
    bundle = _bundle_to_dict(
        demographics=demographics,
        liquidity=liquidity,
        outlier=outlier,
        flipping=flipping,
        price_trend=price_trend,
        amenities=amenities,
        urban_risks=urban_risks,
        prior_auction=prior_auction,
    )

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_extraction_model,
        api_key=settings.openai_api_key.get_secret_value(),
        temperature=0.2,
    ).with_structured_output(SynthesisOutput)

    user = (
        "IMÓVEL EM ANÁLISE:\n"
        f"{property_summary}\n\n"
        "SUB-RESULTADOS DAS DIMENSÕES:\n"
        f"{bundle}\n\n"
        "Agora produza o relatório consolidado seguindo as REGRAS RÍGIDAS."
    )

    try:
        out: SynthesisOutput = await asyncio.to_thread(
            llm.invoke,
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        )  # type: ignore[assignment]
    except Exception as exc:
        logger.error("deep.synthesize.llm_failed", error=str(exc))
        # Degrade graciosamente — não deixar o pipeline inteiro morrer.
        return SynthesisOutput(
            overall_score=3,
            summary_text=(
                "Não foi possível gerar a síntese automática (falha do "
                "LLM). Consulte os sub-resultados individualmente."
            ),
            red_flags=[],
            green_flags=[],
            recommendations=[
                "Revisar manualmente os sub-resultados (outlier, "
                "vizinhança, riscos urbanos) antes de decidir."
            ],
        )

    return out
