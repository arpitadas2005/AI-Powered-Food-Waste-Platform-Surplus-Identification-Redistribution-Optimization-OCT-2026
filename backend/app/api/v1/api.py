"""API v1 master router aggregating all sub-routers."""

from fastapi import APIRouter
from backend.app.api.v1.inventory import router as inventory_router
from backend.app.api.v1.categories import router as categories_router
from backend.app.api.v1.import_export import router as import_export_router
from backend.app.api.v1.alerts import router as alerts_router

api_router = APIRouter()
# Register alerts_router before inventory_router so static paths (/inventory/expiring)
# are matched before parameterized routes (/inventory/{id})
api_router.include_router(alerts_router)
api_router.include_router(inventory_router)
api_router.include_router(categories_router)
api_router.include_router(import_export_router)
