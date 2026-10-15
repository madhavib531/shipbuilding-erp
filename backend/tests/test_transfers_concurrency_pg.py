"""PostgreSQL-only concurrency tests for transfer dispatch and receipt.

Skipped unless TEST_DATABASE_URL points at a separate PostgreSQL database. Each test works inside a
throwaway schema created and dropped by the fixture; nothing outside that schema is touched, and the
test refuses to run against the development database configured in DATABASE_URL.
"""

import os
import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base, Material, MaterialCategory, MaterialTransaction, MaterialTransfer, TransferStatus, Yard
from app.schemas.transfer import TransferReceive
from app.services import transfer_service as service

TEST_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is not set")


def _same_database(a, b) -> bool:
    return (a.host, a.port or 5432, a.database) == (b.host, b.port or 5432, b.database)


@pytest.fixture
def session_factory():
    url = make_url(TEST_URL)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must be a PostgreSQL URL")
    if _same_database(url, make_url(settings.database_url)):
        pytest.fail("TEST_DATABASE_URL must not point at the development database")

    schema = f"transfer_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=12)
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False)
        with factory() as s:
            s.add_all([MaterialCategory(id="C", name="Cat"), Yard(id="Y1", name="Y1", location="a", capacity=1.0),
                       Yard(id="Y2", name="Y2", location="b", capacity=1.0)])
            s.commit()
            s.add(Material(id="M", name="Plate", category_id="C", batch="B", unit="u",
                           quantity=10, available=10, reserved=0, yard_id="Y1"))
            s.commit()
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _approved_transfer(factory, quantity: int) -> int:
    with factory() as s:
        t = MaterialTransfer(material_id="M", quantity=quantity, unit="u", from_yard_id="Y1", to_yard_id="Y2",
                             status=TransferStatus.APPROVED, requested_by="test")
        s.add(t)
        s.commit()
        return t.id


def _run_concurrently(factory, actions):
    barrier = threading.Barrier(len(actions))
    results = [None] * len(actions)

    def worker(i, action):
        session = factory()
        try:
            barrier.wait()
            action(session)
            results[i] = "ok"
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


def _stock(factory):
    with factory() as s:
        m = s.get(Material, "M")
        outs = s.scalar(select(func.count()).select_from(MaterialTransaction).where(
            MaterialTransaction.transaction_type == "TRANSFER_OUT"))
        return m.quantity, m.available, outs


def test_competing_dispatches_never_oversell(session_factory):
    ids = [_approved_transfer(session_factory, 3) for _ in range(5)]  # 15 requested against 10 available
    results = _run_concurrently(session_factory, [lambda s, i=i: service.dispatch(s, i, "t", None) for i in ids])
    assert sorted(results, key=str) == sorted(["ok"] * 3 + [409] * 2, key=str), results
    assert _stock(session_factory) == (1, 1, 3)


def test_same_transfer_dispatched_concurrently_deducts_once(session_factory):
    tid = _approved_transfer(session_factory, 3)
    results = _run_concurrently(session_factory, [lambda s: service.dispatch(s, tid, "t", None)] * 6)
    assert results.count("ok") == 1 and results.count(409) == 5, results
    assert _stock(session_factory) == (7, 7, 1)


def test_same_transfer_received_concurrently_once(session_factory):
    tid = _approved_transfer(session_factory, 4)
    with session_factory() as s:
        service.dispatch(s, tid, "t", None)
    body = TransferReceive(actor="t", destination_material_id="M-Y2")
    results = _run_concurrently(session_factory, [lambda s: service.receive(s, tid, body)] * 6)
    assert results.count("ok") == 1 and results.count(409) == 5, results
    with session_factory() as s:
        assert s.get(Material, "M-Y2").quantity == 4
