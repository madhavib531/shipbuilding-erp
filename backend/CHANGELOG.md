# Changelog — Dockyard Materials Command Backend

## [Unreleased] — Procurement M1: Supplier API

### Added
- Supplier directory API under `/api/v1/suppliers`: list (search, status and country filters, pagination),
  detail, create and partial update. Names are unique case-insensitively; suppliers are deactivated via
  status instead of being deleted. No schema change (the `suppliers` table already existed).
- Development seed now inserts four Approved suppliers.
- Supplier API tests, including a check that supplier changes never touch stock or the ledger.

## [Unreleased] — Module 3: Material Movements and Yard Transfers

### Added
- Transfer lifecycle API under `/api/v1/transfers`: request, approve, reject, cancel, dispatch, receive,
  list with status filters, summary counts, and detail with audit history.
- `material_transfers` and `material_transfer_events` tables (migration `cab3875a1603`).
- `TRANSFER_OUT` / `TRANSFER_IN` ledger types; dispatch and receipt write ledger rows, and receipt
  shortages are recorded as `ADJUSTMENT` rows with the discrepancy reason.
- Idempotent transfer creation via the `Idempotency-Key` header.
- `materials.version` and `expected_version` on `PATCH /api/v1/materials/{id}` for stale-edit protection.
- CHECK constraints on materials: non-negative stock and `available + reserved <= quantity`.
- Transfer tests (SQLite) and opt-in PostgreSQL concurrency tests (`TEST_DATABASE_URL`).

### Changed
- Material updates and deletes lock the row; deletes are refused while transfers reference the material.
- The SQLite fallback uses a connection pool for file databases (a single shared connection is now
  used only for in-memory SQLite), fixing corrupted reads and crashes under concurrent requests.

### Known limitations
- No authentication: `actor` is supplied by the client (the frontend sends the top-bar profile name).
- Downgrading `cab3875a1603` leaves the two new enum values in PostgreSQL's `transactiontype` type.

## [1.0.0] — 2026-10-10 (Module 1: Backend Foundation)

### Added

**Application Infrastructure**
- FastAPI application with CORS middleware for frontend communication
- Pydantic configuration management with environment variable support
- SQLAlchemy ORM with SQLite database backend
- Database session management and dependency injection
- Custom exception handling (ItemNotFoundError, InvalidInputError, ConflictError, InternalServerError)

**Database Models**
- `MaterialCategory` — Material classification
- `Material` — Inventory items with status tracking
- `Yard` — Shipyard facilities
- `StorageLocation` — Physical storage bins with capacity tracking
- `ShipSeries` — Ship design program lines
- `Ship` — Individual vessels under construction
- `Supplier` — Vendor management
- `MaterialTransaction` — Movement and transaction logging

**API Endpoints**
- `GET /` — Root endpoint with version info
- `GET /health` — Health check with database connectivity verification
- `GET /api/docs` — Swagger UI documentation
- `GET /api/redoc` — ReDoc documentation
- `GET /api/v1/materials` — Materials list endpoint (Phase 1 stub)

**Pydantic Schemas**
- `HealthCheckResponse` — Health check response model
- `ErrorResponse` — Standard error response
- `SuccessResponse` — Standard success response

**Testing Infrastructure**
- Pytest configuration with in-memory SQLite for testing
- Fixture-based test database setup
- Test fixtures: `db`, `client`
- 12 comprehensive tests covering:
  - Health endpoints (3 tests)
  - API documentation (1 test)
  - Database models (8 tests)

**Configuration & Documentation**
- `.env.example` — Environment variable template
- `.gitignore` — Python/IDE/database exclusions
- `requirements.txt` — Python dependencies (FastAPI, Uvicorn, SQLAlchemy, Pydantic, pytest)
- Comprehensive `README.md` with:
  - Quick start guide
  - Installation instructions
  - Running & testing procedures
  - Database schema documentation
  - API endpoint reference
  - CORS configuration details
  - Troubleshooting guide
  - Extension guidelines

### Database Schema

