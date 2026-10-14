"""Read-only lookup lists used to populate material forms and filters."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.material import MaterialCategory
from app.models.facility import Yard, StorageLocation
from app.models.program import Ship
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/api/v1/reference-data", tags=["reference data"])


@router.get("", response_model=SuccessResponse)
def get_reference_data(db: Session = Depends(get_db)):
    """Categories, yards, storage locations and ships available for material records."""
    return SuccessResponse(
        message="Reference data retrieved successfully",
        data={
            "categories": [
                {"id": c.id, "name": c.name}
                for c in db.query(MaterialCategory).order_by(MaterialCategory.name)
            ],
            "yards": [
                {"id": y.id, "name": y.name}
                for y in db.query(Yard).order_by(Yard.name)
            ],
            "locations": [
                {"id": l.id, "yard_id": l.yard_id, "zone": l.zone, "aisle": l.aisle, "bin": l.bin}
                for l in db.query(StorageLocation).order_by(StorageLocation.yard_id, StorageLocation.zone, StorageLocation.aisle)
            ],
            "ships": [
                {"id": s.id, "name": s.name, "yard_id": s.yard_id}
                for s in db.query(Ship).order_by(Ship.name)
            ],
        },
    )
