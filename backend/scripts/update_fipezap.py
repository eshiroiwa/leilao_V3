"""Atualiza ``city_ppm2_stats`` com o índice FipeZAP mensal.

Baixa o PDF da FipeZAP (residencial venda) via Firecrawl, parseia o ranking
de cidades e faz upsert na tabela ``city_ppm2_stats``. Idempotente — se
rodar duas vezes no mesmo mês, o segundo upsert substitui o primeiro com
o mesmo valor.

Uso:

    # mês corrente (publicado no ~dia 5 do mês seguinte):
    python scripts/update_fipezap.py

    # mês específico:
    python scripts/update_fipezap.py --year 2026 --month 1

    # dry-run (não persiste, só mostra o que seria feito):
    python scripts/update_fipezap.py --dry-run

Pode ser agendado mensalmente via cron / systemd timer no dia 10 às 03:00.
"""

from __future__ import annotations

import argparse
from datetime import date

from app.core.logging import configure_logging, get_logger
from app.services.fipezap_service import get_fipezap_service
from app.services.supabase_service import get_supabase_service

logger = get_logger("update_fipezap")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    today = date.today()
    parser.add_argument("--year", type=int, default=today.year)
    parser.add_argument("--month", type=int, default=today.month)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não persiste no Supabase — só mostra as leituras parseadas.",
    )
    args = parser.parse_args()

    configure_logging()

    readings = get_fipezap_service().fetch_and_parse(args.year, args.month)
    if not readings:
        logger.error("update_fipezap.empty", year=args.year, month=args.month)
        return 1

    print(f"FipeZAP {args.year}-{args.month:02d}: {len(readings)} cidade(s)")
    for r in readings[:10]:
        print(f"  {r.city} ({r.state}): R$ {r.mean_ppm2_brl:>10,.2f}/m²")
    if len(readings) > 10:
        print(f"  ... +{len(readings) - 10} cidades")

    if args.dry_run:
        print("\n[dry-run] não persistindo.")
        return 0

    sb = get_supabase_service()
    rows = [
        {
            "city": r.city,
            "state": r.state,
            "mean_ppm2_brl": r.mean_ppm2_brl,
            "asof_year": r.year,
            "asof_month": r.month,
            "source": "fipezap",
        }
        for r in readings
    ]
    # Upsert: conflito em (city, state, asof_year, asof_month) atualiza valor.
    sb.client.table("city_ppm2_stats").upsert(
        rows, on_conflict="city,state,asof_year,asof_month"
    ).execute()
    print(f"\n✓ Upserted {len(rows)} row(s) em city_ppm2_stats.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
