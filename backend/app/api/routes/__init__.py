"""Routers FastAPI."""

from fastapi import APIRouter

from app.api.routes import agents, deep, opportunity, properties, valuations

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(agents.router)
api_router.include_router(properties.router)
api_router.include_router(valuations.router)
api_router.include_router(opportunity.router)
api_router.include_router(deep.router_property)
api_router.include_router(deep.router_global)

__all__ = ["api_router"]
