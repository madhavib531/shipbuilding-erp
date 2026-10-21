"""GET /api/v1/materials/{id}/transactions: a batch's ledger history, newest first."""

from datetime import datetime, timedelta

from app.models.material import Material
from app.models.transaction import MaterialTransaction, TransactionType as T
from tests.test_goods_receipts import approved_order, receive, rline, world  # noqa: F401

URL = "/api/v1/materials/{}/transactions"


def _row(db, n, material_id, kind, minutes_ago):
    db.add(MaterialTransaction(id=f"TXN-{n}", material_id=material_id, transaction_type=kind, quantity=n,
                               unit="sheets", actor="t", reference_id=f"REF-{n}",
                               created_at=datetime(2026, 10, 1) - timedelta(minutes=minutes_ago)))


def test_unknown_material_is_404(client, world):
    assert client.get(URL.format("NOPE")).status_code == 404


def test_newest_first_with_pagination_and_only_this_batch(client, world, db):
    for n, kind, ago in [(1, T.RECEIPT, 30), (2, T.TRANSFER_OUT, 20), (3, T.ADJUSTMENT, 10)]:
        _row(db, n, "EXIST", kind, ago)
    _row(db, 9, "OTHER", T.RECEIPT, 0)
    db.commit()
    data = client.get(URL.format("EXIST")).json()["data"]
    assert data["total"] == 3
    assert [(t["id"], t["transaction_type"], t["quantity"], t["reference_id"]) for t in data["transactions"]] == [
        ("TXN-3", "Adjustment", 3, "REF-3"), ("TXN-2", "Transfer out", 2, "REF-2"), ("TXN-1", "Receipt", 1, "REF-1")]
    page = client.get(URL.format("EXIST"), params={"skip": 1, "limit": 1}).json()["data"]
    assert (page["total"], [t["id"] for t in page["transactions"]]) == (3, ["TXN-2"])


def test_identical_timestamps_are_ordered_by_id_and_page_without_gaps(client, world, db):
    same = datetime(2026, 10, 1)
    for n in (4, 7, 1, 9, 3):
        db.add(MaterialTransaction(id=f"TXN-{n}", material_id="EXIST", transaction_type=T.RECEIPT, quantity=n,
                                   unit="sheets", actor="t", created_at=same))
    db.commit()
    full = [t["id"] for t in client.get(URL.format("EXIST")).json()["data"]["transactions"]]
    assert full == ["TXN-9", "TXN-7", "TXN-4", "TXN-3", "TXN-1"]
    assert all([t["id"] for t in client.get(URL.format("EXIST")).json()["data"]["transactions"]] == full for _ in range(3))
    paged = [t["id"] for skip in range(0, 5, 2)
             for t in client.get(URL.format("EXIST"), params={"skip": skip, "limit": 2}).json()["data"]["transactions"]]
    assert paged == full


def test_history_of_a_held_and_released_receipt(client, world, db):
    po = approved_order(client)
    r = receive(client, po, [rline(po, destination_material_id="H-1", batch="LOT-H", hold_for_inspection=True)])
    hold = r.json()["data"]["receipt"]["lines"][0]["inspection_hold"]
    client.post(f"/api/v1/inspections/{hold['id']}/release", json={"actor": "QA", "expected_version": 1, "quantity": 10})
    rows = client.get(URL.format("H-1")).json()["data"]["transactions"]
    assert sorted((t["transaction_type"], t["quantity"], t["reference_id"][:3]) for t in rows) == [
        ("Inspection", 10, "QI-"), ("Receipt", 10, "GR-"), ("Release", 10, "QI-")]
    assert all(t["unit"] == "sheets" and t["actor"] for t in rows)
    assert db.get(Material, "H-1").available == 10


def test_limit_is_bounded(client, world):
    assert client.get(URL.format("EXIST"), params={"limit": 201}).status_code == 422
