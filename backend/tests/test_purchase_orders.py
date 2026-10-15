"""Purchase-order API: drafts (M2.2) and lifecycle (M2.3)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.facility import Yard
from app.models.material import Material, MaterialCategory
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus as S
from app.models.supplier import Supplier, SupplierStatusEnum as SS
from app.models.transaction import MaterialTransaction
from app.services.purchase_order_service import recalculate_status

BASE = "/api/v1/purchase-orders"
ACTOR = "Maya Chen"
TODAY = date.today()


@pytest.fixture
def refs(db):
    db.add_all([
        Supplier(id="SUP-A", name="Approved Co", status=SS.APPROVED),
        Supplier(id="SUP-C", name="Conditional Co", status=SS.CONDITIONAL),
        Supplier(id="SUP-P", name="Probation Co", status=SS.PROBATION),
        Supplier(id="SUP-I", name="Inactive Co", status=SS.INACTIVE),
        Supplier(id="SUP-B", name="Blocked Co", status=SS.BLOCKED),
        MaterialCategory(id="STEEL", name="Steel"),
        MaterialCategory(id="PIPE", name="Pipe"),
        Yard(id="Y1", name="Yard 1", location="North", capacity=1.0),
    ])
    db.commit()
    db.add(Material(id="M1", name="Plate", category_id="STEEL", batch="B1", unit="sheets",
                    quantity=50, available=40, reserved=5, yard_id="Y1"))
    db.commit()


def line(**over):
    data = {"category_id": "STEEL", "description": "AH36 plate 12mm", "unit": "sheets",
            "ordered_quantity": 10, "unit_price": "125.5000", "currency": "EUR"}
    data.update(over)
    return data


def create(client, key=None, **over):
    body = {"actor": ACTOR, "supplier_id": "SUP-A", "lines": [line()], "expected_delivery_date": str(TODAY + timedelta(days=10))}
    body.update(over)
    return client.post(BASE, json=body, headers={"Idempotency-Key": key} if key else {})


def created(client, **over):
    r = create(client, **over)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def get(client, oid):
    return client.get(f"{BASE}/{oid}").json()["data"]


def act(client, oid, action, version, **body):
    return client.post(f"{BASE}/{oid}/{action}", json={"actor": ACTOR, "expected_version": version, **body})


def approved(client, **over):
    po = created(client, **over)
    r = act(client, po["id"], "approve", po["version"])
    assert r.status_code == 200, r.text
    return r.json()["data"]


def stock_snapshot(db):
    db.expire_all()
    m = db.get(Material, "M1")
    return (m.quantity, m.available, m.reserved, m.version, db.query(MaterialTransaction).count())


def force_receipt(db, oid, received=0, rejected=0, status=None):
    """Simulates what a goods receipt (M3) will write, to test lifecycle rules that depend on it."""
    db.expire_all()
    ln = db.query(PurchaseOrderLine).filter_by(purchase_order_id=oid).order_by(PurchaseOrderLine.line_no).first()
    ln.received_quantity, ln.rejected_quantity = received, rejected
    po = db.get(PurchaseOrder, oid)
    if status:
        po.status = status
    po.version += 1
    db.commit()
    return po.version


class TestCreate:
    def test_create_draft(self, client, refs):
        po = created(client)
        assert (po["status"], po["version"], po["display_id"], po["created_by"]) == ("Draft", 1, f"PO-{po['id']:05d}", ACTOR)
        assert (po["supplier"]["id"], po["currency"], po["total_value"], po["outstanding_value"]) == ("SUP-A", "EUR", "1255.0000", "1255.0000")
        ln = po["lines"][0]
        assert (ln["line_no"], ln["ordered_quantity"], ln["outstanding_quantity"], ln["unit_price"], ln["line_total"]) == (1, 10, 10, "125.5000", "1255.0000")
        assert [(e["action"], e["to_status"], e["actor"], e["version"]) for e in po["events"]] == [("created", "Draft", ACTOR, 1)]
        assert po["approved_by"] is None and po["is_overdue"] is False

    def test_draft_without_lines_or_date_is_allowed(self, client, refs):
        po = created(client, lines=[], expected_delivery_date=None)
        assert (po["lines"], po["currency"], po["total_value"], po["expected_delivery_date"]) == ([], None, "0", None)

    def test_lines_are_numbered_in_order(self, client, refs):
        po = created(client, lines=[line(description="a"), line(description="b"), line(description="c")])
        assert [(l["line_no"], l["description"]) for l in po["lines"]] == [(1, "a"), (2, "b"), (3, "c")]

    @pytest.mark.parametrize("supplier", ["SUP-A", "SUP-C", "SUP-P"])
    def test_eligible_suppliers(self, client, refs, supplier):
        assert create(client, supplier_id=supplier).status_code == 201

    @pytest.mark.parametrize("supplier, fragment", [("SUP-I", "Inactive"), ("SUP-B", "Blocked"), ("NOPE", "does not exist")])
    def test_ineligible_or_unknown_supplier_rejected(self, client, refs, db, supplier, fragment):
        r = create(client, supplier_id=supplier)
        assert r.status_code == 422 and fragment in r.json()["detail"]
        assert db.query(PurchaseOrder).count() == 0

    @pytest.mark.parametrize("price", ["1.23456", "-0.0001", "12345678901", "abc"])
    def test_invalid_prices_rejected_before_persistence(self, client, refs, db, price):
        assert create(client, lines=[line(unit_price=price)]).status_code == 422
        assert db.query(PurchaseOrder).count() == 0

    @pytest.mark.parametrize("price, stored", [("0", "0.0000"), ("0.0001", "0.0001"), ("9999999999.9999", "9999999999.9999"), (12.5, "12.5000")])
    def test_valid_prices_keep_four_decimals(self, client, refs, price, stored):
        assert created(client, lines=[line(unit_price=price)])["lines"][0]["unit_price"] == stored

    @pytest.mark.parametrize("currency", ["eur", "EU", "EURO", "E1R", "€UR", " EUR"])
    def test_invalid_currency_rejected(self, client, refs, currency):
        assert create(client, lines=[line(currency=currency)]).status_code == 422

    def test_mixed_currencies_rejected(self, client, refs):
        r = create(client, lines=[line(), line(description="other", currency="USD")])
        assert r.status_code == 422 and "same currency" in r.json()["detail"]

    @pytest.mark.parametrize("second", [
        {"description": "ah36   PLATE 12mm"},
        {"description": " AH36 plate 12mm "},
    ])
    def test_duplicate_lines_rejected(self, client, refs, second):
        r = create(client, lines=[line(), line(**second)])
        assert r.status_code == 422 and "Lines 1 and 2" in r.json()["detail"]

    @pytest.mark.parametrize("second", [
        {"supplier_part_number": "NMS-12"},
        {"unit": "plates"},
        {"category_id": "PIPE"},
    ])
    def test_lines_differing_in_identity_are_allowed(self, client, refs, second):
        assert create(client, lines=[line(), line(**second)]).status_code == 201

    @pytest.mark.parametrize("over", [
        {"ordered_quantity": 0}, {"ordered_quantity": -1}, {"ordered_quantity": 1.5},
        {"description": "  "}, {"unit": ""}, {"category_id": "NOPE"},
    ])
    def test_invalid_line_rejected(self, client, refs, over):
        assert create(client, lines=[line(**over)]).status_code == 422

    def test_missing_actor_rejected(self, client, refs):
        assert create(client, actor="  ").status_code == 422

    def test_idempotent_replay_returns_original(self, client, refs, db):
        a = create(client, key="k-1")
        b = create(client, key="k-1")
        assert (a.status_code, b.status_code) == (201, 200)
        assert a.json()["data"]["id"] == b.json()["data"]["id"]
        assert db.query(PurchaseOrder).count() == 1

    def test_key_reused_with_different_body_conflicts(self, client, refs, db):
        create(client, key="k-1")
        r = create(client, key="k-1", notes="different")
        assert r.status_code == 409
        assert db.query(PurchaseOrder).count() == 1


class TestRead:
    def test_get_404(self, client, refs):
        r = client.get(f"{BASE}/999")
        assert r.status_code == 404 and "PO-00999" in r.json()["detail"]

    def test_list_filters_search_and_pagination(self, client, refs):
        a = created(client, lines=[line(description="Cu-Ni pipe 80mm", category_id="PIPE", supplier_part_number="BL-80")])
        b = created(client, supplier_id="SUP-C")
        c = created(client, lines=[])
        page = client.get(BASE).json()["data"]
        assert (page["total"], [p["id"] for p in page["purchase_orders"]]) == (3, [c["id"], b["id"], a["id"]])
        q = lambda **p: [o["id"] for o in client.get(BASE, params=p).json()["data"]["purchase_orders"]]
        assert q(supplier_id="SUP-C") == [b["id"]]
        assert q(search=a["display_id"]) == [a["id"]]
        assert a["id"] in q(search=str(a["id"])), "a bare number also matches descriptions such as '12mm'"
        assert q(search="conditional") == [b["id"]]
        assert q(search="cu-ni") == [a["id"]]
        assert q(search="bl-80") == [a["id"]]
        assert q(status="Draft", limit=2, skip=1) == [b["id"], a["id"]]
        assert q(status="Approved") == []

    def test_invalid_status_filter_rejected(self, client, refs):
        assert client.get(BASE, params={"status": "Open"}).status_code == 422


class TestDraftEdit:
    def test_edit_header_fields(self, client, refs):
        po = created(client)
        new_date = str(TODAY + timedelta(days=30))
        r = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "supplier_id": "SUP-P",
                                                     "expected_delivery_date": new_date, "notes": "Rush"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert (d["supplier"]["id"], d["expected_delivery_date"], d["notes"], d["version"]) == ("SUP-P", new_date, "Rush", 2)
        assert d["events"][-1]["action"] == "edited"
        assert sorted(d["events"][-1]["changes"]["fields"]) == ["expected_delivery_date", "notes", "supplier_id"]

    def test_clear_optional_fields(self, client, refs):
        po = created(client, notes="x")
        d = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1,
                                                    "expected_delivery_date": None, "notes": ""}).json()["data"]
        assert (d["expected_delivery_date"], d["notes"]) == (None, None)

    def test_replace_lines_deletes_removed_lines(self, client, refs, db):
        po = created(client, lines=[line(description="a"), line(description="b")])
        r = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1,
                                                     "lines": [line(description="c", ordered_quantity=3)]})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert [(l["line_no"], l["description"]) for l in d["lines"]] == [(1, "c")]
        # SQLite may reuse a deleted rowid, so check the old rows by content rather than by ID.
        db.expire_all()
        assert [(l.description, l.ordered_quantity) for l in db.query(PurchaseOrderLine).all()] == [("c", 3)]
        assert d["events"][-1]["changes"]["lines"] == {"before": 2, "after": 1}

    def test_remove_all_lines_in_draft(self, client, refs):
        po = created(client)
        d = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "lines": []}).json()["data"]
        assert d["lines"] == [] and d["version"] == 2

    def test_no_op_edit_changes_nothing(self, client, refs):
        po = created(client, notes="same")
        d = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "notes": "same"}).json()["data"]
        assert d["version"] == 1 and len(d["events"]) == 1

    def test_stale_version_rejected_and_nothing_changes(self, client, refs):
        po = created(client)
        client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "notes": "first"})
        r = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "notes": "second"})
        assert r.status_code == 409 and "Reload" in r.json()["detail"]
        d = get(client, po["id"])
        assert (d["notes"], d["version"]) == ("first", 2)

    def test_invalid_edit_rolls_back_entirely(self, client, refs):
        po = created(client)
        r = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "notes": "changed",
                                                     "lines": [line(), line(currency="USD", description="b")]})
        assert r.status_code == 422
        d = get(client, po["id"])
        assert (d["notes"], d["version"], len(d["lines"])) == (None, 1, 1)

    @pytest.mark.parametrize("over, code", [
        ({"supplier_id": "SUP-B"}, 422), ({"supplier_id": None}, 422), ({"lines": None}, 422),
        ({"lines": [line(unit_price="1.00001")]}, 422),
    ])
    def test_invalid_edits(self, client, refs, over, code):
        po = created(client)
        assert client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, **over}).status_code == code

    def test_expected_version_required(self, client, refs):
        po = created(client)
        assert client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "notes": "x"}).status_code == 422

    def test_edit_unknown_order_404(self, client, refs):
        assert client.patch(f"{BASE}/999", json={"actor": ACTOR, "expected_version": 1, "notes": "x"}).status_code == 404


class TestLifecycle:
    def test_approve(self, client, refs):
        po = created(client)
        d = act(client, po["id"], "approve", 1, reason="Budget ok").json()["data"]
        assert (d["status"], d["approved_by"], d["version"]) == ("Approved", ACTOR, 2)
        assert d["approved_at"]
        assert (d["events"][-1]["action"], d["events"][-1]["from_status"], d["events"][-1]["reason"]) == ("approved", "Draft", "Budget ok")

    @pytest.mark.parametrize("over, fragment", [
        ({"lines": []}, "no lines"),
        ({"expected_delivery_date": None}, "no expected delivery date"),
    ])
    def test_approval_preconditions(self, client, refs, over, fragment):
        po = created(client, **over)
        r = act(client, po["id"], "approve", 1)
        assert r.status_code == 422 and fragment in r.json()["detail"]
        assert get(client, po["id"])["status"] == "Draft"

    def test_supplier_blocked_after_drafting_blocks_approval(self, client, refs):
        po = created(client)
        assert client.patch("/api/v1/suppliers/SUP-A", json={"status": "Blocked"}).status_code == 200
        r = act(client, po["id"], "approve", 1)
        assert r.status_code == 422 and "Blocked" in r.json()["detail"]

    def test_approved_order_stays_approved_if_supplier_is_blocked_later(self, client, refs):
        po = approved(client)
        client.patch("/api/v1/suppliers/SUP-A", json={"status": "Blocked"})
        assert get(client, po["id"])["status"] == "Approved"

    def test_approved_order_cannot_be_edited(self, client, refs):
        po = approved(client)
        r = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": po["version"], "notes": "x"})
        assert r.status_code == 409 and "cannot be edited" in r.json()["detail"]

    def test_reopen_clears_approval_and_allows_edit(self, client, refs):
        po = approved(client)
        assert act(client, po["id"], "reopen", po["version"]).status_code == 422, "reason required"
        d = act(client, po["id"], "reopen", po["version"], reason="Price changed").json()["data"]
        assert (d["status"], d["approved_by"], d["approved_at"], d["version"]) == ("Draft", None, None, 3)
        assert d["events"][-1]["action"] == "reopened"
        edited = client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 3,
                                                          "lines": [line(unit_price="130")]})
        assert edited.status_code == 200
        assert act(client, po["id"], "approve", 4).json()["data"]["status"] == "Approved"

    @pytest.mark.parametrize("received, rejected", [(0, 2), (3, 0)])
    def test_reopen_refused_after_any_receipt(self, client, refs, db, received, rejected):
        po = approved(client)
        status = S.PARTIALLY_RECEIVED if received else None
        v = force_receipt(db, po["id"], received=received, rejected=rejected, status=status)
        assert act(client, po["id"], "reopen", v, reason="x").status_code == 409

    @pytest.mark.parametrize("make", ["draft", "approved"])
    def test_cancel_before_receipt(self, client, refs, make):
        po = created(client) if make == "draft" else approved(client)
        assert act(client, po["id"], "cancel", po["version"]).status_code == 422, "reason required"
        d = act(client, po["id"], "cancel", po["version"], reason="Not needed").json()["data"]
        assert d["status"] == "Cancelled"
        assert [(l["cancelled_quantity"], l["outstanding_quantity"]) for l in d["lines"]] == [(10, 0)]

    def test_cancel_after_rejected_only_delivery(self, client, refs, db):
        po = approved(client)
        v = force_receipt(db, po["id"], rejected=4)
        d = act(client, po["id"], "cancel", v, reason="Supplier cannot redeliver").json()["data"]
        assert (d["status"], d["lines"][0]["cancelled_quantity"], d["lines"][0]["rejected_quantity"]) == ("Cancelled", 10, 4)

    def test_cancel_refused_once_goods_were_accepted(self, client, refs, db):
        po = approved(client)
        v = force_receipt(db, po["id"], received=4, status=S.PARTIALLY_RECEIVED)
        assert act(client, po["id"], "cancel", v, reason="x").status_code == 409

    def test_close_cancels_only_the_outstanding_remainder(self, client, refs, db):
        po = approved(client, lines=[line(), line(description="b", ordered_quantity=5)])
        v = force_receipt(db, po["id"], received=4, rejected=1, status=S.PARTIALLY_RECEIVED)
        assert act(client, po["id"], "close", v).status_code == 422, "reason required"
        d = act(client, po["id"], "close", v, reason="Supplier short").json()["data"]
        assert d["status"] == "Closed"
        assert [(l["received_quantity"], l["rejected_quantity"], l["cancelled_quantity"], l["outstanding_quantity"])
                for l in d["lines"]] == [(4, 1, 6, 0), (0, 0, 5, 0)]
        assert d["events"][-1]["changes"] == {"cancelled_by_line": {"1": 6, "2": 5}}

    @pytest.mark.parametrize("setup, action", [
        ("draft", "reopen"), ("draft", "close"),
        ("approved", "approve"), ("approved", "close"),
        ("cancelled", "approve"), ("cancelled", "cancel"), ("cancelled", "reopen"),
        ("closed", "close"), ("closed", "cancel"), ("closed", "reopen"),
        ("received", "cancel"), ("received", "close"), ("received", "approve"),
    ])
    def test_forbidden_transitions_conflict_and_change_nothing(self, client, refs, db, setup, action):
        po = created(client) if setup == "draft" else approved(client)
        version = po["version"]
        if setup == "cancelled":
            version = act(client, po["id"], "cancel", version, reason="x").json()["data"]["version"]
        elif setup == "closed":
            v = force_receipt(db, po["id"], received=4, status=S.PARTIALLY_RECEIVED)
            version = act(client, po["id"], "close", v, reason="x").json()["data"]["version"]
        elif setup == "received":
            version = force_receipt(db, po["id"], received=10, status=S.RECEIVED)
        before = get(client, po["id"])
        r = act(client, po["id"], action, version, reason="x")
        assert r.status_code == 409, r.text
        assert get(client, po["id"]) == before

    @pytest.mark.parametrize("action", ["approve", "reopen", "cancel", "close"])
    def test_stale_version_rejected(self, client, refs, action):
        po = created(client)
        client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "notes": "bump"})
        r = act(client, po["id"], action, 1, reason="x")
        assert r.status_code == 409 and "version" in r.json()["detail"]

    def test_unknown_order_404(self, client, refs):
        assert act(client, 999, "approve", 1).status_code == 404

    def test_no_purchase_order_operation_touches_stock_or_ledger(self, client, refs, db):
        before = stock_snapshot(db)
        po = created(client)
        client.patch(f"{BASE}/{po['id']}", json={"actor": ACTOR, "expected_version": 1, "notes": "x"})
        act(client, po["id"], "approve", 2)
        act(client, po["id"], "reopen", 3, reason="x")
        act(client, po["id"], "approve", 4)
        act(client, po["id"], "cancel", 5, reason="x")
        other = approved(client, lines=[line(description="z")])
        v = force_receipt(db, other["id"], received=2, status=S.PARTIALLY_RECEIVED)
        act(client, other["id"], "close", v, reason="x")
        client.get(f"{BASE}/summary")
        assert stock_snapshot(db) == before


class TestSummary:
    def test_empty(self, client, refs):
        s = client.get(f"{BASE}/summary").json()["data"]
        assert s == {"by_status": {"Draft": 0, "Approved": 0, "Partially received": 0, "Received": 0, "Cancelled": 0, "Closed": 0},
                     "open": 0, "overdue": 0, "due_this_week": 0, "partially_received": 0, "open_value": []}

    def test_counts_and_open_value_by_currency(self, client, refs, db):
        created(client)                                                                    # draft: not open
        approved(client, expected_delivery_date=str(TODAY - timedelta(days=1)))            # overdue
        approved(client, expected_delivery_date=str(TODAY + timedelta(days=3)),             # due this week
                 lines=[line(unit_price="0.3333", ordered_quantity=3, currency="USD")])
        partial = approved(client, expected_delivery_date=str(TODAY + timedelta(days=20)))
        force_receipt(db, partial["id"], received=4, rejected=2, status=S.PARTIALLY_RECEIVED)
        cancelled = approved(client)
        act(client, cancelled["id"], "cancel", cancelled["version"], reason="x")
        s = client.get(f"{BASE}/summary").json()["data"]
        assert s["by_status"] == {"Draft": 1, "Approved": 2, "Partially received": 1, "Received": 0, "Cancelled": 1, "Closed": 0}
        assert (s["open"], s["overdue"], s["due_this_week"], s["partially_received"]) == (3, 1, 1, 1)
        # EUR: 10 x 125.5 (overdue order) + 6 outstanding x 125.5 (partial order); USD: 3 x 0.3333
        assert s["open_value"] == [{"currency": "EUR", "amount": "2008.0000"}, {"currency": "USD", "amount": "0.9999"}]

    def test_overdue_filter_matches_summary(self, client, refs):
        late = approved(client, expected_delivery_date=str(TODAY - timedelta(days=2)))
        approved(client)
        listed = client.get(BASE, params={"overdue": "true"}).json()["data"]
        assert [o["id"] for o in listed["purchase_orders"]] == [late["id"]]
        assert listed["purchase_orders"][0]["is_overdue"] is True
        assert client.get(f"{BASE}/summary").json()["data"]["overdue"] == listed["total"] == 1


class TestStatusRecalculation:
    def _lines(self, *rows):
        return [PurchaseOrderLine(ordered_quantity=o, received_quantity=r, rejected_quantity=j, cancelled_quantity=c,
                                  unit_price=Decimal("1")) for o, r, j, c in rows]

    @pytest.mark.parametrize("rows, expected", [
        ([(10, 0, 4, 0)], S.APPROVED),                       # rejected-only delivery is not fulfilment
        ([(10, 3, 0, 0)], S.PARTIALLY_RECEIVED),
        ([(10, 10, 2, 0)], S.RECEIVED),
        ([(10, 10, 0, 0), (5, 0, 5, 0)], S.PARTIALLY_RECEIVED),  # one line full, other only rejected
        ([(10, 10, 0, 0), (5, 2, 0, 3)], S.RECEIVED),       # remainder cancelled
    ])
    def test_status_after_receipt(self, rows, expected):
        assert recalculate_status(self._lines(*rows)) == expected
