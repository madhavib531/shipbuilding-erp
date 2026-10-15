"""PostgreSQL-only concurrency tests for transfer dispatch and receipt (see tests/pg_support.py)."""

import pytest
from sqlalchemy import func, select

from app.models import Material, MaterialCategory, MaterialTransaction, MaterialTransfer, TransferStatus, Yard
from app.schemas.transfer import TransferReceive
from app.services import transfer_service as service
from tests.pg_support import pg_session_factory, requires_pg, run_concurrently

pytestmark = requires_pg


def _seed(s):
    s.add_all([MaterialCategory(id="C", name="Cat"), Yard(id="Y1", name="Y1", location="a", capacity=1.0),
               Yard(id="Y2", name="Y2", location="b", capacity=1.0)])
    s.commit()
    s.add(Material(id="M", name="Plate", category_id="C", batch="B", unit="u",
                   quantity=10, available=10, reserved=0, yard_id="Y1"))
    s.commit()


@pytest.fixture
def session_factory():
    with pg_session_factory("transfer_test", _seed) as factory:
        yield factory


def _approved_transfer(factory, quantity: int) -> int:
    with factory() as s:
        t = MaterialTransfer(material_id="M", quantity=quantity, unit="u", from_yard_id="Y1", to_yard_id="Y2",
                             status=TransferStatus.APPROVED, requested_by="test")
        s.add(t)
        s.commit()
        return t.id


def _stock(factory):
    with factory() as s:
        m = s.get(Material, "M")
        outs = s.scalar(select(func.count()).select_from(MaterialTransaction).where(
            MaterialTransaction.transaction_type == "TRANSFER_OUT"))
        return m.quantity, m.available, outs


def test_competing_dispatches_never_oversell(session_factory):
    ids = [_approved_transfer(session_factory, 3) for _ in range(5)]  # 15 requested against 10 available
    results = run_concurrently(session_factory, [lambda s, i=i: service.dispatch(s, i, "t", None) for i in ids])
    assert sorted(results, key=str) == sorted(["ok"] * 3 + [409] * 2, key=str), results
    assert _stock(session_factory) == (1, 1, 3)


def test_same_transfer_dispatched_concurrently_deducts_once(session_factory):
    tid = _approved_transfer(session_factory, 3)
    results = run_concurrently(session_factory, [lambda s: service.dispatch(s, tid, "t", None)] * 6)
    assert results.count("ok") == 1 and results.count(409) == 5, results
    assert _stock(session_factory) == (7, 7, 1)


def test_same_transfer_received_concurrently_once(session_factory):
    tid = _approved_transfer(session_factory, 4)
    with session_factory() as s:
        service.dispatch(s, tid, "t", None)
    body = TransferReceive(actor="t", destination_material_id="M-Y2")
    results = run_concurrently(session_factory, [lambda s: service.receive(s, tid, body)] * 6)
    assert results.count("ok") == 1 and results.count(409) == 5, results
    with session_factory() as s:
        assert s.get(Material, "M-Y2").quantity == 4
