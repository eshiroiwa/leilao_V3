"""Routers FastAPI."""

from fastapi import APIRouter

from app.api.routes import agents, opportunity, properties, valuations

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(agents.router)
api_router.include_router(properties.router)
api_router.include_router(valuations.router)
api_router.include_router(opportunity.router)

__all__ = ["api_router"]
