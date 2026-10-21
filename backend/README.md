# Dockyard Materials Command — Backend

FastAPI + SQLAlchemy + PostgreSQL API for the shipbuilding materials ERP: inventory batches, yard
transfers, procurement (suppliers, purchase orders, goods receipts), inspection holds, a stock ledger,
an audit feed, dashboard aggregates and rule-based analytics. The React frontend lives in `../frontend`.

## Quick start (Windows PowerShell)

Prerequisites: Python 3.11+, PostgreSQL 16, Node 22 (for the frontend).

```powershell
cd C:\ACD_cpb\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # then set DATABASE_URL in .env
alembic upgrade head                 # create or upgrade tables
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`DATABASE_URL` is **required** — the backend refuses to start without it rather than silently using a
local SQLite file. Use `postgresql+psycopg://USER:PASSWORD@localhost:5432/dockyard_inventory`
(URL-encode special characters in the password). SQLite works only if you set it explicitly.

Optional development data (categories, yards, locations, ships and four suppliers; never materials):
`python -m scripts.seed_reference_data`. It only inserts missing rows.

Frontend: `cd ..\frontend; npm install; npm run dev` → http://localhost:5173 (expects the API at
http://localhost:8000; override with `VITE_API_BASE_URL`).

Interactive API docs: http://localhost:8000/api/docs · health check: http://localhost:8000/health

## Schema migrations

Alembic, one linear history: `45e53a0f1df0` initial → `cab3875a1603` transfers → `8b06997ed8a5`
purchase orders → `6e07101bb214` goods receipts → `f3263eb479ec` inspection holds (head).
`alembic current` shows the applied revision. After changing a model:
`alembic revision --autogenerate -m "..."`, review the file, then `alembic upgrade head`. Back up the
database before applying migrations to it.

## Testing

```powershell
pytest -q                               # whole suite on temporary SQLite files; never touches DATABASE_URL
python scripts\run_pg_tests.py          # PostgreSQL-only tests (concurrency, SQL portability)
```

The PostgreSQL tests need a **separate** database, by default `<your database>_test` (e.g.
`dockyard_inventory_test`; create it once with `CREATE DATABASE dockyard_inventory_test OWNER dockyard_app;`),
or set `TEST_DATABASE_URL`. The runner refuses the development database, works in throwaway schemas,
never prints the password, and confirms the development database's row counts are unchanged.

## How stock is kept consistent

* A batch (`materials` row) has `quantity` (on hand), `available`, `reserved`; the rest is blocked
  (for example on inspection hold). Database CHECK constraints keep these consistent.
* Every change to stock writes a row to the stock ledger (`material_transactions`) in the same
  transaction: RECEIPT (goods receipts), TRANSFER_OUT / TRANSFER_IN (transfers), INSPECTION / RELEASE /
  RETURN / SCRAP (inspection holds), and ADJUSTMENT for manual inventory changes.
* Ledger quantities are positive, with direction given by the type — except manual ADJUSTMENT rows
  (no reference document), which are **signed**: `+n` added, `-n` removed, `0` when only available or
  reserved moved. Creating a batch with stock writes an opening-balance `+n`. Transit-shortage
  ADJUSTMENT rows (referencing a TR- transfer) are positive write-offs, as before.
* Changing on-hand, available or reserved through `PATCH /materials/{id}` requires `actor` and
  `stock_reason`; creating a batch with stock requires `actor`. Inspection holds, the
  available + reserved ≤ on-hand rule and stale-version checks are enforced first.
* Concurrent requests are serialised with row locks; purchase orders, receipts and transfers accept an
  `Idempotency-Key` so a retried request is replayed, not repeated.

## API (all under `/api/v1` unless noted)

| Area | Endpoints |
|---|---|
| Health | `GET /health` (API and database status; error details are logged, not returned) |
| Reference data | `GET /reference-data` (categories, yards, locations, ships) |
| Materials | `GET/POST /materials`, `GET/PATCH/DELETE /materials/{id}`, `GET /materials/summary`, `GET /materials/{id}/transactions` (ledger history). List filters: `search`, `category`, `yard`, `ship`, `status_filter` |
| Transfers | `GET/POST /transfers`, `GET /transfers/summary`, `GET /transfers/{id}`, `POST /transfers/{id}/approve · reject · cancel · dispatch · receive` |
| Suppliers | `GET/POST /suppliers`, `GET/PATCH /suppliers/{id}` |
| Purchase orders | `GET/POST /purchase-orders`, `GET /purchase-orders/summary`, `GET/PATCH /purchase-orders/{id}`, `POST /purchase-orders/{id}/approve · reopen · cancel · close`, `GET/POST /purchase-orders/{id}/receipts` |
| Inspections | `GET /inspections`, `GET /inspections/summary`, `GET /inspections/{id}`, `POST /inspections/{id}/release · reject` |
| Audit feed | `GET /audit-events` — stock ledger, transfer, purchase-order and inspection events; filters `source` (repeatable), `search`, `actor`, `date_from`, `date_to`, `skip`, `limit` ≤ 200 |
| Dashboard | `GET /dashboard/movements?months=1..24`, `GET /dashboard/ships`, `GET /dashboard/yards` |
| Analytics | `GET /analytics/overview` — categories, batch age, supplier, transfer and inspection figures and rule-based attention flags, computed from stored records (no AI model) |

Responses use `{"status": "success", "message": ..., "data": ...}`; errors use `{"detail": ...}` with
404 (not found), 409 (conflict, stale version, idempotency-key reuse) or 422 (validation).

## Project structure

```
app/
  main.py            FastAPI app and router registration
  config.py          settings from environment / .env (DATABASE_URL required)
  database.py        engine and session
  errors.py          404 / 409 / 422 exceptions
  models/            SQLAlchemy models
  schemas/           Pydantic request/response models
  services/          business rules (transfers, purchase orders, receipts, inspections, audit, analytics)
  api/v1/            routers
alembic/versions/    migrations
scripts/             seed_reference_data.py, run_pg_tests.py
tests/               pytest suite (*_pg.py files need PostgreSQL)
```

## Known limitations

* No sign-in or roles: the `actor` on each change is supplied by the client and not verified.
* Supplier changes, edits to non-stock fields, and inventory edits made before stock adjustments were
  recorded do not appear in the audit feed. The application only appends to its history tables, but
  the database does not enforce immutability.
* No stock valuation (costs), offline mode, notifications, export, or QR label printing / camera
  scanning. The Assistant and Analytics pages are rule-based; no AI model is connected.
* Timestamps are stored without a time zone in the database server's local time.
