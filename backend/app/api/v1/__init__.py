"""API v1 Router aggregation."""

from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.organizations import router as orgs_router
from app.api.v1.economics import router as economics_router
from app.api.v1.audit import router as audit_router

from app.api.v1.orders import router as orders_router
from app.api.v1.csv_import import router as csv_import_router
from app.api.v1.delivery import router as delivery_router
from app.api.v1.demo import router as demo_router
from app.api.v1.monitoring import router as monitoring_router
from app.api.v1.integrations import router as integrations_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(orgs_router)
api_v1_router.include_router(economics_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(orders_router)
api_v1_router.include_router(csv_import_router)
api_v1_router.include_router(delivery_router)
api_v1_router.include_router(demo_router)
api_v1_router.include_router(monitoring_router)
api_v1_router.include_router(integrations_router)

