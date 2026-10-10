"""Common Pydantic schemas."""

from pydantic import BaseModel
from typing import Any, Dict


class HealthCheckResponse(BaseModel):
    """Health check endpoint response."""
    status: str
    message: str
    version: str
    database: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    status: str = "error"
    message: str
    detail: Any = None


class SuccessResponse(BaseModel):
    """Standard success response."""
    status: str = "success"
    message: str
    data: Any = None
