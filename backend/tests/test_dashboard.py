"""Dashboard aggregates: monthly stock movements and ship programs."""

from datetime import date, datetime

import pytest

from app.models.facility import Yard
from app.models.material import Material, MaterialCategory
from app.models.program import Ship, ShipBuildStatusEnum, ShipSeries
from app.models.transaction import MaterialTransaction, TransactionType as T
from app.services import dashboard_service


@pytest.fixture
def refs(db):
    db.add_all([MaterialCategory(id="C", name="Cat"), Yard(id="Y1", name="Yard 1", location="a", capacity=1.0),
                ShipSeries(id="SER", name="Series")])
    db.commit()
    db.add_all([
        Ship(id="S1", name="Atlas", series_id="SER", yard_id="Y1", allocated_value=0.0,
             build_status=ShipBuildStatusEnum.OUTFITTING, build_progress=54),
        Ship(id="S2", name="Calypso", series_id="SER", yard_id="Y1", allocated_value=0.0),
        Material(id="M", name="m", category_id="C", batch="B", unit="u", quantity=9, available=9, reserved=0, yard_id="Y1"),
    ])
    db.commit()


def ledger(db, n, kind, when):
    db.add(MaterialTransaction(id=f"TXN-{n}", material_id="M", transaction_type=kind, quantity=1, unit="u",
                               actor="t", created_at=when))


class TestMovements:
    def test_monthly_counts_classify_types_and_zero_fill_across_a_year_boundary(self, db, refs):
        for n, (kind, when) in enumerate([
            (T.RECEIPT, datetime(2025, 12, 3)), (T.TRANSFER_IN, datetime(2025, 12, 20)),
            (T.TRANSFER_OUT, datetime(2025, 12, 21)),
            (T.SCRAP, datetime(2026, 2, 1)), (T.RETURN, datetime(2026, 2, 9)), (T.ISSUANCE, datetime(2026, 2, 9)),
            (T.RECEIPT, datetime(2026, 2, 10, 23, 59)),
            # Neither in nor out: holds, releases and transit-shortage adjustments.
            (T.INSPECTION, datetime(2026, 2, 2)), (T.RELEASE, datetime(2026, 2, 2)), (T.ADJUSTMENT, datetime(2026, 2, 2)),
            # Before the window.
            (T.RECEIPT, datetime(2025, 11, 30, 23, 59)),
        ]):
            ledger(db, n, kind, when)
        db.commit()
        data = dashboard_service.movements(db, 3, today=date(2026, 2, 10))
        assert data["months"] == [
            {"month": "2025-12", "stock_in": 2, "stock_out": 1},
            {"month": "2026-01", "stock_in": 0, "stock_out": 0},
            {"month": "2026-02", "stock_in": 1, "stock_out": 3},
        ]
        assert data["stock_in_types"] == ["Receipt", "Transfer in"]
        assert data["stock_out_types"] == ["Transfer out", "Issuance", "Scrap", "Return"]

    def test_api_returns_requested_months_and_bounds_them(self, client, db, refs):
        r = client.get("/api/v1/dashboard/movements", params={"months": 12})
        assert r.status_code == 200
        months = r.json()["data"]["months"]
        assert len(months) == 12 and months[-1]["month"] == f"{date.today():%Y-%m}"
        assert all(m["stock_in"] == m["stock_out"] == 0 for m in months)
        assert client.get("/api/v1/dashboard/movements", params={"months": 0}).status_code == 422
        assert client.get("/api/v1/dashboard/movements", params={"months": 25}).status_code == 422


def test_ships_report_build_status_and_allocated_batches(client, db, refs):
    db.add_all([
        Material(id="A1", name="a", category_id="C", batch="B", unit="u", quantity=5, available=2, reserved=3, yard_id="Y1", ship_id="S1"),
        Material(id="A2", name="a", category_id="C", batch="B", unit="u", quantity=5, available=5, reserved=0, yard_id="Y1", ship_id="S1"),
    ])
    db.commit()
    ships = client.get("/api/v1/dashboard/ships").json()["data"]["ships"]
    assert ships == [
        {"id": "S1", "name": "Atlas", "yard": "Yard 1", "build_status": "Outfitting", "build_progress": 54,
         "allocated_batches": 2, "reserved_batches": 1},
        {"id": "S2", "name": "Calypso", "yard": "Yard 1", "build_status": "Planning", "build_progress": 0,
         "allocated_batches": 0, "reserved_batches": 0},
    ]
