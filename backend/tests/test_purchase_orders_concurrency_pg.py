"""PostgreSQL-only concurrency tests for purchase orders (see tests/pg_support.py)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models import MaterialCategory, PurchaseOrder, PurchaseOrderEvent, Supplier
from app.schemas.purchase_order import (
    PurchaseOrderAction, PurchaseOrderCreate, PurchaseOrderReasonAction, PurchaseOrderUpdate,
)
from app.services import purchase_order_service as service
from tests.pg_support import pg_session_factory, requires_pg, run_concurrently

pytestmark = requires_pg

LINE = {"category_id": "C", "description": "Plate", "unit": "u", "ordered_quantity": 5,
        "unit_price": "10.0000", "currency": "EUR"}


def _seed(s):
    s.add_all([Supplier(id="S", name="Supplier"), MaterialCategory(id="C", name="Cat")])
    s.commit()


@pytest.fixture
def session_factory():
    with pg_session_factory("po_test", _seed) as factory:
        yield factory


def _body(**over):
    data = {"actor": "t", "supplier_id": "S", "lines": [LINE], "expected_delivery_date": str(date.today() + timedelta(days=5))}
    data.update(over)
    return PurchaseOrderCreate(**data)


def _draft(factory) -> int:
    with factory() as s:
        return service.create_order(s, _body(), None)[0]


def _count(factory, model, *where):
    with factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def test_same_idempotency_key_creates_one_order(session_factory):
    body = _body()
    results = run_concurrently(session_factory, [lambda s: service.create_order(s, body, "k-1")] * 6)
    ids = {r[1][0] for r in results if isinstance(r, tuple)}
    assert len(ids) == 1 and all(isinstance(r, tuple) for r in results), results
    assert _count(session_factory, PurchaseOrder) == 1


def test_concurrent_creation_allocates_distinct_numbers(session_factory):
    results = run_concurrently(session_factory, [lambda s: service.create_order(s, _body(), None)] * 8)
    ids = [r[1][0] for r in results if isinstance(r, tuple)]
    assert len(ids) == 8 and len(set(ids)) == 8, results
    assert _count(session_factory, PurchaseOrder) == 8


def test_approve_racing_edit_lets_exactly_one_win(session_factory):
    oid = _draft(session_factory)
    approve = lambda s: service.approve(s, oid, PurchaseOrderAction(actor="a", expected_version=1))
    edit = lambda s: service.update_draft(s, oid, PurchaseOrderUpdate(actor="e", expected_version=1, notes="late edit"))
    results = run_concurrently(session_factory, [approve, edit] * 3)
    assert results.count("ok") == 1 and results.count(409) == 5, results
    with session_factory() as s:
        order = s.get(PurchaseOrder, oid)
        assert order.version == 2
        assert (order.status.value, order.notes) in {("Approved", None), ("Draft", "late edit")}
    assert _count(session_factory, PurchaseOrderEvent, PurchaseOrderEvent.purchase_order_id == oid) == 2


def test_cancel_racing_approve_lets_exactly_one_win(session_factory):
    oid = _draft(session_factory)
    approve = lambda s: service.approve(s, oid, PurchaseOrderAction(actor="a", expected_version=1))
    cancel = lambda s: service.cancel(s, oid, PurchaseOrderReasonAction(actor="c", expected_version=1, reason="x"))
    results = run_concurrently(session_factory, [approve, cancel, approve, cancel])
    assert results.count("ok") == 1 and results.count(409) == 3, results
    with session_factory() as s:
        assert s.get(PurchaseOrder, oid).status.value in {"Approved", "Cancelled"}
