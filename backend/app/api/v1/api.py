"""API v1 master router aggregating all sub-routers."""

from fastapi import APIRouter
from backend.app.api.v1.inventory import router as inventory_router
from backend.app.api.v1.categories import router as categories_router

api_router = APIRouter()
api_router.include_router(inventory_router)
api_router.include_router(categories_router)
