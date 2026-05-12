"""Cliente da API Pública do DataJud (CNJ).

Consulta METADADOS de processos judiciais em todos os tribunais do país.
A API é GRATUITA mas exige uma "chave pública" obtida no portal do CNJ
(Portaria CNJ 160/2020). A chave é a MESMA para todos os consumidores —
é só um identificador de uso, não um segredo. Pode vir de env var
``CNJ_DATAJUD_API_KEY`` ou usar o default público abaixo.

Cada tribunal expõe seu próprio endpoint:
    https://api-publica.datajud.cnj.jus.br/api_publica_{TRIBUNAL}/_search

LIMITAÇÃO IMPORTANTE (descoberta em 2026-05-12): a API pública **não
expõe o campo `partes`** no ``_source`` (LGPD). O índice ElasticSearch
público contém apenas: ``numeroProcesso``, ``classe``, ``assuntos``,
``movimentos``, ``orgaoJulgador``, ``sistema``, ``tribunal``, ``grau``,
``nivelSigilo``, ``dataAjuizamento``. **Não há nome nem CPF/CNPJ das
partes** — buscar por ``partes.documento`` ou ``partes.nome`` sempre
retorna 0 hits.

Por isso o agente legal NÃO usa DataJud para descobrir processos a
partir do CPF/nome. DataJud fica reservado para **enriquecer** um
número de processo já conhecido (vindo do edital, por exemplo) ou
classificar processos vindos de outras fontes (Firecrawl).

Cache em memória por (numero_processo, tribunal): TTL 7 dias.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Final, Literal

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Matched-by indica via qual chave (CPF ou nome) o processo foi identificado.
# Útil para a UI sinalizar "match por nome" como suspeito (homônimo possível).
MatchedBy = Literal["cpf", "nome", "both"]


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

# Justiça Federal (TRFs) — a API DataJud expõe 6 regiões. Sem mapeamento por
# UF: na consulta nacional varremos os 6. Cobre execuções fiscais federais
# (União/INSS/Receita Federal) que NÃO aparecem nos TJs estaduais.
_TRFS: Final[tuple[str, ...]] = ("trf1", "trf2", "trf3", "trf4", "trf5", "trf6")

# Tribunais superiores cobertos pela API DataJud.
_SUPERIOR: Final[tuple[str, ...]] = ("stj",)


def all_tribunals() -> list[str]:
    """Lista canônica nacional: 26 TJs + 24 TRTs distintos + 6 TRFs + STJ."""
    tribs: list[str] = list(_TJ_BY_STATE.values())
    seen: set[str] = set(tribs)
    for trts in _TRT_BY_STATE.values():
        for t in trts:
            if t not in seen:
                tribs.append(t)
                seen.add(t)
    for t in _TRFS:
        if t not in seen:
            tribs.append(t)
            seen.add(t)
    for t in _SUPERIOR:
        if t not in seen:
            tribs.append(t)
            seen.add(t)
    return tribs


# Códigos do segmento J (Justiça) + TR (tribunal) embutidos no número CNJ
# unificado (Resolução CNJ 65/2008). Formato:
#   NNNNNNN-DD.AAAA.J.TR.OOOO
# J = 1 STF · 2 CNJ · 3 STJ · 4 Federal · 5 Trabalho · 8 Estadual · …
# Para J=8 (Estadual), TR é o código do TJ (1=AC, 2=AL, …, 26=SP, 27=TO).
# Para J=5 (Trabalho), TR é o número do TRT (1=TRT1 …).
# Para J=4 (Federal), TR é a região do TRF (1=TRF1 … 6=TRF6).
# Para J=3 (STJ) ou J=1 (STF), TR é fixo "00".
_TJ_BY_CNJ_CODE: Final[dict[int, str]] = {
    1: "tjac", 2: "tjal", 3: "tjam", 4: "tjap", 5: "tjba", 6: "tjce",
    7: "tjdft", 8: "tjes", 9: "tjgo", 10: "tjma", 11: "tjms", 12: "tjmt",
    13: "tjmg", 14: "tjpa", 15: "tjpb", 16: "tjpe", 17: "tjpi", 18: "tjpr",
    19: "tjrj", 20: "tjrn", 21: "tjro", 22: "tjrr", 23: "tjrs", 24: "tjsc",
    25: "tjse", 26: "tjsp", 27: "tjto",
}


def tribunal_from_cnj_number(numero: str) -> str | None:
    """Decodifica o slug do tribunal embutido em um número CNJ unificado.

    Aceita formato com ou sem pontuação. Retorna ``None`` quando o número
    não bate o padrão ou o segmento (J, TR) não é coberto pela API DataJud.

    Ex.: ``"0012345-67.2024.8.26.0001"`` → ``"tjsp"``.
    """
    digits = "".join(c for c in (numero or "") if c.isdigit())
    if len(digits) != 20:
        return None
    j = int(digits[13])
    tr = int(digits[14:16])
    if j == 8:  # Estadual
        return _TJ_BY_CNJ_CODE.get(tr)
    if j == 5:  # Trabalho (TRTs 1-24)
        return f"trt{tr}" if 1 <= tr <= 24 else None
    if j == 4:  # Federal (TRFs 1-6)
        slug = f"trf{tr}"
        return slug if slug in _TRFS else None
    if j == 3:  # STJ
        return "stj"
    return None


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
    matched_by: MatchedBy = "cpf"


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
        # Cache key: (numero_processo, "", tribunal). O segundo slot é
        # reservado (uso futuro caso a busca evolua além de número).
        # TTL: 7 dias.
        self._cache: dict[tuple[str, str, str], tuple[float, DataJudQueryResult]] = {}
        self._cache_lock = threading.Lock()

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
        ``[tjsp, trt2, trt15]``.
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

    def all_tribunals(self) -> list[str]:
        """Atalho de instância para :func:`all_tribunals`."""
        return all_tribunals()

    # ------------------------------------------------------------------ #
    def search_by_number(
        self,
        numero_processo: str,
        *,
        tribunal: str,
        force_refresh: bool = False,
    ) -> ProcessHit | None:
        """Busca um processo específico pelo seu número CNJ.

        Este é o único caso de uso útil da API DataJud pública hoje
        (o índice não expõe partes — ver docstring do módulo). Use quando
        o número do processo for conhecido (vindo do edital, decisão ou
        descoberta por outra fonte).

        Retorna ``ProcessHit`` ou ``None`` se não encontrado.
        Levanta :class:`DataJudServiceError` em erro de rede/JSON.
        """
        numero = "".join(c for c in (numero_processo or "") if c.isdigit())
        if not numero:
            raise DataJudServiceError("número de processo vazio")

        cache_key = (numero, "", tribunal)
        if not force_refresh:
            with self._cache_lock:
                cached = self._cache.get(cache_key)
            if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
                procs = cached[1].processes
                return procs[0] if procs else None

        body = {
            "size": 1,
            "query": {"match": {"numeroProcesso": numero}},
        }
        payload = self._http_search(tribunal=tribunal, body=body)
        hits = (payload.get("hits") or {}).get("hits") or []
        hit: ProcessHit | None = None
        if hits:
            src = hits[0].get("_source") or {}
            hit = self._parse_hit(src=src, tribunal=tribunal)

        result = DataJudQueryResult(
            cpf_cnpj="",
            tribunal=tribunal,
            total_hits=1 if hit else 0,
            critical_hits=1 if hit and hit.is_critical else 0,
            processes=[hit] if hit else [],
            critical_labels=[],
        )
        with self._cache_lock:
            self._cache[cache_key] = (time.time(), result)
        return hit

    # ------------------------------------------------------------------ #
    # Internos
    # ------------------------------------------------------------------ #
    def _http_search(self, *, tribunal: str, body: dict) -> dict:
        """POST contra o endpoint de um tribunal com 1 retry em 429/503."""
        url = f"{_BASE_URL}/api_publica_{tribunal}/_search"
        headers = {
            "Authorization": f"APIKey {self._api_key}",
            "Content-Type": "application/json",
        }
        logger.info(
            "datajud.search.start",
            tribunal=tribunal,
            size=body.get("size"),
            from_offset=body.get("from", 0),
        )
        attempt = 0
        while True:
            try:
                r = httpx.post(url, headers=headers, json=body, timeout=self._timeout_s)
                if r.status_code in (429, 503) and attempt == 0:
                    attempt += 1
                    time.sleep(1.0)
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as exc:
                logger.warning(
                    "datajud.search.http_error",
                    tribunal=tribunal,
                    error=str(exc),
                    attempt=attempt,
                )
                raise DataJudServiceError(f"DataJud HTTP erro: {exc}") from exc
            except ValueError as exc:
                logger.warning(
                    "datajud.search.json_error", tribunal=tribunal, error=str(exc)
                )
                raise DataJudServiceError(f"DataJud JSON inválido: {exc}") from exc

    def _parse_hit(self, *, src: dict, tribunal: str) -> ProcessHit | None:
        classe = src.get("classe") or {}
        classe_codigo = classe.get("codigo") if isinstance(classe, dict) else None
        try:
            classe_codigo_int = int(classe_codigo) if classe_codigo is not None else None
        except (TypeError, ValueError):
            classe_codigo_int = None
        classe_nome = classe.get("nome") if isinstance(classe, dict) else None
        category, is_critical_hit = categorize_process(
            classe_codigo=classe_codigo_int,
            classe_nome=classe_nome,
            tribunal=tribunal,
        )
        return ProcessHit(
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


@lru_cache(maxsize=1)
def get_datajud_service() -> DataJudService:
    return DataJudService()


__all__ = [
    "DataJudService",
    "DataJudServiceError",
    "DataJudQueryResult",
    "MatchedBy",
    "ProcessHit",
    "all_tribunals",
    "get_datajud_service",
    "tribunal_from_cnj_number",
]
