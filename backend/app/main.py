"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import health
from app.api.v1 import materials, reference, suppliers, transfers

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

# Include routers
app.include_router(health.router)
app.include_router(materials.router)
app.include_router(reference.router)
app.include_router(transfers.router)
app.include_router(suppliers.router)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/api/docs",
    }
