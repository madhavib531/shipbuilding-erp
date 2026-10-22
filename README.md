# Dockyard Materials Command

Shipbuilding materials ERP: sign-in with roles, inventory batches with stock valuation, yard transfers,
procurement and goods receipts, inspection holds, QR batch labels and camera scanning, ships and yards,
notifications, an audit log, a live dashboard, rule-based analytics and an optional Claude-powered assistant.

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
python scripts\create_user.py --username admin --name "Your Name" --role Admin   # first time only
uvicorn app.main:app --port 8000 --reload

# 2. Web app — in a second terminal
cd frontend
npm install
npm run dev          # open http://localhost:8443 (the "Local" URL Vite prints) and sign in
npm run dev:https    # phones: open the https:// "Network" URL; accept the certificate warning once
```

## Check it

```powershell
cd backend;  pytest -q;  python scripts\run_pg_tests.py     # API tests (SQLite) and PostgreSQL tests
cd frontend; npx tsc --noEmit -p .;  npm run build           # type check and production build
```

## What is and isn't included

* **Sign-in and roles.** Everyone signs in; changes are recorded under the signed-in user. Roles: Admin,
  Storekeeper, Procurement, Inspector, Viewer (read-only). Admins manage users under Settings → Roles & access.
* **Currency is the Indian rupee (₹, INR).** New orders and batch costs default to INR. Amounts in other
  currencies keep their own currency and are converted to rupees for totals with exchange rates an admin
  enters in Settings → General; a currency without a rate is shown as not converted, never guessed.
* **Stock value** = on-hand quantity × unit cost, shown in rupees. Costs come from the purchase price on
  receipt, or are entered on a batch; batches without a cost are shown as not valued.
* **Yard selector** (top bar) filters every page; purchase orders by their optional delivery yard.
* **Notifications** are stored per user for the roles that handle each event; email is sent only if SMTP
  is configured in `backend/.env`.
* **Offline** is read-only: pages already opened are shown from this browser's cache with a banner; changes
  are refused until the server is reachable again. Production builds also keep the app itself offline.
* **Assistant** uses Claude when `ANTHROPIC_API_KEY` is set in `backend/.env` (questions and the records it
  looks up are sent to Anthropic; it can only read). Without a key it answers fixed questions by rule.
  Analytics stays rule-based.
* **QR labels** encode the batch ID; scanning a label offers transfer, inspection hold and stock edit.
* **CSV export** on Inventory, Procurement (orders, suppliers), Quality and the audit log; the dashboard
  report prints or saves as PDF.
