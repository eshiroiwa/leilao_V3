"""AGENTE 4 — Análise Aprofundada (Deep Analysis).

Estuda **vizinhança e contexto** do imóvel, complementando o AGENTE 3
(opportunity). Retorna scores qualitativos por dimensão + síntese consolidada.

Decisões de projeto explicitadas:

* **Sem LangGraph**: AGENTE 4 é I/O-bound com fan-out paralelo puro;
  ``asyncio.gather`` é mais natural e mais rápido. AGENTES 1 e 2 continuam
  com LangGraph porque têm steps condicionais.
* **Workflow assíncrono**: ``status pending → running → completed | failed``
  persistido na tabela ``deep_analyses``. O frontend faz polling.
* **Sem score de segurança**: dados oficiais brasileiros não descem ao
  bairro de forma confiável. Decisão consciente.
"""

from app.agents.deep.schemas import (
    AmenitiesResult,
    DemographicsResult,
    DeepAnalysisInput,
    DeepAnalysisResult,
    DeepAnalysisStatus,
    FlippingResult,
    OutlierResult,
    PriceTrendResult,
    PriorAuctionResult,
    SourceDocument,
    UrbanRisksResult,
)
from app.agents.deep.service import (
    enqueue_deep_analysis,
    get_or_create_deep_analysis,
    run_deep_analysis_inline,
)

__all__ = [
    "AmenitiesResult",
    "DemographicsResult",
    "DeepAnalysisInput",
    "DeepAnalysisResult",
    "DeepAnalysisStatus",
    "FlippingResult",
    "OutlierResult",
    "PriceTrendResult",
    "PriorAuctionResult",
    "SourceDocument",
    "UrbanRisksResult",
    "enqueue_deep_analysis",
    "get_or_create_deep_analysis",
    "run_deep_analysis_inline",
]
