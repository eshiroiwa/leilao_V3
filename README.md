# Leilão IA v3 — Sistema Multi-Agente para Precificação de Imóveis de Leilão

Plataforma multi-agente que coleta, normaliza e enriquece dados de imóveis publicados
em sites de leilão judiciais e extrajudiciais brasileiros (ex.: **Zuk**, **Mega Leilões**),
para alimentar um pipeline de **precificação automatizada**.

---

## Visão geral da arquitetura

```
┌───────────────────────┐         ┌──────────────────────────────┐
│  Next.js 16 (App      │  HTTP   │  FastAPI                     │
│  Router, TS, Tailwind │ ──────► │  + LangGraph (orquestração)  │
│  shadcn/ui)           │         │                              │
└───────────────────────┘         │   ┌──── Agente 1 ────┐       │
                                  │   │ Scraper + Geo    │       │
                                  │   └──────────────────┘       │
                                  │   ┌──── Agente 2 ────┐       │
                                  │   │ (futuro)         │       │
                                  │   └──────────────────┘       │
                                  └────────────┬─────────────────┘
                                               │
                ┌──────────────┬───────────────┼─────────────────┐
                ▼              ▼               ▼                 ▼
          Firecrawl       OpenAI         Google Maps        Supabase
         (scraping →     (extração       (Address Val.    (Postgres +
          Markdown)       LLM)            + Geocoding)    PostGIS + JSONB)
```

### Stack

| Camada       | Tecnologia                                                    |
|--------------|---------------------------------------------------------------|
| Frontend     | Next.js 16 (App Router), TypeScript, Tailwind CSS, shadcn/ui  |
| Backend      | Python 3.12+, FastAPI, LangGraph, Pydantic v2                 |
| LLM          | OpenAI (via `langchain-openai`)                               |
| Scraping     | Firecrawl (`firecrawl-py`)                                    |
| Geolocaliz.  | Google Maps Platform — Address Validation + Geocoding         |
| Banco        | Supabase (PostgreSQL 15 + PostGIS + JSONB)                    |

---

## Estrutura de pastas

```
leilao_ia_v3/
├── backend/                  # API FastAPI + agentes LangGraph
│   ├── app/
│   │   ├── agents/
│   │   │   └── scraper/      # AGENTE 1
│   │   ├── api/              # rotas REST
│   │   ├── services/         # integrações externas
│   │   ├── db/               # schema SQL + migrations
│   │   ├── core/             # settings, logging
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── requirements.txt
│
├── frontend/                 # Next.js 16 (colocation pattern)
│   ├── app/
│   │   ├── (dashboard)/
│   │   │   ├── scrape/
│   │   │   │   ├── _components/
│   │   │   │   └── page.tsx
│   │   │   └── properties/
│   │   │       ├── _components/
│   │   │       └── page.tsx
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/ui/        # shadcn/ui primitives
│   ├── lib/
│   ├── package.json
│   └── tsconfig.json
│
├── .env.example
├── .gitignore
└── README.md
```

> **Padrão de colocation** no frontend: cada rota possui uma pasta `_components/`
> (prefixo `_` faz o Next.js ignorar como rota) com os componentes que pertencem
> exclusivamente àquela tela. Componentes verdadeiramente compartilhados ficam
> em `components/`.

---

## Setup rápido

### 1. Variáveis de ambiente

```bash
cp .env.example .env
# preencha as chaves: OPENAI_API_KEY, FIRECRAWL_API_KEY, SUPABASE_*, GOOGLE_MAPS_API_KEY
```

### 2. Banco (Supabase)

No SQL Editor do Supabase, execute o conteúdo de
[`backend/app/db/schema.sql`](backend/app/db/schema.sql). Ele habilita PostGIS e cria
todas as tabelas, índices e triggers.

### 3. Instalação (uma vez só)

```bash
# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..

# Frontend
cd frontend && npm install && cd ..
```

### 4. Subir o sistema (dia a dia)

A partir da raiz do projeto, basta um comando — sobe **backend + frontend** juntos
e, ao pressionar `Ctrl+C`, **derruba os dois**:

```bash
./dev.sh
```

- Backend: <http://localhost:8000/docs>
- Frontend: <http://localhost:3000>

> O `dev.sh` cuida de matar processos antigos na porta 8000, esperar o backend
> ficar pronto, prefixar logs com `[BACKEND]`/`[FRONTEND]` e garantir que o trap
> de saída encerre os dois processos juntos (incluindo qualquer filho do uvicorn
> com `--reload`).

Se preferir rodar manualmente em terminais separados, os comandos clássicos
continuam funcionando:

```bash
# Terminal 1
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

---

## AGENTE 1 — Scraper e Normalizador Geográfico

**Responsabilidade:** dado o link de um lote em um leiloeiro brasileiro, produzir
um registro estruturado em `properties` com endereço validado e coordenadas
geográficas confiáveis.

Fluxo (LangGraph):

```
START
  │
  ▼
scrape_url        ── Firecrawl converte HTML → Markdown limpo
  │
  ▼
extract_data      ── OpenAI (function calling) → JSON estruturado
  │
  ▼
validate_address  ── Google Address Validation API
  │
  ▼
geocode           ── Google Geocoding API (lat/lng + place_id)
  │
  ▼
persist           ── Upsert em Supabase (PostGIS POINT)
  │
  ▼
END
```

Cada nó é idempotente e registra erros/avisos em `state.errors`, permitindo
retentativas finas e auditoria por lote.

Endpoint:

```http
POST /api/v1/agents/scraper/run
Content-Type: application/json

{ "url": "https://www.zuk.com.br/leiloes/imoveis/123-apartamento-..." }
```

---

## Roadmap de agentes

- [x] **Agente 1** — Scraper + Normalizador Geográfico
- [ ] **Agente 2** — Pesquisa de mercado (comparáveis)
- [ ] **Agente 3** — Análise jurídica do edital
- [ ] **Agente 4** — Modelo de precificação (ML + regras)
- [ ] **Agente 5** — Score de oportunidade e relatório final
