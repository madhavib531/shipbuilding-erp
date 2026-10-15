"""Supplier directory endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.supplier import SupplierStatusEnum
from app.schemas.common import SuccessResponse
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services import supplier_service as service

router = APIRouter(prefix="/api/v1/suppliers", tags=["suppliers"])


def _read(supplier) -> dict:
    return SupplierRead.model_validate(supplier).model_dump(mode="json")


def _write(db: Session, action):
    try:
        return action()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The supplier ID or name conflicts with a concurrent change. Reload and try again.",
        )
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=SuccessResponse)
def list_suppliers(
    search: str = Query("", description="Matches ID, name, contact person or country"),
    statuses: list[SupplierStatusEnum] = Query(default=[], alias="status", description="Repeat to match several"),
    country: str = Query("", description="Exact country, case-insensitive"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total, items = service.list_suppliers(db, search, statuses, country, skip, limit)
    return SuccessResponse(
        message="Suppliers retrieved successfully",
        data={"suppliers": [_read(s) for s in items], "total": total, "skip": skip, "limit": limit},
    )


@router.get("/{supplier_id}", response_model=SuccessResponse)
def get_supplier(supplier_id: str, db: Session = Depends(get_db)):
    return SuccessResponse(message="Supplier retrieved successfully", data=_read(service.get_supplier(db, supplier_id)))


@router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(data: SupplierCreate, db: Session = Depends(get_db)):
    supplier = _write(db, lambda: service.create_supplier(db, data))
    return SuccessResponse(message="Supplier created successfully", data=_read(supplier))


@router.patch("/{supplier_id}", response_model=SuccessResponse)
def update_supplier(supplier_id: str, data: SupplierUpdate, db: Session = Depends(get_db)):
    supplier = _write(db, lambda: service.update_supplier(db, supplier_id, data))
    return SuccessResponse(message="Supplier updated successfully", data=_read(supplier))
