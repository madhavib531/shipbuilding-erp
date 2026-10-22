"""AI assistant (Claude with read-only tools). Available only when ANTHROPIC_API_KEY is configured."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.common import SuccessResponse
from app.services import assistant_service as service

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(max_length=8000)]


class Question(BaseModel):
    question: Text
    history: list[Turn] = Field(default_factory=list, max_length=20)


@router.get("/status", response_model=SuccessResponse)
def assistant_status():
    return SuccessResponse(message="Assistant status", data={
        "enabled": service.enabled(), "model": settings.assistant_model if service.enabled() else None,
        "tools": sorted(service.TOOLS)})


@router.post("/ask", response_model=SuccessResponse)
def ask(data: Question, db: Session = Depends(get_db)):
    if not service.enabled():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="The AI assistant is not configured: add ANTHROPIC_API_KEY to backend/.env")
    try:
        result = service.ask(db, data.question, [t.model_dump() for t in data.history])
    except Exception as exc:  # noqa: BLE001 - the AI service failed; report its kind, not internals
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"The AI service could not answer ({type(exc).__name__}). Try again.")
    return SuccessResponse(message="Answered", data=result)
