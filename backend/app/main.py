"""FastAPI application factory."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import health
from app.api.v1 import analytics, assistant, audit, auth, exchange_rates, dashboard, inspections, materials, notifications, purchase_orders, reference, suppliers, transfers
from app.auth import current_user

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Driven Material Management System for Shipbuilding",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS configuration for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health and sign-in are public; everything else needs a signed-in user (writes also check the role).
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(auth.users_router)
_signed_in = [Depends(current_user)]
for module in (materials, reference, transfers, suppliers, purchase_orders, inspections, dashboard, audit, analytics, notifications, assistant, exchange_rates):
    app.include_router(module.router, dependencies=_signed_in)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/api/docs",
    }
