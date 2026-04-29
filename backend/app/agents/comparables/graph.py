"""LangGraph do AGENTE 2 — Avaliador Comparativo de Mercado (CMA).

Desenho do grafo (com loop de expansão controlado em DUAS camadas):

    load_target
        │
        ├─(erros?)→ END
        ▼
    build_query
        ▼
    search_listings ◄────────retry_search────┐
        ▼                                    │
    fetch_candidates                         │
        ▼                                    │
    extract_listings                         │
        ▼                                    │
    enrich_geo                               │
        ▼                                    │
    score_similarity ◄─retry_score─┐         │
        ▼                          │         │
    check_minimum ─────────────────┘         │
        │                                    │
        ├──── retry_search ──────────────────┘
        │
        └─(não retry)─→ estimate_price → persist → END

* ``retry_score``  : só re-roda o `score_similarity` com um raio maior
  (mesma estratégia, ZERO chamadas externas).
* ``retry_search`` : refaz busca/scrape/LLM porque trocamos de estratégia.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.comparables.nodes import (
    node_build_query,
    node_check_minimum,
    node_enrich_geo,
    node_estimate_price,
    node_extract_listings,
    node_fetch_candidates,
    node_load_target,
    node_persist,
    node_score_similarity,
    node_search_listings,
)
from app.agents.comparables.state import ComparablesState
from app.core.logging import get_logger
from app.services.supabase_service import get_supabase_service

logger = get_logger(__name__)

_AGENT_NAME = "comparables"


def _has_errors(state: ComparablesState) -> bool:
    return bool(state.get("errors"))


def _route_after_load(state: ComparablesState) -> str:
    return "abort" if _has_errors(state) else "ok"


def _route_after_check(state: ComparablesState) -> str:
    """Decide o próximo passo após o check de mínimo:

    - ``retry_score``  ⇒ apenas re-escora com novo raio (mesma estratégia).
    - ``retry_search`` ⇒ refaz busca/scrape/LLM (nova estratégia).
    - ``estimate``     ⇒ vamos para o pricing.
    """
    if state.get("should_retry_score"):
        return "retry_score"
    if state.get("should_retry_search"):
        return "retry_search"
    return "estimate"


def build_comparables_graph():
    g = StateGraph(ComparablesState)

    g.add_node("load_target", node_load_target)
    g.add_node("build_query", node_build_query)
    g.add_node("search_listings", node_search_listings)
    g.add_node("fetch_candidates", node_fetch_candidates)
    g.add_node("extract_listings", node_extract_listings)
    g.add_node("enrich_geo", node_enrich_geo)
    g.add_node("score_similarity", node_score_similarity)
    g.add_node("check_minimum", node_check_minimum)
    g.add_node("estimate_price", node_estimate_price)
    g.add_node("persist", node_persist)

    g.add_edge(START, "load_target")
    g.add_conditional_edges(
        "load_target",
        _route_after_load,
        {"ok": "build_query", "abort": END},
    )
    g.add_edge("build_query", "search_listings")
    g.add_edge("search_listings", "fetch_candidates")
    g.add_edge("fetch_candidates", "extract_listings")
    g.add_edge("extract_listings", "enrich_geo")
    g.add_edge("enrich_geo", "score_similarity")
    g.add_edge("score_similarity", "check_minimum")

    g.add_conditional_edges(
        "check_minimum",
        _route_after_check,
        {
            "retry_score": "score_similarity",
            "retry_search": "search_listings",
            "estimate": "estimate_price",
        },
    )
    g.add_edge("estimate_price", "persist")
    g.add_edge("persist", END)

    return g.compile()


def run_comparables(property_id: str) -> dict[str, Any]:
    """Executa o agente para um property e devolve o estado final.

    Faz auditoria em ``agent_runs`` (insere ao iniciar, atualiza ao terminar),
    igual ao padrão do AGENTE 1.
    """
    sb = get_supabase_service()
    started_at = time.perf_counter()

    run = sb.insert_agent_run(
        {
            "agent_name": _AGENT_NAME,
            "property_id": property_id,
            "input": {"property_id": property_id},
            "status": "running",
        }
    )
    run_id = run.get("id")

    initial: ComparablesState = {
        "property_id": property_id,
        "agent_run_id": run_id or "",
        "warnings": [],
        "errors": [],
        "firecrawl_calls": 0,
        "llm_calls": 0,
        "cost_estimate_brl": 0.0,
    }

    graph = build_comparables_graph()
    try:
        # `recursion_limit` cobre loops de expansão (+ folga). Cada iteração
        # do loop usa ~6 nodes; permitimos até 4 expansões.
        final: ComparablesState = graph.invoke(initial, {"recursion_limit": 30})
        status = "failed" if final.get("errors") else "success"
        error_msg = "; ".join(final.get("errors") or []) or None
    except Exception as exc:
        logger.exception("cma.graph.exception", error=str(exc))
        final = {**initial, "errors": [str(exc)]}
        status = "failed"
        error_msg = str(exc)

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    if run_id:
        sb.update_agent_run(
            run_id,
            {
                "status": status,
                "error_message": error_msg,
                "output": {
                    "valuation_id": final.get("valuation_id"),
                    "confidence": final.get("confidence"),
                    "estimated_price": final.get("estimated_price"),
                    "comparables_used": sum(
                        1 for s in (final.get("scored_comparables") or []) if s.get("used")
                    ),
                    "firecrawl_calls": final.get("firecrawl_calls"),
                    "llm_calls": final.get("llm_calls"),
                    "cost_estimate_brl": final.get("cost_estimate_brl"),
                },
                "finished_at": datetime.now(UTC).isoformat(),
                "duration_ms": duration_ms,
            },
        )

    return final
