"""Cliente da API Pública do DataJud (CNJ).

Consulta metadados de processos judiciais em todos os tribunais do país.
A API é GRATUITA mas exige uma "chave pública" obtida no portal do CNJ
(Portaria CNJ 160/2020). A chave é a MESMA para todos os consumidores —
é só um identificador de uso, não um segredo. Pode vir de env var
``CNJ_DATAJUD_API_KEY`` ou usar o default público abaixo.

Cada tribunal expõe seu próprio endpoint:
    https://api-publica.datajud.cnj.jus.br/api_publica_{TRIBUNAL}/_search

Onde ``{TRIBUNAL}`` é o slug do tribunal (ex.: ``tjsp``, ``tjrj``).
NÃO há endpoint federado — para "todos os processos do CPF X" seria
preciso iterar pelos 90+ tribunais. Por isso defaultamos para o TJ da
UF do imóvel (provável foro do processo de execução que originou o leilão).

Uso no Agente Legal:
  1. Recebe ``owner_cpf_cnpj`` do property (extraído pelo Scraper).
  2. Consulta TJ-UF por documento da parte.
  3. Classifica processos em "críticos" (execuções fiscais, execução de
     título extrajudicial, ações de despejo, indisponibilidade) vs
     "neutros" (outros).
  4. Devolve contagem + amostra dos críticos como red_flags.

Cache em memória por (cpf_cnpj, tribunal): TTL 7 dias.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Final

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class DataJudServiceError(RuntimeError):
    """Falha ao consultar o DataJud."""


# Chave pública atual (documentada pelo CNJ — não é segredo). Override via
# env var quando o CNJ rotacionar.
_DEFAULT_PUBLIC_KEY: Final[str] = (
    "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
)
_BASE_URL: Final[str] = "https://api-publica.datajud.cnj.jus.br"
_CACHE_TTL_SECONDS: Final[int] = 7 * 24 * 3600  # 7 dias


# Classes processuais (Tabela Processual Unificada do CNJ) que indicam
# risco patrimonial específico para o arrematante: se há processo dessas
# classes contra o proprietário, há grande chance de o imóvel ter ônus
# que sobrevive ao arremate (penhora paralela, indisponibilidade, ação
# de despejo, execução fiscal não declarada).
#
# Conservador por design: classes genéricas (Procedimento Comum, Cautelar
# Sem Mais Detalhe) NÃO entram aqui — usuário tomaria red flag em deals
# saudáveis sempre que o devedor tiver qualquer ação cível pendente.
_CRITICAL_CLASS_CODES: Final[frozenset[int]] = frozenset({
    159,    # Execução Fiscal
    1116,   # Execução de Título Extrajudicial
    156,    # Cumprimento de Sentença
    1733,   # Penhora (medida cautelar)
    62,     # Despejo
    12085,  # Busca e Apreensão (financeira)
})

# Tradução amigável para warnings (pt-BR).
_CRITICAL_CLASS_LABELS: Final[dict[int, str]] = {
    159: "Execução Fiscal",
    1116: "Execução de Título Extrajudicial",
    156: "Cumprimento de Sentença",
    1733: "Penhora",
    62: "Despejo",
    12085: "Busca e Apreensão",
}


# Mapeamento código → categoria legível usada na UI/relatório. Quando o
# código não estiver mapeado, ``categorize_process`` cai em heurística
# textual sobre ``classe_nome`` (anulatórias e embargos costumam aparecer
# com classe "Procedimento Comum" e só dá pra identificar pelo nome).
_CATEGORY_BY_CODE: Final[dict[int, str]] = {
    159: "execucao_fiscal",
    1116: "execucao_titulo",
    156: "cumprimento_sentenca",
    1733: "penhora",
    62: "despejo",
    12085: "busca_apreensao",
}


def categorize_process(
    *,
    classe_codigo: int | None,
    classe_nome: str | None,
    tribunal: str,
) -> tuple[str, bool]:
    """Devolve ``(category, is_critical)`` para um processo do DataJud.

    Prioridades (na ordem):
      1. Heurística textual para anulatórias/embargos — esses raramente
         têm classe própria (vêm como Procedimento Comum, código 39); a
         única pista é a palavra "anulação" ou "embargos" no nome.
         Ambos são SEMPRE críticos (risco direto à arrematação).
      2. TRT — qualquer processo trabalhista é crítico (privilégio do
         crédito) e ganha categoria ``trabalhista``.
      3. Whitelist por código (``_CATEGORY_BY_CODE``) — crítico.
      4. Fallback ``outro`` — não crítico.
    """
    name_l = (classe_nome or "").lower()
    if "anula" in name_l and ("leil" in name_l or "arremat" in name_l):
        return "anulatoria", True
    if "embargo" in name_l and ("arremat" in name_l or "execu" in name_l):
        return "embargos_arrematacao", True

    if tribunal.startswith("trt"):
        return "trabalhista", True

    if classe_codigo is not None and classe_codigo in _CATEGORY_BY_CODE:
        return _CATEGORY_BY_CODE[classe_codigo], True

    return "outro", False


# Mapeamento UF → slug do TJ. DataJud cobre TJs estaduais + tribunais
# federais; defaultamos para o TJ da UF (foro mais provável da execução
# civil que originou o leilão).
_TJ_BY_STATE: Final[dict[str, str]] = {
    "AC": "tjac", "AL": "tjal", "AM": "tjam", "AP": "tjap",
    "BA": "tjba", "CE": "tjce", "DF": "tjdft", "ES": "tjes",
    "GO": "tjgo", "MA": "tjma", "MG": "tjmg", "MS": "tjms",
    "MT": "tjmt", "PA": "tjpa", "PB": "tjpb", "PE": "tjpe",
    "PI": "tjpi", "PR": "tjpr", "RJ": "tjrj", "RN": "tjrn",
    "RO": "tjro", "RR": "tjrr", "RS": "tjrs", "SC": "tjsc",
    "SE": "tjse", "SP": "tjsp", "TO": "tjto",
}

# Mapeamento UF → TRTs com jurisdição. Importante porque crédito
# trabalhista (CLT art. 449) tem privilégio na execução: penhora de
# imóvel do CNPJ executado é cenário frequente. SP é cortado em dois:
# TRT2 (capital + região metropolitana) e TRT15 (interior, sede em
# Campinas). Outras UFs têm apenas um TRT.
_TRT_BY_STATE: Final[dict[str, tuple[str, ...]]] = {
    "AC": ("trt14",),
    "AL": ("trt19",),
    "AM": ("trt11",),
    "AP": ("trt8",),
    "BA": ("trt5",),
    "CE": ("trt7",),
    "DF": ("trt10",),
    "ES": ("trt17",),
    "GO": ("trt18",),
    "MA": ("trt16",),
    "MG": ("trt3",),
    "MS": ("trt24",),
    "MT": ("trt23",),
    "PA": ("trt8",),
    "PB": ("trt13",),
    "PE": ("trt6",),
    "PI": ("trt22",),
    "PR": ("trt9",),
    "RJ": ("trt1",),
    "RN": ("trt21",),
    "RO": ("trt14",),
    "RR": ("trt11",),
    "RS": ("trt4",),
    "SC": ("trt12",),
    "SE": ("trt20",),
    "SP": ("trt2", "trt15"),
    "TO": ("trt10",),
}


@dataclass(frozen=True, slots=True)
class ProcessHit:
    """Um processo retornado pelo DataJud (campos mínimos relevantes)."""

    numero_processo: str
    classe_codigo: int | None
    classe_nome: str | None
    orgao_julgador: str | None
    data_ajuizamento: str | None
    tribunal: str
    is_critical: bool
    category: str = "outro"


@dataclass(frozen=True, slots=True)
class DataJudQueryResult:
    """Resumo do resultado de uma consulta por CPF/CNPJ num tribunal."""

    cpf_cnpj: str
    tribunal: str
    total_hits: int
    critical_hits: int
    processes: list[ProcessHit] = field(default_factory=list)
    critical_labels: list[str] = field(default_factory=list)


class DataJudService:
    """Cliente síncrono para a API Pública do DataJud."""

    def __init__(self, *, api_key: str | None = None, timeout_s: float = 12.0) -> None:
        self._api_key = api_key or os.getenv(
            "CNJ_DATAJUD_API_KEY", _DEFAULT_PUBLIC_KEY
        )
        self._timeout_s = timeout_s
        self._cache: dict[tuple[str, str], tuple[float, DataJudQueryResult]] = {}

    # ------------------------------------------------------------------ #
    def tribunal_for_state(self, state: str | None) -> str | None:
        """Slug do TJ default para uma UF (ou None se desconhecida).

        Mantido por retrocompatibilidade — para consultas multi-tribunais
        (TJ + TRT) use :meth:`tribunals_for_state`.
        """
        if not state:
            return None
        return _TJ_BY_STATE.get(state.strip().upper())

    def tribunals_for_state(self, state: str | None) -> list[str]:
        """Lista de tribunais a consultar para uma UF: TJ-UF + TRT(s).

        Devolve ``[]`` quando a UF é inválida/desconhecida. Para SP devolve
        ``[tjsp, trt2, trt15]`` — interior de SP fica no TRT15 (sede em
        Campinas), capital e região metropolitana no TRT2. Outras UFs têm
        apenas um TRT por jurisdição.
        """
        if not state:
            return []
        uf = state.strip().upper()
        out: list[str] = []
        tj = _TJ_BY_STATE.get(uf)
        if tj:
            out.append(tj)
        out.extend(_TRT_BY_STATE.get(uf, ()))
        return out

    # ------------------------------------------------------------------ #
    def search_by_document(
        self,
        cpf_cnpj: str,
        *,
        tribunal: str,
        size: int = 100,
    ) -> DataJudQueryResult:
        """Busca processos onde a PARTE tem o documento informado.

        Devolve até ``size`` processos, ordenados por data de ajuizamento
        descendente. Levanta :class:`DataJudServiceError` em erro de rede;
        cache hit dentro de 7 dias evita o round-trip.
        """
        digits = "".join(c for c in cpf_cnpj or "" if c.isdigit())
        if len(digits) not in (11, 14):
            raise DataJudServiceError(
                f"CPF/CNPJ inválido (esperado 11 ou 14 dígitos, recebido {len(digits)})"
            )

        cache_key = (digits, tribunal)
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        url = f"{_BASE_URL}/api_publica_{tribunal}/_search"
        headers = {
            "Authorization": f"APIKey {self._api_key}",
            "Content-Type": "application/json",
        }
        # Elasticsearch DSL: match no documento de qualquer parte. O
        # campo padrão é ``partes.documento``.
        body = {
            "size": size,
            "sort": [{"dataAjuizamento": {"order": "desc"}}],
            "query": {"match": {"partes.documento": digits}},
        }

        logger.info("datajud.search.start", tribunal=tribunal, cpf_cnpj_digits=len(digits))
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=self._timeout_s)
            r.raise_for_status()
            payload = r.json()
        except httpx.HTTPError as exc:
            logger.error("datajud.search.http_error", tribunal=tribunal, error=str(exc))
            raise DataJudServiceError(f"DataJud HTTP erro: {exc}") from exc
        except ValueError as exc:
            logger.error("datajud.search.json_error", tribunal=tribunal, error=str(exc))
            raise DataJudServiceError(f"DataJud JSON inválido: {exc}") from exc

        hits_root = (payload.get("hits") or {})
        total = hits_root.get("total")
        # ``total`` pode ser int (legado) ou dict {"value": N} (ES 7+).
        total_hits = total["value"] if isinstance(total, dict) else int(total or 0)
        raw_hits = hits_root.get("hits") or []

        processes: list[ProcessHit] = []
        for h in raw_hits:
            src = h.get("_source") or {}
            classe = src.get("classe") or {}
            classe_codigo = classe.get("codigo") if isinstance(classe, dict) else None
            try:
                classe_codigo_int = int(classe_codigo) if classe_codigo is not None else None
            except (TypeError, ValueError):
                classe_codigo_int = None
            classe_nome = (
                classe.get("nome") if isinstance(classe, dict) else None
            )
            category, is_critical_hit = categorize_process(
                classe_codigo=classe_codigo_int,
                classe_nome=classe_nome,
                tribunal=tribunal,
            )
            processes.append(
                ProcessHit(
                    numero_processo=str(src.get("numeroProcesso") or ""),
                    classe_codigo=classe_codigo_int,
                    classe_nome=classe_nome,
                    orgao_julgador=(
                        (src.get("orgaoJulgador") or {}).get("nome")
                        if isinstance(src.get("orgaoJulgador"), dict)
                        else None
                    ),
                    data_ajuizamento=src.get("dataAjuizamento"),
                    tribunal=tribunal,
                    is_critical=is_critical_hit,
                    category=category,
                )
            )

        critical_hits = sum(1 for p in processes if p.is_critical)
        labels_set: set[str] = set()
        for p in processes:
            if not p.is_critical:
                continue
            if p.category == "anulatoria":
                labels_set.add("Ação anulatória de leilão")
            elif p.category == "embargos_arrematacao":
                labels_set.add("Embargos à arrematação")
            elif p.category == "trabalhista":
                labels_set.add("Processo trabalhista")
            else:
                lbl = _CRITICAL_CLASS_LABELS.get(p.classe_codigo or 0)
                if lbl:
                    labels_set.add(lbl)
        critical_labels = sorted(labels_set)

        result = DataJudQueryResult(
            cpf_cnpj=digits,
            tribunal=tribunal,
            total_hits=total_hits,
            critical_hits=critical_hits,
            processes=processes,
            critical_labels=critical_labels,
        )
        self._cache[cache_key] = (time.time(), result)
        return result


@lru_cache(maxsize=1)
def get_datajud_service() -> DataJudService:
    return DataJudService()


__all__ = [
    "DataJudService",
    "DataJudServiceError",
    "DataJudQueryResult",
    "ProcessHit",
    "get_datajud_service",
]
