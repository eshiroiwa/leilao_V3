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

    # ===== Firecrawl =====
    firecrawl_api_key: SecretStr

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
