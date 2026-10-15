"""Supplier directory: list, read, create and update. Suppliers are never hard-deleted;
set the status to Inactive or Blocked instead so purchase-order history stays intact."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ConflictError, ItemNotFoundError
from app.models.supplier import Supplier, SupplierStatusEnum
from app.schemas.supplier import SupplierCreate, SupplierUpdate


def list_suppliers(db: Session, search: str, statuses: list[SupplierStatusEnum], country: str,
                   skip: int, limit: int) -> tuple[int, list[Supplier]]:
    query = select(Supplier)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            Supplier.id.ilike(term) | Supplier.name.ilike(term)
            | Supplier.contact_person.ilike(term) | Supplier.country.ilike(term)
        )
    if statuses:
        query = query.where(Supplier.status.in_(statuses))
    if country:
        query = query.where(func.lower(Supplier.country) == country.strip().lower())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Supplier.name, Supplier.id).offset(skip).limit(limit)).all()
    return total, items


def get_supplier(db: Session, supplier_id: str) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ItemNotFoundError("Supplier", supplier_id)
    return supplier


def _ensure_name_free(db: Session, name: str, except_id: str | None = None) -> None:
    query = select(Supplier.id).where(func.lower(Supplier.name) == name.lower())
    if except_id is not None:
        query = query.where(Supplier.id != except_id)
    clash = db.scalar(query)
    if clash is not None:
        raise ConflictError(f"Supplier name '{name}' is already used by supplier '{clash}'")


def create_supplier(db: Session, data: SupplierCreate) -> Supplier:
    if db.get(Supplier, data.id) is not None:
        raise ConflictError(f"Supplier with ID '{data.id}' already exists")
    _ensure_name_free(db, data.name)
    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(db: Session, supplier_id: str, data: SupplierUpdate) -> Supplier:
    supplier = db.scalar(
        select(Supplier).where(Supplier.id == supplier_id).with_for_update().execution_options(populate_existing=True)
    )
    if supplier is None:
        raise ItemNotFoundError("Supplier", supplier_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _ensure_name_free(db, changes["name"], except_id=supplier_id)
    for field, value in changes.items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier
