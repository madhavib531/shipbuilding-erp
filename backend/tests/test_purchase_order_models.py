"""Purchase-order model and database-constraint tests (no API yet)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.material import MaterialCategory
from app.models.purchase_order import PurchaseOrder, PurchaseOrderEvent, PurchaseOrderLine, PurchaseOrderStatus as S
from app.models.supplier import Supplier


@pytest.fixture
def refs(db):
    db.add_all([Supplier(id="SUP", name="Supplier"), MaterialCategory(id="CAT", name="Category")])
    db.commit()


def order(db, **over):
    values = dict(supplier_id="SUP", created_by="Maya Chen")
    values.update(over)
    po = PurchaseOrder(**values)
    db.add(po)
    db.commit()
    return po


def line(db, po, **over):
    values = dict(purchase_order_id=po.id, line_no=1, category_id="CAT", description="AH36 plate 12mm",
                  unit="sheets", ordered_quantity=10, unit_price=Decimal("125.5000"), currency="EUR")
    values.update(over)
    ln = PurchaseOrderLine(**values)
    db.add(ln)
    db.commit()
    return ln


def rejects(db, obj):
    db.add(obj)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


class TestDefaultsAndRelationships:
    def test_new_order_defaults(self, db, refs):
        po = order(db)
        assert (po.status, po.version, po.approved_by, po.approved_at, po.expected_delivery_date) == (S.DRAFT, 1, None, None, None)
        assert po.created_at and po.updated_at
        assert po.display_id == f"PO-{po.id:05d}"

    def test_ids_are_generated_and_increase(self, db, refs):
        a, b = order(db), order(db)
        assert b.id > a.id
        assert (a.display_id, b.display_id) == (f"PO-{a.id:05d}", f"PO-{b.id:05d}")

    def test_line_defaults_and_outstanding(self, db, refs):
        ln = line(db, order(db))
        assert (ln.received_quantity, ln.rejected_quantity, ln.cancelled_quantity) == (0, 0, 0)
        assert ln.outstanding_quantity == 10

    def test_rejected_quantity_stays_outstanding(self, db, refs):
        ln = line(db, order(db), ordered_quantity=10, received_quantity=4, rejected_quantity=3, cancelled_quantity=1)
        assert ln.outstanding_quantity == 5

    def test_lines_ordered_by_line_no_and_events_by_id(self, db, refs):
        po = order(db)
        line(db, po, line_no=3, description="c")
        line(db, po, line_no=1, description="a")
        line(db, po, line_no=2, description="b")
        for action in ("created", "edited", "approved"):
            db.add(PurchaseOrderEvent(purchase_order_id=po.id, action=action, to_status="Draft", actor="t", version=1))
        db.commit()
        db.refresh(po)
        assert [l.line_no for l in po.lines] == [1, 2, 3]
        assert [e.action for e in po.events] == ["created", "edited", "approved"]
        assert po.supplier.name == "Supplier" and po.lines[0].category.name == "Category"

    def test_line_ids_are_independent_of_line_numbers(self, db, refs):
        a = line(db, order(db), line_no=1)
        b = line(db, order(db), line_no=1)
        assert a.id != b.id

    def test_event_changes_round_trip_as_json(self, db, refs):
        po = order(db)
        changes = {"fields": ["expected_delivery_date"], "lines": {"before": 1, "after": 2}}
        db.add(PurchaseOrderEvent(purchase_order_id=po.id, action="edited", from_status="Draft", to_status="Draft",
                                  actor="t", version=2, changes=changes))
        db.commit()
        db.expire_all()
        assert db.get(PurchaseOrder, po.id).events[0].changes == changes


class TestPrices:
    @pytest.mark.parametrize("price", ["0", "0.0001", "125.5", "1234567890.1234"])
    def test_unit_price_keeps_four_decimal_places(self, db, refs, price):
        ln = line(db, order(db), unit_price=Decimal(price))
        db.expire_all()
        stored = db.get(PurchaseOrderLine, ln.id).unit_price
        assert isinstance(stored, Decimal)
        assert stored == Decimal(price)

    def test_zero_price_is_allowed(self, db, refs):
        assert line(db, order(db), unit_price=Decimal("0")).unit_price == 0


class TestLineConstraints:
    @pytest.mark.parametrize("over", [
        {"ordered_quantity": 0},
        {"ordered_quantity": -1},
        {"received_quantity": -1},
        {"rejected_quantity": -1},
        {"cancelled_quantity": -1},
        {"ordered_quantity": 10, "received_quantity": 7, "cancelled_quantity": 4},
        {"ordered_quantity": 10, "received_quantity": 11},
        {"unit_price": Decimal("-0.0001")},
        {"currency": "EU"},
        {"currency": "EURO"},
        {"currency": "eur"},
        {"line_no": 0},
    ])
    def test_invalid_line_rejected(self, db, refs, over):
        po = order(db)
        values = dict(purchase_order_id=po.id, line_no=1, category_id="CAT", description="x", unit="u",
                      ordered_quantity=10, unit_price=Decimal("1"), currency="EUR")
        values.update(over)
        rejects(db, PurchaseOrderLine(**values))

    def test_fully_received_or_cancelled_line_is_allowed(self, db, refs):
        po = order(db)
        assert line(db, po, line_no=1, received_quantity=6, cancelled_quantity=4).outstanding_quantity == 0
        assert line(db, po, line_no=2, received_quantity=10).outstanding_quantity == 0

    def test_rejected_does_not_count_toward_the_ordered_limit(self, db, refs):
        ln = line(db, order(db), ordered_quantity=10, received_quantity=10, rejected_quantity=25)
        assert ln.outstanding_quantity == 0

    def test_line_number_unique_within_an_order(self, db, refs):
        po = order(db)
        line(db, po, line_no=1)
        rejects(db, PurchaseOrderLine(purchase_order_id=po.id, line_no=1, category_id="CAT", description="dup",
                                      unit="u", ordered_quantity=1, unit_price=Decimal("1"), currency="EUR"))


class TestOrderConstraints:
    def test_idempotency_key_is_unique(self, db, refs):
        order(db, idempotency_key="k-1")
        rejects(db, PurchaseOrder(supplier_id="SUP", created_by="t", idempotency_key="k-1"))

    def test_orders_without_idempotency_key_are_allowed(self, db, refs):
        order(db)
        order(db)

    def test_version_must_be_positive(self, db, refs):
        rejects(db, PurchaseOrder(supplier_id="SUP", created_by="t", version=0))

    @pytest.mark.parametrize("status", [S.APPROVED, S.PARTIALLY_RECEIVED, S.RECEIVED, S.CLOSED])
    @pytest.mark.parametrize("missing", ["approved_by", "approved_at", "expected_delivery_date"])
    def test_approved_states_need_approval_details_and_delivery_date(self, db, refs, status, missing):
        values = dict(supplier_id="SUP", created_by="t", status=status, approved_by="Maya Chen",
                      approved_at=datetime(2026, 10, 15, 9, 0), expected_delivery_date=date(2026, 11, 1))
        values[missing] = None
        rejects(db, PurchaseOrder(**values))

    @pytest.mark.parametrize("status", [S.APPROVED, S.PARTIALLY_RECEIVED, S.RECEIVED, S.CLOSED])
    def test_approved_states_with_complete_details_are_allowed(self, db, refs, status):
        po = order(db, status=status, approved_by="Maya Chen", approved_at=datetime(2026, 10, 15, 9, 0),
                   expected_delivery_date=date(2026, 11, 1))
        assert po.status == status

    @pytest.mark.parametrize("status", [S.DRAFT, S.CANCELLED])
    def test_draft_and_cancelled_do_not_need_approval_details(self, db, refs, status):
        assert order(db, status=status).status == status
