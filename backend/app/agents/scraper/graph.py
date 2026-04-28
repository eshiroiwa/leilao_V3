"""Construção e execução do grafo LangGraph do Agente 1."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from app.agents.scraper.nodes import (
    node_extract_data,
    node_geocode,
    node_persist,
    node_scrape_url,
    node_validate_address,
)
from app.agents.scraper.state import ScraperState
from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Edges condicionais — abortam o pipeline se houver erro fatal
# --------------------------------------------------------------------------- #
def _has_fatal_error(state: ScraperState) -> bool:
    return bool(state.get("errors"))


def _route_after_scrape(state: ScraperState) -> str:
    return END if _has_fatal_error(state) else "extract_data"


def _route_after_extract(state: ScraperState) -> str:
    return END if _has_fatal_error(state) else "validate_address"


def _route_after_validate(state: ScraperState) -> str:
    return "geocode"


def _route_after_geocode(state: ScraperState) -> str:
    return "persist"


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_scraper_graph() -> Any:
    """Constrói e compila o grafo do Agente 1."""
    graph = StateGraph(ScraperState)

    graph.add_node("scrape_url", node_scrape_url)
    graph.add_node("extract_data", node_extract_data)
    graph.add_node("validate_address", node_validate_address)
    graph.add_node("geocode", node_geocode)
    graph.add_node("persist", node_persist)

    graph.add_edge(START, "scrape_url")
    graph.add_conditional_edges("scrape_url", _route_after_scrape, [END, "extract_data"])
    graph.add_conditional_edges("extract_data", _route_after_extract, [END, "validate_address"])
    graph.add_conditional_edges("validate_address", _route_after_validate, ["geocode"])
    graph.add_conditional_edges("geocode", _route_after_geocode, ["persist"])
    graph.add_edge("persist", END)

    return graph.compile()


# Compilamos uma vez na importação (cache em processo).
_compiled_graph = None


def _get_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_scraper_graph()
    return _compiled_graph


# --------------------------------------------------------------------------- #
# Runner com auditoria em agent_runs
# --------------------------------------------------------------------------- #
def run_scraper(url: str) -> dict[str, Any]:
    """Executa o Agente 1 sincronamente e registra o run em ``agent_runs``."""
    sb = get_supabase_service()
    started = time.perf_counter()

    try:
        run = sb.insert_agent_run(
            {
                "agent_name": "scraper",
                "input": {"url": url},
                "status": "running",
            }
        )
    except SupabaseError as exc:
        logger.warning("agent.scraper.audit.insert_failed", error=str(exc))
        run = {}

    run_id: str | None = run.get("id")

    initial: ScraperState = {"url": url}  # type: ignore[typeddict-item]
    final_state: ScraperState

    try:
        final_state = _get_graph().invoke(initial)  # type: ignore[assignment]
    except Exception as exc:
        logger.exception("agent.scraper.unhandled_exception")
        if run_id:
            try:
                sb.update_agent_run(
                    run_id,
                    {
                        "status": "failed",
                        "error_message": str(exc),
                        "finished_at": datetime.now(UTC).isoformat(),
                        "duration_ms": int((time.perf_counter() - started) * 1000),
                    },
                )
            except SupabaseError:
                pass
        raise

    duration_ms = int((time.perf_counter() - started) * 1000)
    status = "failed" if final_state.get("errors") else "success"
    output_payload: dict[str, Any] = {
        "property_id": final_state.get("property_id"),
        "warnings": final_state.get("warnings"),
        "errors": final_state.get("errors"),
        "geocoding_confidence": final_state.get("geocoding_confidence"),
    }

    if run_id:
        try:
            sb.update_agent_run(
                run_id,
                {
                    "status": status,
                    "property_id": final_state.get("property_id"),
                    "output": output_payload,
                    "duration_ms": duration_ms,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "error_message": (
                        "; ".join(final_state.get("errors") or []) or None
                    ),
                },
            )
        except SupabaseError as exc:
            logger.warning("agent.scraper.audit.update_failed", error=str(exc))

    # Garante UUID serializável caso venha como objeto
    pid = final_state.get("property_id")
    if isinstance(pid, UUID):
        final_state["property_id"] = str(pid)

    return {
        "run_id": run_id,
        "status": status,
        "duration_ms": duration_ms,
        "property_id": final_state.get("property_id"),
        "warnings": final_state.get("warnings") or [],
        "errors": final_state.get("errors") or [],
        "saved_property": final_state.get("saved_property"),
    }
