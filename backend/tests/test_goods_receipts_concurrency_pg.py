"""PostgreSQL-only concurrency tests for goods receipts (see tests/pg_support.py)."""

import threading
import time
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.models import (
    GoodsReceipt, GoodsReceiptLine, Material, MaterialCategory, MaterialTransaction, PurchaseOrder,
    PurchaseOrderLine, Supplier,
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


def _post_all_behind_order_lock(factory, oid, bodies, key):
    """Posts every body with the same key while another session holds the order's row lock, and releases
    that lock only once every post is waiting on it, so each has already passed the pre-lock replay
    lookup. This forces the interleaving in which duplicates meet the original's version change."""
    blocker = factory()
    blocker.execute(select(PurchaseOrder).where(PurchaseOrder.id == oid).with_for_update())
    results = [None] * len(bodies)

    def worker(i, body):
        s = factory()
        try:
            results[i] = ("ok", *receipts.post_receipt(s, oid, body, key))
        except HTTPException as exc:
            s.rollback()
            results[i] = (exc.status_code, exc.detail)
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i, b)) for i, b in enumerate(bodies)]
    for t in threads:
        t.start()
    try:
        deadline = time.monotonic() + 30
        with factory() as probe:
            while probe.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                    "AND wait_event_type = 'Lock'")) < len(bodies):
                probe.rollback()  # activity statistics are snapshotted per transaction
                if time.monotonic() > deadline:
                    pytest.fail("posts never queued behind the order lock")
                time.sleep(0.02)
    finally:
        blocker.rollback()
        blocker.close()
    for t in threads:
        t.join(timeout=60)
    return results


def test_duplicates_queued_behind_the_original_replay_it(session_factory):
    oid, line_id = _approved_order(session_factory)
    body = _receipt(line_id, 4)
    results = _post_all_behind_order_lock(session_factory, oid, [body] * 6, "gr-q")
    assert all(r[0] == "ok" for r in results), results
    assert len({r[1] for r in results}) == 1 and [r[2] for r in results].count(True) == 1, results
    assert _state(session_factory, oid) == (9, 4, 1, 1, 3)
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(GoodsReceiptLine)) == 1


def test_queued_key_reuse_with_different_payload_still_conflicts(session_factory):
    oid, line_id = _approved_order(session_factory)
    bodies = [_receipt(line_id, 4)] + [_receipt(line_id, 3)] * 3
    results = _post_all_behind_order_lock(session_factory, oid, bodies, "gr-mixed")
    created = [i for i, r in enumerate(results) if r[0] == "ok" and r[2]]
    assert len(created) == 1, results
    winner = bodies[created[0]]
    for body, r in zip(bodies, results):
        if body == winner:
            assert r[0] == "ok" and r[1] == results[created[0]][1], results
        else:
            assert r == (409, "This Idempotency-Key was already used for a different goods receipt"), results
    quantity = winner.lines[0].accepted_quantity
    assert _state(session_factory, oid) == (5 + quantity, quantity, 1, 1, 3)


def test_stale_request_with_new_key_still_conflicts(session_factory):
    oid, line_id = _approved_order(session_factory)
    with session_factory() as s:
        receipts.post_receipt(s, oid, _receipt(line_id, 4), "gr-first")
    with session_factory() as s:
        with pytest.raises(HTTPException) as caught:
            receipts.post_receipt(s, oid, _receipt(line_id, 2), "gr-other")  # still expects version 2
        s.rollback()
    assert caught.value.status_code == 409 and "changed by another update" in caught.value.detail
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
