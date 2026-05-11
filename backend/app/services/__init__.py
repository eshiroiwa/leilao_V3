"""Wrappers de integrações externas (Firecrawl, OpenAI, Supabase, Google Maps, BACEN)."""

from app.services.bacen_service import BacenService, get_bacen_service
from app.services.brasilapi_service import BrasilApiService, get_brasilapi_service
from app.services.cnj_datajud_service import DataJudService, get_datajud_service
from app.services.fipezap_service import FipeZapService, get_fipezap_service
from app.services.firecrawl_service import FirecrawlService, get_firecrawl_service
from app.services.google_maps_service import GoogleMapsService, get_google_maps_service
from app.services.supabase_service import SupabaseService, get_supabase_service
from app.services.vision_service import VisionService, get_vision_service

__all__ = [
    "BacenService",
    "BrasilApiService",
    "DataJudService",
    "FipeZapService",
    "FirecrawlService",
    "GoogleMapsService",
    "SupabaseService",
    "VisionService",
    "get_bacen_service",
    "get_brasilapi_service",
    "get_datajud_service",
    "get_fipezap_service",
    "get_firecrawl_service",
    "get_google_maps_service",
    "get_supabase_service",
    "get_vision_service",
]
