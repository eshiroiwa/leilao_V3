"""Wrappers de integrações externas (Firecrawl, OpenAI, Supabase, Google Maps, BACEN)."""

from app.services.bacen_service import BacenService, get_bacen_service
from app.services.firecrawl_service import FirecrawlService, get_firecrawl_service
from app.services.google_maps_service import GoogleMapsService, get_google_maps_service
from app.services.supabase_service import SupabaseService, get_supabase_service

__all__ = [
    "BacenService",
    "FirecrawlService",
    "GoogleMapsService",
    "SupabaseService",
    "get_bacen_service",
    "get_firecrawl_service",
    "get_google_maps_service",
    "get_supabase_service",
]
