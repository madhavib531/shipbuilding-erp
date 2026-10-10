# Dockyard Materials Command — Backend Foundation (Module 1)

**AI-Driven Material Management System for Shipbuilding**

## Overview

This is the FastAPI backend foundation for the Shipbuilding ERP Dashboard. Module 1 establishes:
- Database schema for core entities (Materials, Yards, Ships, Suppliers, Transactions)
- CORS-configured FastAPI application
- Health check and API documentation endpoints
- Pydantic validation schemas
- SQLite database with SQLAlchemy ORM
- Comprehensive test suite

**Status:** Phase 1 Backend Foundation (Ready for Module 1 Inventory CRUD implementation)

## Quick Start

### Prerequisites
- Python 3.10+
- pip or uv package manager

### Installation

1. **Navigate to backend directory:**
```powershell
cd C:\ACD_cpb\backend
```

2. **Create and activate virtual environment:**
```powershell
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

3. **Install dependencies:**
```powershell
pip install -r requirements.txt
```

4. **Create .env file (optional — defaults provided in config.py):**
```powershell
Copy-Item ".env.example" ".env"
# Edit .env if needed
```

5. **Initialize database:**
```powershell
# Database is auto-created on first run, or manually:
python -c "from app.database import init_db; init_db()"
```

### Running the Server

**Development mode:**
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Server runs at: `http://localhost:8000`

**Production mode (no auto-reload):**
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Verification Steps

1. **Health check:**
```powershell
# PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing | Select-Object -ExpandProperty Content

# Or via browser:
# http://localhost:8000/health
```

2. **Swagger API documentation:**
```
http://localhost:8000/api/docs
```

3. **ReDoc documentation:**
```
http://localhost:8000/api/redoc
```

