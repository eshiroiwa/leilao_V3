"""Settings carregadas de variáveis de ambiente / .env via Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env fica na raiz do monorepo (um nível acima de /backend).
ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Configuração centralizada da aplicação."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== App =====
    app_name: str = "Leilão IA — Backend"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8000)
    backend_cors_origins: str = Field(default="http://localhost:3000")

    # ===== OpenAI =====
    openai_api_key: SecretStr
    openai_model: str = Field(default="gpt-4o")
    # Modelo barato usado pelo AGENTE 2 para extrair listings (tarefa simples,
    # não precisa de Opus/4o). Configurável via OPENAI_EXTRACTION_MODEL.
    openai_extraction_model: str = Field(default="gpt-5-mini")

    # ===== Firecrawl =====
    firecrawl_api_key: SecretStr

    # ===== AGENTE 2 (Comparáveis / CMA) =====
    # Limites duros de orçamento por avaliação.
    # OBS: cada scrape de página de RESULTADOS DE BUSCA do VivaReal/ZAP
    # devolve ~8-20 listings num único batch LLM. Logo 3-4 scrapes já
    # geram mais de 25 candidatos.
    cma_max_firecrawl_searches: int = Field(default=2)
    cma_max_firecrawl_scrapes: int = Field(default=4)
    # 1 LLM por scrape (batch). Manter alinhado com scrapes.
    cma_max_llm_calls: int = Field(default=4)
    # Wall-clock total (segundos) para o batch de scrapes do
    # ``node_fetch_candidates``. Acima disso, scrapes pendentes são
    # abandonados e o pipeline avança com o que conseguiu. Sem esse cap,
    # UM scrape lento (ImovelWeb costuma demorar 1-2 min) trava todo o
    # request mesmo com paralelismo de 8.
    cma_fetch_batch_timeout_s: int = Field(default=60)
    # Cache.
    cma_listing_cache_days: int = Field(default=30)
    cma_neighborhood_ppm2_cache_days: int = Field(default=7)
    # Pipeline.
    cma_min_comparables_acceptable: int = Field(default=3)   # < isso => INSUFFICIENT
    cma_min_comparables_confident: int = Field(default=5)    # >= isso => MEDIUM/HIGH
    cma_max_comparables_kept: int = Field(default=15)        # trim se passar
    # Custo unitário aproximado em BRL (auditoria — ajuste conforme contrato).
    cma_brl_per_firecrawl_call: float = Field(default=0.025)
    cma_brl_per_llm_call: float = Field(default=0.020)

    # ===== Supabase =====
    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr

    # ===== Google Maps =====
    google_maps_api_key: SecretStr

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton de Settings (cacheado)."""
    return Settings()  # type: ignore[call-arg]
