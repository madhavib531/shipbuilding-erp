"""Shared helpers for opt-in PostgreSQL concurrency tests.

Tests using these helpers are skipped unless TEST_DATABASE_URL points at a separate PostgreSQL
database. Each test works inside a throwaway schema that is created and dropped here; nothing outside
that schema is touched, and the development database configured in DATABASE_URL is refused.
"""

import os
import threading
import uuid
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base

TEST_URL = os.environ.get("TEST_DATABASE_URL")
requires_pg = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is not set")


def _same_database(a, b) -> bool:
    return (a.host, a.port or 5432, a.database) == (b.host, b.port or 5432, b.database)


@contextmanager
def pg_session_factory(prefix: str, seed):
    """Yields a session factory bound to a fresh schema seeded by `seed(session)`."""
    url = make_url(TEST_URL)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must be a PostgreSQL URL")
    if _same_database(url, make_url(settings.database_url)):
        pytest.fail("TEST_DATABASE_URL must not point at the development database")

    schema = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=12)
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False)
        with factory() as session:
            seed(session)
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def run_concurrently(factory, actions):
    """Runs each action(session) in its own thread, released together. Returns per-action results:
    "ok", the HTTP status of a raised HTTPException, or the repr of any other exception."""
    barrier = threading.Barrier(len(actions))
    results = [None] * len(actions)

    def worker(i, action):
        session = factory()
        try:
            barrier.wait()
            outcome = action(session)
            results[i] = "ok" if outcome is None else ("ok", outcome)
        except HTTPException as exc:
            session.rollback()
            results[i] = exc.status_code
        except Exception as exc:
            session.rollback()
            results[i] = repr(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i, a)) for i, a in enumerate(actions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results
