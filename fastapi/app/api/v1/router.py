from fastapi import APIRouter

from app.api.v1.endpoints import analytics, links

api_router = APIRouter()
api_router.include_router(links.router)
api_router.include_router(analytics.router)
