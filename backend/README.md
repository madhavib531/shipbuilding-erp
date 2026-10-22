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
python scripts\create_user.py --username admin --name "Your Name" --role Admin   # first admin (asks for a password)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Every endpoint except `/health` and `/api/v1/auth/login` needs a session: sign in with
`POST /api/v1/auth/login` and send `Authorization: Bearer <token>` (sessions last 12 hours). Passwords are
stored as scrypt hashes; tokens only as SHA-256 digests; five failed sign-ins for a username lock it for
15 minutes. Changes are recorded under the signed-in user, whatever `actor` a request body says.

| Role | Can change |
|---|---|
| Admin | everything, including users |
| Storekeeper | inventory, transfers, goods receipts, inspection holds |
| Procurement | suppliers and purchase orders |
| Inspector | inspection holds and decisions |
| Viewer | nothing (read-only) |

Optional settings in `.env`: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`,
`SMTP_STARTTLS` (true) to email notifications; `ANTHROPIC_API_KEY` (and `ASSISTANT_MODEL`, default
`claude-sonnet-5-5`) to let the Assistant answer with Claude.

`DATABASE_URL` is **required** — the backend refuses to start without it rather than silently using a
local SQLite file. Use `postgresql+psycopg://USER:PASSWORD@localhost:5432/dockyard_inventory`
(URL-encode special characters in the password). SQLite works only if you set it explicitly.

Optional development data (categories, yards, locations, ships and four suppliers; never materials):
`python -m scripts.seed_reference_data`. It only inserts missing rows.

Phones: `npm run dev:https` serves the app over self-signed HTTPS and proxies `/api` to the backend, so the
camera works and no CORS change is needed (set `API_PROXY_TARGET` if the API is not on localhost:8000).

Frontend: `cd ..\frontend; npm install; npm run dev` → open **http://localhost:8443** (expects the API
at http://localhost:8000; override with `VITE_API_BASE_URL`). The API only accepts browser requests
from the origins in `CORS_ORIGINS` (default: `localhost`/`127.0.0.1` on ports 8443 and 5173). Opening the
app from another address — such as Vite's "Network" URL or a different port — makes every request fail
with `400 Disallowed CORS origin`; add that address to `CORS_ORIGINS` in `.env` if you need it.

Interactive API docs: http://localhost:8000/api/docs · health check: http://localhost:8000/health

## Schema migrations

Alembic, one linear history: `45e53a0f1df0` initial → `cab3875a1603` transfers → `8b06997ed8a5`
purchase orders → `6e07101bb214` goods receipts → `f3263eb479ec` inspection holds → `9d4c2a7e1b30`
manual inspection holds → `a7c1e5d2f4b8` users and sessions → `d2f6b8a1c3e5` stock valuation, delivery
yard and notifications → `e8b3c1f4a9d2` exchange rates (head). The last three add tables and nullable
columns only; no data is changed.
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
* An inspection hold is opened by a goods receipt ("Hold for inspection") or by hand on existing stock
  (`POST /inspections`): that moves the quantity from available to held (on hand is unchanged) with an
  INSPECTION ledger row. Release returns it to available; rejection removes it from on hand. Only receipt
  holds can be returned to the supplier (the quantity stays owed on the order); stock held by hand can
  only be scrapped. A batch with an open hold has status Inspection and cannot receive more goods.
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
| Inspections | `GET /inspections`, `GET /inspections/summary`, `GET /inspections/{id}`, `POST /inspections` (hold available stock: `material_id`, `quantity`, `reason`, `actor`), `POST /inspections/{id}/release · reject` |
| Audit feed | `GET /audit-events` — stock ledger, transfer, purchase-order and inspection events; filters `source` (repeatable), `search`, `actor`, `date_from`, `date_to`, `skip`, `limit` ≤ 200 |
| Dashboard | `GET /dashboard/movements?months=1..24`, `GET /dashboard/ships`, `GET /dashboard/yards` |
| Analytics | `GET /analytics/overview` — categories, batch age, supplier, transfer and inspection figures and rule-based attention flags, computed from stored records (no AI model) |
| Sign-in | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/password` |
| Users (Admin) | `GET/POST /users`, `PATCH /users/{id}` (name, email, role, active), `POST /users/{id}/password` |
| Notifications | `GET /notifications` (own, with unread count), `POST /notifications/{id}/read`, `POST /notifications/read-all` |
| Assistant | `GET /assistant/status`, `POST /assistant/ask` (Claude with read-only tools; 503 without `ANTHROPIC_API_KEY`) |
| Exchange rates | `GET /exchange-rates` (base currency and rates), `PUT /exchange-rates/{currency}` `{"rate"}` and `DELETE /exchange-rates/{currency}` (Admin) |

`yard` filters `GET /materials/summary`, `/transfers/summary`, `/inspections`, `/inspections/summary`,
`/purchase-orders` and `/purchase-orders/summary` (delivery yard), `/dashboard/movements`, `/dashboard/ships`
and `/audit-events`. Batches carry `unit_cost` and `cost_currency`; `GET /materials/summary` adds
`stock_value` per currency, `stock_value_base` (converted into INR) and `unvalued_batches`;
`GET /purchase-orders/summary` adds `open_value_base`. The base currency is `BASE_CURRENCY` (default INR).

Responses use `{"status": "success", "message": ..., "data": ...}`; errors use `{"detail": ...}` with
401 (not signed in), 403 (role), 404 (not found), 409 (conflict, stale version, idempotency-key reuse),
422 (validation) or 429 (too many failed sign-ins).

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

* Supplier changes, edits to non-stock fields, and inventory edits made before stock adjustments were
  recorded do not appear in the audit feed. The application only appends to its history tables, but
  the database does not enforce immutability.
* Exchange rates are entered by an admin and used as they stand (no history, no online feed); conversion is
  for totals only. A receipt into a batch that already holds uncosted stock, or is costed in another
  currency, leaves its cost unchanged.
* Offline mode is read-only; nothing is queued or synced. Yard filters on the stock ledger and inspections
  use the batch's current yard. Login throttling is per backend process.
* Email is sent synchronously after a change when SMTP is configured; failures are logged, never retried.
* QR labels are printed from the browser (no label-printer integration).
* `requirements.txt` pins older versions than the ones installed in the development venv (FastAPI, Starlette,
  Pydantic, SQLAlchemy, httpx); the code is tested against the installed versions.
* Timestamps are stored without a time zone in the database server's local time.
