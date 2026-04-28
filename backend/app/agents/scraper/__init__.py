"""AGENTE 1 — Scraper e Normalizador Geográfico."""

from app.agents.scraper.graph import build_scraper_graph, run_scraper
from app.agents.scraper.state import ScraperState

__all__ = ["ScraperState", "build_scraper_graph", "run_scraper"]
