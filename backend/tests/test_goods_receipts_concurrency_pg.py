"""PostgreSQL-only concurrency tests for goods receipts (see tests/pg_support.py)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    GoodsReceipt, Material, MaterialCategory, MaterialTransaction, PurchaseOrder, PurchaseOrderLine, Supplier,
)
from app.models.facility import StorageLocation, Yard
from app.schemas.goods_receipt import GoodsReceiptCreate
from app.schemas.purchase_order import PurchaseOrderAction, PurchaseOrderCreate
from app.services import goods_receipt_service as receipts
from app.services import purchase_order_service as orders
from tests.pg_support import pg_session_factory, requires_pg, run_concurrently

pytestmark = requires_pg


def _seed(s):
    s.add_all([Supplier(id="S", name="Supplier"), MaterialCategory(id="C", name="Cat"),
               Yard(id="Y", name="Yard", location="North", capacity=1.0)])
    s.commit()
    s.add(StorageLocation(id="L", yard_id="Y", zone="A", aisle="1", capacity=100))
    s.add(Material(id="EXIST", name="Plate", category_id="C", batch="B1", unit="u",
                   quantity=5, available=5, reserved=0, yard_id="Y", location_id="L"))
    s.commit()


@pytest.fixture
def session_factory():
    with pg_session_factory("gr_test", _seed) as factory:
        yield factory


def _approved_order(factory) -> tuple[int, int]:
    """Returns (order id, line id) for an approved order of 10 units."""
    with factory() as s:
        oid = orders.create_order(s, PurchaseOrderCreate(
            actor="t", supplier_id="S", expected_delivery_date=date.today() + timedelta(days=3),
            lines=[{"category_id": "C", "description": "Plate", "unit": "u", "ordered_quantity": 10,
                    "unit_price": "1", "currency": "EUR"}]), None)[0]
    with factory() as s:
        orders.approve(s, oid, PurchaseOrderAction(actor="t", expected_version=1))
    with factory() as s:
        return oid, s.scalar(select(PurchaseOrderLine.id).where(PurchaseOrderLine.purchase_order_id == oid))


def _receipt(line_id, quantity, destination="EXIST", batch=None):
    return GoodsReceiptCreate(actor="r", expected_version=2, yard_id="Y", location_id="L", lines=[
        {"purchase_order_line_id": line_id, "accepted_quantity": quantity,
         "destination_material_id": destination, "batch": batch}])


def _state(factory, oid):
    with factory() as s:
        return (s.get(Material, "EXIST").quantity,
                s.scalar(select(func.sum(PurchaseOrderLine.received_quantity)).where(PurchaseOrderLine.purchase_order_id == oid)),
                s.scalar(select(func.count()).select_from(GoodsReceipt)),
                s.scalar(select(func.count()).select_from(MaterialTransaction)),
                s.get(PurchaseOrder, oid).version)


def test_same_idempotency_key_adds_stock_once(session_factory):
    oid, line_id = _approved_order(session_factory)
    body = _receipt(line_id, 4)
    results = run_concurrently(session_factory, [lambda s: receipts.post_receipt(s, oid, body, "gr-k")] * 6)
    assert all(isinstance(r, tuple) for r in results), results
    assert len({r[1][0] for r in results}) == 1 and sum(r[1][1] for r in results) == 1, results
    assert _state(session_factory, oid) == (9, 4, 1, 1, 3)


def test_competing_receipts_cannot_over_receive(session_factory):
    oid, line_id = _approved_order(session_factory)
    actions = [lambda s, k=k: receipts.post_receipt(s, oid, _receipt(line_id, 10), f"gr-{k}") for k in range(6)]
    results = run_concurrently(session_factory, actions)
    assert sum(isinstance(r, tuple) for r in results) == 1 and results.count(409) == 5, results
    assert _state(session_factory, oid) == (15, 10, 1, 1, 3)
    with session_factory() as s:
        assert s.get(PurchaseOrder, oid).status.value == "Received"


def test_competing_new_batch_creation_creates_one_batch(session_factory):
    oid, line_id = _approved_order(session_factory)
    actions = [lambda s, k=k: receipts.post_receipt(s, oid, _receipt(line_id, 3, "NEW", "LOT"), f"gr-{k}") for k in range(4)]
    results = run_concurrently(session_factory, actions)
    assert sum(isinstance(r, tuple) for r in results) == 1 and results.count(409) == 3, results
    with session_factory() as s:
        assert s.get(Material, "NEW").quantity == 3
