"""Run the PostgreSQL-only tests (tests/test_*_pg.py) against a separate test database.

Usage, from backend/:
    python scripts/run_pg_tests.py            # uses TEST_DATABASE_URL, or <your database>_test
    python scripts/run_pg_tests.py -k audit   # extra arguments go to pytest

The test URL is TEST_DATABASE_URL if set, otherwise DATABASE_URL with the database name suffixed
"_test" (e.g. dockyard_inventory_test). It refuses to run against the DATABASE_URL database. Tests work
in throwaway schemas they create and drop. The password is passed to pytest in its environment only
and is never printed. The development database is only read, to show its row counts are unchanged.
"""

import os
import subprocess
import sys
from glob import glob
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import settings  # noqa: E402

COUNTED = ("materials", "material_transactions", "material_transfers", "purchase_orders", "inspection_holds")


def same_database(a, b) -> bool:
    return (a.host, a.port or 5432, a.database) == (b.host, b.port or 5432, b.database)


def dev_counts(url) -> dict:
    with create_engine(url).connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        tables = {r[0] for r in c.execute(text("select tablename from pg_tables where schemaname = 'public'"))}
        return {t: c.execute(text(f'select count(*) from public."{t}"')).scalar() for t in COUNTED if t in tables}


def main() -> int:
    dev = make_url(settings.database_url)
    if not dev.drivername.startswith("postgresql"):
        print("DATABASE_URL is not PostgreSQL; these tests need PostgreSQL.")
        return 2
    test = make_url(os.environ["TEST_DATABASE_URL"]) if os.environ.get("TEST_DATABASE_URL") else dev.set(database=f"{dev.database}_test")
    if not test.drivername.startswith("postgresql") or same_database(test, dev):
        print("Refusing to run: the test database must be a different PostgreSQL database than DATABASE_URL.")
        return 2
    print("development database:", dev.render_as_string(hide_password=True))
    print("test database:       ", test.render_as_string(hide_password=True))
    try:
        with create_engine(test).connect() as c:
            c.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001 - report and stop
        print(f"Cannot connect to the test database ({type(exc).__name__}). Create it first, e.g. in psql:")
        print(f"    CREATE DATABASE {test.database} OWNER {test.username};")
        return 2

    before = dev_counts(dev)
    files = sorted(glob("tests/test_*_pg.py"))
    env = {**os.environ, "TEST_DATABASE_URL": test.render_as_string(hide_password=False)}
    result = subprocess.run([sys.executable, "-m", "pytest", *files, "-v", "-rs", "-p", "no:warnings", *sys.argv[1:]], env=env)
    after = dev_counts(dev)
    print("development row counts before:", before)
    print("development row counts after: ", after, "(unchanged)" if before == after else "(CHANGED — investigate)")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
