"""CLI utilitário para rodar o Agente 1 fora do FastAPI.

Uso:
    python -m scripts.run_scraper https://www.zuk.com.br/leiloes/imoveis/123
"""

from __future__ import annotations

import json
import sys

from app.agents.scraper import run_scraper
from app.core.logging import configure_logging


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.run_scraper <URL>", file=sys.stderr)
        return 2

    configure_logging()
    url = sys.argv[1]
    result = run_scraper(url)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