4. **Materials list endpoint (Phase 1 stub):**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/materials" -UseBasicParsing | Select-Object -ExpandProperty Content
```

## Testing

### Run all tests:
```powershell
pytest -v
```

### Run specific test file:
```powershell
pytest tests/test_health.py -v
pytest tests/test_models.py -v
```

### Run with coverage:
```powershell
pytest --cov=app tests/
```

### Expected test results:
- `test_root_endpoint` — ✓ Pass
- `test_health_check` — ✓ Pass
- `test_openapi_docs` — ✓ Pass
- `test_materials_list_endpoint` — ✓ Pass
- `test_*_creation` (models) — ✓ Pass (8 model tests)

**Total:** 12 tests, all passing

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app initialization + CORS
│   ├── config.py               # Environment settings
│   ├── database.py             # SQLAlchemy engine & session management
│   ├── errors.py               # Custom exception classes
│   ├── models/
│   │   ├── base.py             # Base model + TimestampMixin
│   │   ├── material.py         # Material, MaterialCategory
│   │   ├── facility.py         # Yard, StorageLocation
│   │   ├── program.py          # Ship, ShipSeries
│   │   ├── supplier.py         # Supplier
│   │   └── transaction.py      # MaterialTransaction, TransactionType
│   ├── schemas/
│   │   ├── common.py           # HealthCheckResponse, ErrorResponse, SuccessResponse
│   │   └── (future phases: material.py, facility.py, program.py)
│   ├── api/
│   │   ├── health.py           # GET /health
│   │   └── v1/
│   │       └── materials.py    # GET /api/v1/materials (stub)
│   └── services/               # Business logic (to be populated)
├── tests/
│   ├── conftest.py             # Pytest fixtures & in-memory DB
│   ├── test_health.py          # Endpoint tests
│   └── test_models.py          # ORM model tests
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Database Schema

### Core Entities

**MaterialCategory** (`material_categories`)
- `id` (PK): Category identifier
- `name`: Unique category name
- `description`: Optional description
- Timestamps: `created_at`, `updated_at`

**Material** (`materials`)
- `id` (PK): Material identifier (e.g., STL-10084)
- `name`: Full material name
- `category_id` (FK): Reference to MaterialCategory
- `batch`: Batch/lot identifier
- `quantity`: Total available quantity
- `available`: Unreserved quantity
- `reserved`: Allocated quantity
- `unit`: Unit of measurement (sheets, lengths, meters, etc.)
- `yard_id` (FK): Reference to Yard
- `location_id` (FK): Reference to StorageLocation
- `ship_id` (FK): Reference to Ship (allocated to)
- `status`: Enum (Healthy, Low stock, Inspection, Reserved)
- Timestamps

**Yard** (`yards`)
- `id` (PK): Yard identifier
- `name`: Unique yard name
- `location`: Geographic/site location
- `capacity`: Facility capacity (m² or tonnes)
- `status`: Enum (Active, Maintenance, Closed)
- Timestamps

**StorageLocation** (`storage_locations`)
- `id` (PK): Location identifier
- `yard_id` (FK): Reference to Yard
- `zone`: Zone code (A1, B2, etc.)
- `aisle`: Aisle identifier
- `bin`: Bin number (optional)
- `capacity`: Max items/weight
- `current_load`: Current items/weight
- `status`: Enum (Available, Full, Maintenance, Restricted)
- Timestamps

**ShipSeries** (`ship_series`)
- `id` (PK): Series identifier
- `name`: Unique series name
- `description`: Design/type
- `design_spec`: Specification notes
- Timestamps

**Ship** (`ships`)
- `id` (PK): Ship identifier (e.g., MV-CALYPSO)
- `name`: Unique ship name
- `series_id` (FK): Reference to ShipSeries
- `yard_id` (FK): Reference to Yard
- `build_status`: Enum (Planning through Commissioned)
- `build_progress`: Percentage 0-100
- `allocated_value`: Total material value allocated (USD)
- `material_line_count`: Number of material lines
- `scheduled_launch`: Launch date
- `scheduled_commissioning`: Commissioning date
- Timestamps

**Supplier** (`suppliers`)
- `id` (PK): Supplier identifier
- `name`: Unique supplier name
- `contact_person`, `contact_email`, `contact_phone`: Contact info
- `address`, `country`: Address details
- `status`: Enum (Approved, Conditional, Probation, Inactive, Blocked)
- `notes`: Optional notes
- Timestamps

**MaterialTransaction** (`material_transactions`)
- `id` (PK): Transaction identifier
- `material_id` (FK): Reference to Material
- `transaction_type`: Enum (Receipt, Issuance, Transfer, Adjustment, Return, Scrap, Inspection, Quarantine, Release)
- `quantity`: Amount moved
- `unit`: Unit of measurement
- `from_location_id` (FK): Source location
- `to_location_id` (FK): Destination location
- `from_ship_id`, `to_ship_id`: Ship allocations
- `reference_id`: Related PO, Receipt, or Transfer ID
- `actor`: User who performed action
- `reason`: Optional reason/notes
- `status`: Transaction status
- Timestamps

### Relationships

```
MaterialCategory ←→ Material
Yard ←→ Material
Yard ←→ StorageLocation
StorageLocation ←→ Material
Ship ←→ Material
ShipSeries ←→ Ship
Material ←→ MaterialTransaction
```

## API Endpoints (Module 1)

### Health & Status
- `GET /` — Root endpoint with version info
- `GET /health` — Health check (database connectivity verification)

### API Documentation
- `GET /api/docs` — Swagger UI
- `GET /api/redoc` — ReDoc documentation
- `GET /api/openapi.json` — OpenAPI schema

### Materials (Phase 1 Stub)
- `GET /api/v1/materials` — List materials (stub endpoint, returns empty dataset)

**Full Materials CRUD endpoints** (Phase 1, to be implemented):
- `GET /api/v1/materials/{id}` — Get material detail
- `POST /api/v1/materials` — Create material
- `PATCH /api/v1/materials/{id}` — Update material
- `DELETE /api/v1/materials/{id}` — Delete material

## CORS Configuration

Frontend origin is automatically allowed for Vite development servers:
- `http://localhost:8443` (main Vite port)
- `http://localhost:5173` (alternative Vite port)
- `http://127.0.0.1:8443`
- `http://127.0.0.1:5173`

