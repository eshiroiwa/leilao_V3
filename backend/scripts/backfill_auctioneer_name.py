"""Backfill: extrai ``auctioneer_name`` das ``properties`` existentes.

Lê ``raw_markdown`` de cada imóvel e procura o padrão típico do edital
Caixa::

    Leiloeiro(a): NOME DO LEILOEIRO
    Data do 1º Leilão - dd/mm/aaaa - hh'h'mm

Quando encontra, persiste o nome em ``properties.auctioneer_name``.
Imóveis que já têm ``auctioneer_id`` populado (portal próprio: Zuk,
Mega, Biasi…) são pulados — esses já são leilão por definição e não
precisam do nome para o AGENTE 3.

Imóveis com ``Compra Direta`` / ``Venda Online`` no markdown e SEM
leiloeiro nominal ficam com ``auctioneer_name=NULL`` (venda direta da
Caixa, sem comissão).

Como bônus, este script também corrige um efeito colateral do prompt
antigo do Agente 1, que setava ``auctioneer_fee_pct=0.0`` sempre que
detectava "domínio Caixa" — mesmo quando havia leiloeiro nominal. Para
imóveis em que descobrimos ``auctioneer_name`` E o ``auctioneer_fee_pct``
gravado é exatamente ``0.0``, o script reseta o campo para ``NULL``,
deixando o AGENTE 3 aplicar o default de 5% (regra "presença de
leiloeiro = tem comissão").

Idempotente: pode rodar quantas vezes quiser. Use ``--dry-run`` para
ver o que seria feito sem alterar o banco.
"""

from __future__ import annotations

import argparse
import re
from typing import Final

from app.services.supabase_service import get_supabase_service

# Captura "Leiloeiro(a): NOME" parando na primeira quebra de linha,
# bullet ou marcador de "Data do … Leilão" (com ou sem ordinal).
LEILOEIRO_RE: Final = re.compile(
    r"Leiloeiro\(a\)\s*:\s*(?P<name>[^\n\r]+?)\s*(?=\s*Data\s+do|[\n\r]|$)",
    re.IGNORECASE,
)


def _extract_name(markdown: str | None) -> str | None:
    """Roda o regex e devolve o nome limpo (sem markdown bold/itálico)."""
    if not markdown:
        return None
    m = LEILOEIRO_RE.search(markdown)
    if not m:
        return None
    raw = m.group("name").strip()
    cleaned = raw.strip("*_ \t")
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Não persiste nada.")
    args = parser.parse_args()

    sb = get_supabase_service()

    res = (
        sb._client.table("properties")
        .select(
            "id,title,source_url,auctioneer_id,auctioneer_name,"
            "auctioneer_fee_pct,raw_markdown"
        )
        .execute()
    )
    rows = res.data or []
    print(f"→ {len(rows)} properties carregadas\n")

    name_updated = 0
    name_already_set = 0
    skipped_with_id = 0
    no_name_in_md = 0
    fee_reset = 0

    for row in rows:
        pid = row["id"]
        title = (row.get("title") or "")[:35]
        if row.get("auctioneer_id"):
            skipped_with_id += 1
            print(f"  {pid[:8]} ⏭  {title:37} (já tem auctioneer_id)")
            continue
        existing = (row.get("auctioneer_name") or "").strip()
        new_name = _extract_name(row.get("raw_markdown"))

        if not new_name:
            no_name_in_md += 1
            print(f"  {pid[:8]} ✗  {title:37} (sem 'Leiloeiro(a):' no markdown)")
            continue

        # Atualização do auctioneer_name (idempotente).
        update_payload: dict = {}
        if existing == new_name:
            name_already_set += 1
            line = f"  {pid[:8]} =  {title:37} já='{existing[:35]}'"
        else:
            update_payload["auctioneer_name"] = new_name
            line = f"  {pid[:8]} ✓  {title:37} → '{new_name[:35]}'"
            name_updated += 1

        # Bug histórico do prompt antigo: se o markdown tem leiloeiro mas
        # o LLM gravou auctioneer_fee_pct=0.0 (heurística "domínio Caixa
        # = 0%"), reseta para NULL para o AGENTE 3 aplicar o default 5%.
        # Não mexemos quando o valor é diferente (ex.: 0.05 ou outro
        # percentual) — esses são dados confiáveis vindos do edital.
        existing_fee = row.get("auctioneer_fee_pct")
        if existing_fee == 0 or existing_fee == 0.0:
            update_payload["auctioneer_fee_pct"] = None
            line += "  [reset fee 0.0→NULL]"
            fee_reset += 1

        print(line)
        if update_payload and not args.dry_run:
            sb._client.table("properties").update(update_payload).eq(
                "id", pid
            ).execute()

    print(
        f"\nResumo:\n"
        f"  auctioneer_name atualizado   = {name_updated}\n"
        f"  auctioneer_name já correto   = {name_already_set}\n"
        f"  auctioneer_fee_pct resetado  = {fee_reset} (eram 0.0 mas há leiloeiro)\n"
        f"  com auct_id                  = {skipped_with_id} (não precisam de auctioneer_name)\n"
        f"  sem leiloeiro                = {no_name_in_md} (Compra Direta / Venda Online)\n"
    )
    if args.dry_run:
        print("(dry-run; nada foi gravado.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
