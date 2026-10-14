# Quick Start Guide — Dockyard Materials Command

## Frontend (React 19 + Vite)

```powershell
# Terminal 1: Frontend
cd C:\ACD_cpb\frontend
pnpm install
pnpm run dev
# Available at http://localhost:8443
```

## Backend (FastAPI)

```powershell
# Terminal 2: Backend
cd C:\ACD_cpb\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Available at http://localhost:8000
```

## Verification

```powershell
# Terminal 3: Test
cd C:\ACD_cpb\backend
.\venv\Scripts\Activate.ps1
pytest tests/ -v
# Expected: 11 passed
```

## Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:8443 | React UI (Figma-generated) |
| Backend API | http://localhost:8000 | REST API |
| Swagger Docs | http://localhost:8000/api/docs | API Documentation |
| Health Check | http://localhost:8000/health | Backend Status |

## Database

**File:** `C:\ACD_cpb\backend\dockyard_materials.db`
- SQLite database (auto-created on first run)
- 8 tables: materials, yards, ships, suppliers, transactions, etc.
- Relationships and enums configured

## Stop Services

```powershell
# Stop with Ctrl+C in each terminal
# Or in PowerShell:
Get-Process python | Stop-Process -Force
```

## Common Commands

```powershell
# Run backend tests
pytest tests/ -v

# Format code
cd frontend
pnpm format

# Check dependencies
pip list
pip show fastapi

# View database schema
# (Open dockyard_materials.db with SQLite browser or:)
sqlite3 dockyard_materials.db ".schema"
```

---

**Module Status:** ✅ Backend Foundation Complete  
**Next:** Phase 1 — Inventory CRUD Implementation (pending approval)
