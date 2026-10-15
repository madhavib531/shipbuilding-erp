"""PostgreSQL-only concurrency tests for inspection holds (see tests/pg_support.py)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.api.v1.materials import update_material
from app.models import (
    InspectionHold, Material, MaterialCategory, MaterialTransaction, PurchaseOrderLine, Supplier, TransactionType,
)
from app.models.facility import StorageLocation, Yard
from app.schemas.goods_receipt import GoodsReceiptCreate
from app.schemas.inspection import InspectionReject, InspectionRelease
from app.schemas.material import MaterialUpdate
from app.schemas.purchase_order import PurchaseOrderAction, PurchaseOrderCreate
from app.schemas.transfer import TransferCreate
from app.services import goods_receipt_service as receipts
from app.services import inspection_service as inspections
from app.services import purchase_order_service as orders
from app.services import transfer_service as transfers
from tests.pg_support import pg_session_factory, requires_pg, run_concurrently

pytestmark = requires_pg


def _seed(s):
    s.add_all([Supplier(id="S", name="Supplier"), MaterialCategory(id="C", name="Cat"),
               Yard(id="Y", name="Yard", location="North", capacity=1.0),
               Yard(id="Y2", name="Yard 2", location="South", capacity=1.0)])
    s.commit()
    s.add(StorageLocation(id="L", yard_id="Y", zone="A", aisle="1", capacity=100))
    s.commit()


@pytest.fixture
def session_factory():
    with pg_session_factory("qi_test", _seed) as factory:
        yield factory


def _held_batch(factory) -> int:
    """Approved order of 10, received entirely on hold into batch H. Returns the hold id."""
    with factory() as s:
        oid = orders.create_order(s, PurchaseOrderCreate(
            actor="t", supplier_id="S", expected_delivery_date=date.today() + timedelta(days=3),
            lines=[{"category_id": "C", "description": "Plate", "unit": "u", "ordered_quantity": 10,
                    "unit_price": "1", "currency": "EUR"}]), None)[0]
    with factory() as s:
        orders.approve(s, oid, PurchaseOrderAction(actor="t", expected_version=1))
    with factory() as s:
        line_id = s.scalar(select(PurchaseOrderLine.id).where(PurchaseOrderLine.purchase_order_id == oid))
        receipts.post_receipt(s, oid, GoodsReceiptCreate(actor="r", expected_version=2, yard_id="Y", location_id="L", lines=[
            {"purchase_order_line_id": line_id, "accepted_quantity": 10, "destination_material_id": "H",
             "batch": "LOT", "hold_for_inspection": True}]), "gr-1")
    with factory() as s:
        return s.scalar(select(InspectionHold.id))


def _stock(factory):
    with factory() as s:
        m = s.get(Material, "H")
        return m.quantity, m.available, m.reserved, inspections.held_quantity(s, "H")


def _release(hid, version, quantity):
    return lambda s: inspections.release(s, hid, InspectionRelease(actor="i", expected_version=version, quantity=quantity))


def _reject(hid, version, quantity):
    return lambda s: inspections.reject(s, hid, InspectionReject(
        actor="i", expected_version=version, quantity=quantity, reason="Failed", disposition="Scrap"))


def test_duplicate_releases_apply_once(session_factory):
    hid = _held_batch(session_factory)
    results = run_concurrently(session_factory, [_release(hid, 1, 4)] * 6)
    assert results.count("ok") == 1 and results.count(409) == 5, results
    assert _stock(session_factory) == (10, 4, 0, 6)


def test_release_racing_reject_lets_exactly_one_decide(session_factory):
    hid = _held_batch(session_factory)
    results = run_concurrently(session_factory, [_release(hid, 1, 10), _reject(hid, 1, 10)] * 3)
    assert results.count("ok") == 1 and results.count(409) == 5, results
    assert _stock(session_factory) in {(10, 10, 0, 0), (0, 0, 0, 0)}
    with session_factory() as s:
        line = s.scalar(select(PurchaseOrderLine))
        assert line.received_quantity + line.rejected_quantity == 10


def test_dispatch_racing_rejection_never_uses_held_stock(session_factory):
    hid = _held_batch(session_factory)
    with session_factory() as s:
        inspections.release(s, hid, InspectionRelease(actor="i", expected_version=1, quantity=6))
    ids = []
    for _ in range(3):  # 9 requested against 6 released; 4 more are held
        with session_factory() as s:
            tid = transfers.create_transfer(s, TransferCreate(actor="t", material_id="H", quantity=3, to_yard_id="Y2"), None)[0]
            transfers.approve(s, tid, "a", None)
            ids.append(tid)
    actions = [lambda s, t=t: transfers.dispatch(s, t, "d", None) for t in ids] + [_reject(hid, 2, 4)]
    results = run_concurrently(session_factory, actions)
    assert sorted(map(str, results[:3])) == ["409", "ok", "ok"] and results[3] == "ok", results
    assert _stock(session_factory) == (0, 0, 0, 0)
    with session_factory() as s:
        out = s.scalar(select(func.sum(MaterialTransaction.quantity)).where(
            MaterialTransaction.transaction_type == TransactionType.TRANSFER_OUT))
        assert out == 6


def test_inventory_edit_racing_release_cannot_free_held_stock(session_factory):
    hid = _held_batch(session_factory)
    edit = lambda s: update_material("H", MaterialUpdate(available=10), db=s)  # noqa: E731
    results = run_concurrently(session_factory, [edit, _release(hid, 1, 4), edit])
    assert results[1] == "ok" and results[0] == results[2] == 422, results
    assert _stock(session_factory) == (10, 4, 0, 6)
