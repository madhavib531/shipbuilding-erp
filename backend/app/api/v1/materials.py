"""Materials CRUD endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session, undefer
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.material import Material, MaterialCategory, MaterialStatusEnum
from app.models.facility import Yard, StorageLocation
from app.models.program import Ship
from app.models.transaction import MaterialTransaction
from app.models.transfer import MaterialTransfer
from app.schemas.common import SuccessResponse
from app.schemas.material import MaterialCreate, MaterialUpdate, MaterialRead, MaterialTransactionRead
from app.services import inspection_service, material_service

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


# Registered before "/{material_id}" so "summary" is not treated as a material ID.
@router.get("/summary", response_model=SuccessResponse)
def material_summary(db: Session = Depends(get_db)):
    """Batch counts for the dashboard: available, reserved, Low stock (manual status) and active yards."""
    return SuccessResponse(message="Material summary retrieved successfully", data=material_service.summary(db))


@router.get("", response_model=SuccessResponse)
def list_materials(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    search: str = Query("", description="Search by ID, name, or batch"),
    category: str = Query("", description="Filter by category ID"),
    yard: str = Query("", description="Filter by yard ID"),
    ship: str = Query("", description="Filter by allocated ship ID"),
    status_filter: MaterialStatusEnum = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """
    List materials with pagination, search, and filtering.

    Query parameters:
    - search: Search materials by ID, name, or batch
    - category: Filter by category ID
    - yard: Filter by yard ID
    - ship: Filter by allocated ship ID
    - status_filter: Filter by material status
    """
    query = db.query(Material)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Material.id.ilike(search_term))
            | (Material.name.ilike(search_term))
            | (Material.batch.ilike(search_term))
        )

    if category:
        query = query.filter(Material.category_id == category)

    if yard:
        query = query.filter(Material.yard_id == yard)

    if ship:
        query = query.filter(Material.ship_id == ship)

    if status_filter:
        query = query.filter(Material.status == status_filter)

    total = query.count()
    materials = (
        query.options(undefer(Material.held_quantity))
        .order_by(Material.created_at.desc(), Material.id)
        .offset(skip).limit(limit).all()
    )

    materials_data = [MaterialRead.model_validate(m) for m in materials]

    return SuccessResponse(
        message="Materials retrieved successfully",
        data={
            "materials": [m.model_dump() for m in materials_data],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    )


@router.get("/{material_id}", response_model=SuccessResponse)
def get_material(
    material_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific material by ID."""
    material = db.query(Material).filter(Material.id == material_id).first()

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material with ID '{material_id}' not found"
        )

    material_data = MaterialRead.model_validate(material)

    return SuccessResponse(
        message="Material retrieved successfully",
        data=material_data.model_dump()
    )


@router.get("/{material_id}/transactions", response_model=SuccessResponse)
def list_material_transactions(
    material_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Ledger rows for one batch, newest first: its custody and movement history."""
    if db.get(Material, material_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Material with ID '{material_id}' not found")
    query = db.query(MaterialTransaction).filter(MaterialTransaction.material_id == material_id)
    total = query.count()
    rows = (
        query.order_by(MaterialTransaction.created_at.desc(), MaterialTransaction.id.desc())
        .offset(skip).limit(limit).all()
    )
    return SuccessResponse(
        message="Material transactions retrieved successfully",
        data={
            "transactions": [MaterialTransactionRead.model_validate(t).model_dump(mode="json") for t in rows],
            "total": total, "skip": skip, "limit": limit,
        },
    )


@router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def create_material(
    material_data: MaterialCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new material.

    Validates:
    - Material ID is unique
    - Category exists
    - Yard exists
    - Storage location (if provided) belongs to the specified yard
    - Ship (if provided) belongs to the specified yard
    - Quantities are consistent
    """
    # Check if material already exists
    existing = db.query(Material).filter(Material.id == material_data.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Material with ID '{material_data.id}' already exists"
        )

    # Verify category exists
    category = db.query(MaterialCategory).filter(
        MaterialCategory.id == material_data.category_id
    ).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Category '{material_data.category_id}' does not exist"
        )

    # Verify yard exists
    yard = db.query(Yard).filter(Yard.id == material_data.yard_id).first()
    if not yard:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Yard '{material_data.yard_id}' does not exist"
        )

    # Verify storage location if provided
    if material_data.location_id:
        location = db.query(StorageLocation).filter(
            StorageLocation.id == material_data.location_id
        ).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Storage location '{material_data.location_id}' does not exist"
            )
        if str(location.yard_id) != material_data.yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Storage location '{material_data.location_id}' does not belong to yard '{material_data.yard_id}'"
            )

    # Verify ship if provided
    if material_data.ship_id:
        ship = db.query(Ship).filter(Ship.id == material_data.ship_id).first()
        if not ship:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Ship '{material_data.ship_id}' does not exist"
            )
        if str(ship.yard_id) != material_data.yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Ship '{material_data.ship_id}' does not belong to yard '{material_data.yard_id}'"
            )

    if material_data.quantity > 0 and not material_data.actor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="actor is required to create a batch with stock: its opening balance is recorded in the stock ledger"
        )

    material = Material(**material_data.model_dump(exclude={"actor", "stock_reason"}))

    # The batch and its opening-balance ledger entry are committed together or not at all.
    try:
        db.add(material)
        if material.quantity > 0:
            db.flush()
            db.add(material_service.opening_balance(material, material_data.actor, material_data.stock_reason))
        db.commit()
        db.refresh(material)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database integrity error while creating material"
        )

    created = MaterialRead.model_validate(material)

    return SuccessResponse(
        message="Material created successfully",
        data=created.model_dump()
    )


