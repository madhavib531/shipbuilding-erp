# Dockyard Materials Command

Shipbuilding materials ERP: inventory batches, yard transfers, procurement and goods receipts,
inspection holds, QR batch labels and camera scanning, ships and yards, an audit log, a live dashboard and rule-based
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
npm run dev          # open http://localhost:8443 (the "Local" URL Vite prints)
```

## Check it

```powershell
cd backend;  pytest -q;  python scripts\run_pg_tests.py     # API tests (SQLite) and PostgreSQL tests
cd frontend; npx tsc --noEmit -p .;  npm run build           # type check and production build
```

## What is and isn't included

Everything on screen reads live data. There is no sign-in (actor names are not verified), no offline
mode, no stored or emailed notifications (the bell shows live alerts read from current records) and no stock
valuation. The top-bar yard selector filters Inventory and Movements only. Inventory and the audit log export their filtered
lists as CSV; the dashboard report prints (or saves as PDF) from the browser. QR labels encode the batch ID and are printed
from the browser; camera scanning needs the app opened at http://localhost or over HTTPS.
The Assistant and Analytics pages use fixed rules over live data; no AI model is connected.