Configured in `app/config.py` via `CORS_ORIGINS` environment variable.

## Environment Configuration

Settings are managed by Pydantic `BaseSettings` in `app/config.py`. Priority:
1. `.env` file (if present)
2. Environment variables
3. Hardcoded defaults in `Settings` class

**Key settings:**
```
DATABASE_URL=sqlite:///./dockyard_materials.db
APP_NAME=Dockyard Materials Command
APP_VERSION=1.0.0
DEBUG=True
CORS_ORIGINS=http://localhost:8443,http://localhost:5173
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

## Known Limitations (Module 1)

✓ **Implemented:**
- Database schema for core entities
- CORS configuration for frontend
- Health check endpoint
- SQLAlchemy ORM models with relationships
- Pydantic validation schemas
- Test fixtures and basic test suite
- OpenAPI/Swagger documentation

⚠️ **Not yet implemented (Phase 1+):**
- Material CRUD operations
- Receipt/inbound logistics
- Transfers/movements
- Purchase order tracking
- QR/batch tracking
- Quality inspections
- Audit event logging
- AI analytics endpoints
- Chat/assistant backend
- Offline sync snapshots
- Database migrations (Alembic)
- User authentication/authorization
- Production-grade error handling

## Extending the Backend

### Adding a New Endpoint (Phase 1+)

1. **Create model** (if needed): `app/models/your_entity.py`
2. **Create schema** (if needed): `app/schemas/your_entity.py`
3. **Create router**: `app/api/v1/your_entity.py`
4. **Create service** (if needed): `app/services/your_entity_service.py`
5. **Include in main.py**: `app.include_router(your_router)`
6. **Add tests**: `tests/test_your_entity.py`

### Example: Adding Receipt Endpoint

```python
# app/models/receipt.py
class Receipt(Base, TimestampMixin):
    __tablename__ = "receipts"
    id = Column(String(50), primary_key=True)
    purchase_order_id = Column(String(50), ForeignKey("purchase_orders.id"))
    material_id = Column(String(50), ForeignKey("materials.id"))
    quantity_received = Column(Integer)
    # ...

# app/api/v1/receipts.py
router = APIRouter(prefix="/api/v1/receipts", tags=["receipts"])

@router.post("")
def create_receipt(data: ReceiptCreate, db: Session = Depends(get_db)):
    # Implementation in Phase 1
    pass

# app/main.py
app.include_router(receipts.router)
```

## Troubleshooting

### Database File Permission Error (Windows)
If `dockyard_materials.db` cannot be created:
```powershell
# Ensure backend directory is writable
icacls "C:\ACD_cpb\backend" /grant:r "$env:USERNAME`:F"
```

### Port Already in Use
```powershell
# Check what's using port 8000
Get-NetTCPConnection -LocalPort 8000

# Use a different port
uvicorn app.main:app --port 8001
```

### Import Errors
```powershell
# Verify virtual environment is active
.\venv\Scripts\Activate.ps1

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Next Steps (Module 1 → Phase 1)

1. **Implement Material CRUD** — GET list/detail, POST create, PATCH update
2. **Add search & filtering** — By category, yard, ship, status
3. **Wire frontend to backend** — Update React to fetch from `/api/v1/materials`
4. **Test end-to-end** — Frontend ↔ Backend integration

## Documentation References

- **FastAPI:** https://fastapi.tiangolo.com/
- **SQLAlchemy:** https://docs.sqlalchemy.org/
- **Pydantic:** https://docs.pydantic.dev/
- **Uvicorn:** https://www.uvicorn.org/

---

**Module 1 Status:** ✓ Complete  
**Ready for:** Phase 1 Inventory CRUD Implementation  
**Requires Approval:** Before proceeding to Module 2