@router.patch("/{material_id}", response_model=SuccessResponse)
def update_material(
    material_id: str,
    material_update: MaterialUpdate,
    db: Session = Depends(get_db),
):
    """
    Update a material (partial update supported).

    Only provided fields are updated. Validates:
    - Material exists
    - Category exists (if updating)
    - Yard exists (if updating)
    - Storage location constraints (if updating)
    - Ship constraints (if updating)
    - Quantity consistency
    - expected_version, if sent, still matches (stale-edit protection)
    """
    # Lock the row so the checks below and the write cannot interleave with a transfer dispatch or receipt.
    material = (
        db.query(Material).filter(Material.id == material_id)
        .with_for_update().populate_existing().first()
    )

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material with ID '{material_id}' not found"
        )

    update_data = material_update.model_dump(exclude_unset=True)
    expected_version = update_data.pop("expected_version", None)
    actor = update_data.pop("actor", None)
    stock_reason = update_data.pop("stock_reason", None)
    if expected_version is not None and expected_version != material.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Material '{material_id}' was changed by another update (now version "
                   f"{material.version}, you edited version {expected_version}). Reload and try again."
        )

    # Verify category if updating
    if "category_id" in update_data:
        category = db.query(MaterialCategory).filter(
            MaterialCategory.id == update_data["category_id"]
        ).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Category '{update_data['category_id']}' does not exist"
            )

    yard_id = update_data.get("yard_id", material.yard_id)
    location_id = update_data.get("location_id", material.location_id)
    ship_id = update_data.get("ship_id", material.ship_id)
    placement_changed = bool({"yard_id", "location_id", "ship_id"} & update_data.keys())

    if "yard_id" in update_data:
        yard = db.query(Yard).filter(Yard.id == yard_id).first()
        if not yard:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Yard '{yard_id}' does not exist"
            )

    # Re-check stored location/ship too, so a yard-only change cannot orphan them in the old yard.
    if placement_changed and location_id:
        location = db.query(StorageLocation).filter(StorageLocation.id == location_id).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Storage location '{location_id}' does not exist"
            )
        if str(location.yard_id) != yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Storage location '{location_id}' does not belong to yard '{yard_id}'"
            )

    if placement_changed and ship_id:
        ship = db.query(Ship).filter(Ship.id == ship_id).first()
        if not ship:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Ship '{ship_id}' does not exist"
            )
        if str(ship.yard_id) != yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Ship '{ship_id}' does not belong to yard '{yard_id}'"
            )

    # Validate quantity consistency
    quantity = update_data.get("quantity", material.quantity)
    available = update_data.get("available", material.available)
    reserved = update_data.get("reserved", material.reserved)

    if available + reserved > quantity:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"available ({available}) + reserved ({reserved}) "
                   f"cannot exceed quantity ({quantity})"
        )

    # Stock on inspection hold changes only through release or rejection; the row lock above keeps it stable.
    held = inspection_service.held_quantity(db, material_id)
    if held:
        if update_data.get("status", MaterialStatusEnum.INSPECTION) != MaterialStatusEnum.INSPECTION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Material '{material_id}' has {held} {material.unit} on inspection hold; release or "
                       f"reject it on the Quality page before changing its status"
            )
        if available + reserved > quantity - held:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"available ({available}) + reserved ({reserved}) cannot exceed the {quantity - held} "
                       f"{material.unit} not on inspection hold (quantity {quantity}, {held} held)"
            )

    # Every change to a stock figure is recorded in the ledger, so it needs an actor and a reason.
    before = material_service.stock_figures(material)
    stock_changed = any(update_data.get(f, before[f]) != before[f] for f in material_service.STOCK_FIELDS)
    if stock_changed and not actor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="actor is required when on-hand, available or reserved quantities change"
        )
    if stock_changed and not stock_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A reason is required when on-hand, available or reserved quantities change; "
                   "it is recorded in the stock ledger"
        )

    # The material change and its ADJUSTMENT ledger entry are committed together or not at all.
    try:
        for field, value in update_data.items():
            setattr(material, field, value)
        if update_data:
            material.version += 1
        if stock_changed:
            db.add(material_service.stock_adjustment(material, before, actor, stock_reason))
        db.commit()
        db.refresh(material)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database integrity error while updating material"
        )

    material_data = MaterialRead.model_validate(material)

    return SuccessResponse(
        message="Material updated successfully",
        data=material_data.model_dump()
    )


@router.delete("/{material_id}", response_model=SuccessResponse)
def delete_material(
    material_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete a material.

    Note: Will fail if material has associated transactions.
    This is by design to protect referential integrity.
    """
    material = (
        db.query(Material).filter(Material.id == material_id)
        .with_for_update().populate_existing().first()
    )

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material with ID '{material_id}' not found"
        )

    transfer_count = db.query(MaterialTransfer).filter(
        (MaterialTransfer.material_id == material_id)
        | (MaterialTransfer.destination_material_id == material_id)
    ).count()
    if transfer_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete material with {transfer_count} transfer(s) referencing it."
        )

    # Check for associated transactions
    transaction_count = db.query(MaterialTransaction).filter(
        MaterialTransaction.material_id == material_id
    ).count()

    if transaction_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete material with {transaction_count} associated transaction(s). "
                   f"Delete transactions first or set material status to archived."
        )

    try:
        db.delete(material)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database integrity error while deleting material"
        )

    return SuccessResponse(
        message=f"Material '{material_id}' deleted successfully",
        data={"id": material_id}
    )
