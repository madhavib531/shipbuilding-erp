# Dockyard Materials Command

Shipbuilding materials ERP: inventory batches, yard transfers, procurement and goods receipts,
inspection holds, QR batch lookup, ships and yards, an audit log, a live dashboard and rule-based
analytics.

| Part | Stack | Folder |
|---|---|---|
| API | Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL | [`backend/`](backend/README.md) |
| Web app | React 19, TypeScript, Vite | `frontend/` |

## Run it (Windows PowerShell)

```powershell
# 1. API — needs PostgreSQL and DATABASE_URL in backend\.env (see backend/README.md)
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --port 8000 --reload

# 2. Web app — in a second terminal
cd frontend
npm install
npm run dev          # http://localhost:5173
```

## Check it

```powershell
cd backend;  pytest -q;  python scripts\run_pg_tests.py     # API tests (SQLite) and PostgreSQL tests
cd frontend; npx tsc --noEmit -p .;  npm run build           # type check and production build
```

## What is and isn't included

Everything on screen reads live data. There is no sign-in (actor names are not verified), no offline
mode, no notifications, no export, no stock valuation, and no QR label printing or camera scanning.
The Assistant and Analytics pages use fixed rules over live data; no AI model is connected.
