"""PostgreSQL-only: the audit feed's UNION ALL, casts and filters, and stock adjustments, on PostgreSQL itself
(see tests/pg_support.py; runs in a throwaway schema of the dedicated test database)."""

from datetime import date, timedelta

import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from app.api.v1.materials import update_material
from app.models import Material, MaterialTransaction
from app.schemas.inspection import InspectionRelease
from app.schemas.material import MaterialUpdate
from app.schemas.transfer import TransferCreate
from app.services import audit_service, inspection_service, transfer_service
from app.services.audit_service import AuditSource
from tests.pg_support import pg_session_factory, requires_pg
from tests.test_inspections_concurrency_pg import _held_batch, _seed

OLA = SimpleNamespace(display_name="Ola")  # the signed-in user the API handlers record

pytestmark = requires_pg


@pytest.fixture
def factory():
    with pg_session_factory("audit_test", _seed) as f:
        hid = _held_batch(f)  # PO-00001 created/approved/received; batch H on hold; RECEIPT + INSPECTION rows
        with f() as s:
            inspection_service.release(s, hid, InspectionRelease(actor="Nadia", expected_version=1, quantity=6))
        with f() as s:
            tid = transfer_service.create_transfer(s, TransferCreate(actor="Leo", material_id="H", quantity=2, to_yard_id="Y2"), None)[0]
            transfer_service.approve(s, tid, "Maya", None)
            transfer_service.dispatch(s, tid, "Maya", None)
        yield f


def events(f, **kw):
    args = {"sources": [], "search": "", "actor": "", "date_from": None, "date_to": None, "skip": 0, "limit": 200, **kw}
    with f() as s:
        return audit_service.list_events(s, **args)


def test_feed_unions_all_sources_on_postgres(factory):
    total, rows = events(factory)
    assert {r["source"] for r in rows} == {"stock", "transfer", "purchase_order", "inspection"}
    assert total == len(rows)
    assert {r["action"] for r in rows if r["source"] == "stock"} >= {"Receipt", "Inspection", "Release", "Transfer out"}
    assert all(isinstance(r["created_at"], str) for r in rows)


def test_filters_search_ordering_and_pagination_on_postgres(factory):
    total, full = events(factory)
    assert [r["key"] for r in events(factory)[1]] == [r["key"] for r in full], "ordering must be deterministic"
    paged = [r["key"] for skip in range(0, total, 3) for r in events(factory, skip=skip, limit=3)[1]]
    assert paged == [r["key"] for r in full]
    assert {r["source"] for r in events(factory, sources=[AuditSource.INSPECTION])[1]} == {"inspection"}
    assert {r["record"] for r in events(factory, search="PO-00001")[1]} == {"PO-00001", "H"}
    assert {r["record"] for r in events(factory, search="tr-1")[1]} == {"TR-00001", "H"}
    assert {r["source"] for r in events(factory, search="qi-00001")[1]} == {"inspection", "stock"}
    today = date.today()
    assert events(factory, date_from=today, date_to=today)[0] == total
    assert events(factory, date_from=today + timedelta(days=1))[0] == 0
    assert events(factory, actor="nadia")[0] >= 1


def test_stock_adjustment_is_atomic_and_appears_in_the_feed_on_postgres(factory):
    with factory() as s:
        version = s.get(Material, "H").version
    with factory() as s:
        with pytest.raises(HTTPException) as refused:
            update_material("H", MaterialUpdate(available=5, expected_version=version), user=OLA, db=s)  # no reason
        s.rollback()
    assert refused.value.status_code == 422
    with factory() as s:
        update_material("H", MaterialUpdate(available=3, expected_version=version, actor="Ola", stock_reason="Recount"), user=OLA, db=s)
    with factory() as s:
        adjustments = s.query(MaterialTransaction).filter_by(material_id="H", transaction_type="ADJUSTMENT").all()
        assert [(a.quantity, a.reason) for a in adjustments] == [(0, "available 4→3 — Recount")]
    assert [r["reason"] for r in events(factory, search="recount")[1]] == ["available 4→3 — Recount"]


def test_identical_timestamps_and_literal_wildcards_on_postgres(factory):
    from datetime import datetime
    from app.models.transfer import MaterialTransferEvent
    with factory() as s:
        transfer_id = s.query(MaterialTransferEvent.transfer_id).first()[0]
        same = datetime(2026, 10, 20, 9, 0, 0)
        for event_id in (9009, 9010, 9002):
            s.add(MaterialTransferEvent(id=event_id, transfer_id=transfer_id, action="requested", to_status="Requested",
                                        actor="t", created_at=same))
        s.commit()
    tied = [r["key"] for r in events(factory, sources=[AuditSource.TRANSFER], date_from=same.date(), date_to=same.date())[1]]
    assert tied == ["transfer:9010", "transfer:9009", "transfer:9002"]
    total = events(factory)[0]
    assert events(factory, search="%")[0] == 0
    assert 0 < events(factory, search="_")[0] < total
    assert "Transfer out" in {r["action"] for r in events(factory, search="transfer out")[1]}