**Core Tables:**
- `material_categories` — Material classifications
- `materials` — Inventory with relationships to categories, yards, locations, ships
- `yards` — Shipyard facilities
- `storage_locations` — Physical storage with capacity tracking
- `ship_series` — Ship design program lines
- `ships` — Vessels under construction
- `suppliers` — Vendor directory
- `material_transactions` — Transaction log for all material movements

**Key Features:**
- Proper foreign key relationships
- Enumerations for status fields (MaterialStatus, YardStatus, ShipBuildStatus, etc.)
- Timestamp tracking (created_at, updated_at) via TimestampMixin
- Capacity and load tracking for locations
- Progress tracking for ship builds
- Multi-actor transaction logging

### Configuration

**CORS Origins (for frontend):**
- http://localhost:8443 (Vite default)
- http://localhost:5173 (Vite alternative)
- http://127.0.0.1:8443
- http://127.0.0.1:5173

**Default Settings:**
- SQLite database: `./dockyard_materials.db`
- Server: 0.0.0.0:8000
- Debug mode: True
- Auto-reload on file changes

### Testing Results

**Test Suite:** ✓ 12/12 Passing

```
tests/test_health.py::test_root_endpoint PASSED
tests/test_health.py::test_health_check PASSED
tests/test_health.py::test_openapi_docs PASSED
tests/test_health.py::test_materials_list_endpoint PASSED
tests/test_models.py::test_material_category_creation PASSED
tests/test_models.py::test_material_creation_with_category PASSED
tests/test_models.py::test_yard_creation PASSED
tests/test_models.py::test_storage_location_creation PASSED
tests/test_models.py::test_ship_series_creation PASSED
tests/test_models.py::test_ship_creation PASSED
tests/test_models.py::test_supplier_creation PASSED
tests/test_models.py::test_material_transaction_creation PASSED
```

### Known Limitations

**Not Implemented (Phase 1+):**
- Material CRUD operations (full implementation)
- Receipt/inbound logistics workflows
- Transfer/movement request handling
- Purchase order creation and tracking
- QR code/batch tracking system
- Quality inspection workflows
- Audit event logging system
- AI analytics and forecasting
- Chat/assistant backend
- User authentication and authorization
- Database migrations (Alembic)
- Production-grade error logging
- Rate limiting
- Caching strategies

### File Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 (FastAPI app + CORS)
│   ├── config.py               (Environment settings)
│   ├── database.py             (SQLAlchemy setup)
│   ├── errors.py               (Custom exceptions)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py             (Base + TimestampMixin)
│   │   ├── material.py         (Material, MaterialCategory)
│   │   ├── facility.py         (Yard, StorageLocation)
│   │   ├── program.py          (Ship, ShipSeries)
│   │   ├── supplier.py         (Supplier)
│   │   └── transaction.py      (MaterialTransaction, TransactionType)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── common.py           (Responses)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py           (Health endpoint)
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── materials.py    (Materials stub)
│   └── services/
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py             (Fixtures)
│   ├── test_health.py          (Health tests)
│   └── test_models.py          (Model tests)
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── CHANGELOG.md
└── (dockyard_materials.db — created on first run)
```

### Breaking Changes

None. This is the initial release.

### Migration Guide

No migrations required for Module 1 (initial setup).

For upgrading from development snapshots:
1. Delete existing `dockyard_materials.db`
2. Run backend: `uvicorn app.main:app --reload`
3. Database auto-creates on startup

### Dependencies

**Production:**
- fastapi==0.104.1
- uvicorn==0.24.0
- sqlalchemy==2.0.23
- pydantic==2.5.0
- pydantic-settings==2.1.0
- python-dotenv==1.0.0

**Development/Testing:**
- pytest==7.4.3
- pytest-asyncio==0.21.1
- httpx==0.25.2

### Next Release

**Module 1 → Phase 1: Inventory CRUD**
- Implement full Material CRUD endpoints
- Add search, filtering, and pagination
- Create comprehensive Material schemas
- Wire frontend to backend endpoints
- Implement error handling and validation

---

**Version:** 1.0.0  
**Release Date:** 2026-10-10  
**Status:** Module 1 Complete, Ready for Phase 1 Implementation  
**Maintainer:** Development Team
