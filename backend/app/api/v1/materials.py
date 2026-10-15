"""Materials CRUD endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.material import Material, MaterialCategory, MaterialStatusEnum
from app.models.facility import Yard, StorageLocation
from app.models.program import Ship
from app.models.transaction import MaterialTransaction
from app.models.transfer import MaterialTransfer
from app.schemas.common import SuccessResponse
from app.schemas.material import MaterialCreate, MaterialUpdate, MaterialRead

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.get("", response_model=SuccessResponse)
def list_materials(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    search: str = Query("", description="Search by ID, name, or batch"),
    category: str = Query("", description="Filter by category ID"),
    yard: str = Query("", description="Filter by yard ID"),
    status_filter: MaterialStatusEnum = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """
    List materials with pagination, search, and filtering.

    Query parameters:
    - search: Search materials by ID, name, or batch
    - category: Filter by category ID
    - yard: Filter by yard ID
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

    if status_filter:
        query = query.filter(Material.status == status_filter)

    total = query.count()
    materials = (
        query.order_by(Material.created_at.desc(), Material.id)
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Category '{material_data.category_id}' does not exist"
        )

    # Verify yard exists
    yard = db.query(Yard).filter(Yard.id == material_data.yard_id).first()
    if not yard:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Yard '{material_data.yard_id}' does not exist"
        )

    # Verify storage location if provided
    if material_data.location_id:
        location = db.query(StorageLocation).filter(
            StorageLocation.id == material_data.location_id
        ).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Storage location '{material_data.location_id}' does not exist"
            )
        if str(location.yard_id) != material_data.yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Storage location '{material_data.location_id}' does not belong to yard '{material_data.yard_id}'"
            )

    # Verify ship if provided
    if material_data.ship_id:
        ship = db.query(Ship).filter(Ship.id == material_data.ship_id).first()
        if not ship:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ship '{material_data.ship_id}' does not exist"
            )
        if str(ship.yard_id) != material_data.yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ship '{material_data.ship_id}' does not belong to yard '{material_data.yard_id}'"
            )

    # Create material
    material = Material(**material_data.model_dump())

    try:
        db.add(material)
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Yard '{yard_id}' does not exist"
            )

    # Re-check stored location/ship too, so a yard-only change cannot orphan them in the old yard.
    if placement_changed and location_id:
        location = db.query(StorageLocation).filter(StorageLocation.id == location_id).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Storage location '{location_id}' does not exist"
            )
        if str(location.yard_id) != yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Storage location '{location_id}' does not belong to yard '{yard_id}'"
            )

    if placement_changed and ship_id:
        ship = db.query(Ship).filter(Ship.id == ship_id).first()
        if not ship:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ship '{ship_id}' does not exist"
            )
        if str(ship.yard_id) != yard_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ship '{ship_id}' does not belong to yard '{yard_id}'"
            )

    # Validate quantity consistency
    quantity = update_data.get("quantity", material.quantity)
    available = update_data.get("available", material.available)
    reserved = update_data.get("reserved", material.reserved)

    if available + reserved > quantity:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"available ({available}) + reserved ({reserved}) "
                   f"cannot exceed quantity ({quantity})"
        )

    try:
        for field, value in update_data.items():
            setattr(material, field, value)
        if update_data:
            material.version += 1
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
