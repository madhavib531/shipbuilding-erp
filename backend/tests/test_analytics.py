"""GET /api/v1/analytics/overview: rule-based figures computed from stored records."""

from datetime import date, datetime, timedelta

import pytest

from app.services import analytics_service
from tests.test_goods_receipts import PO, approved_order, order_line, receive, rline, world  # noqa: F401

URL = "/api/v1/analytics/overview"


def overview(client):
    r = client.get(URL)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_empty_database_reports_zeros_and_no_invented_ratios(client):
    data = overview(client)
    assert data["categories"] == [] and data["suppliers"] == []
    assert [a["batches"] for a in data["aging"]] == [0, 0, 0, 0]
    assert data["transfers"] == {"window_days": 90, "received": 0, "with_shortage": 0, "average_lead_time_hours": None,
                                 "in_transit": 0, "in_transit_overdue": 0}
    assert data["inspections"]["rejection_rate"] is None and data["inspections"]["holds_opened"] == 0
    assert {a["key"]: a["count"] for a in data["attention"]} == {
        "overdue_orders": 0, "late_transfers": 0, "waiting_requests": 0, "stale_holds": 0, "unavailable_stock": 0}


@pytest.fixture
def activity(client, world):
    """Supplier deliveries with rejections, an overdue order, a held-then-decided lot, a short transfer
    and a fully reserved batch — all through the API."""
    po = approved_order(client)                                   # due in 7 days
    receive(client, po, [rline(po, accepted_quantity=7, rejected_quantity=3, rejection_reason="Dented")], key="r1")
    late = client.post(PO, json={"actor": "Maya", "supplier_id": "SUP", "lines": [order_line(description="late")],
                                 "expected_delivery_date": str(date.today() - timedelta(days=2))}).json()["data"]
    assert client.post(f"{PO}/{late['id']}/approve", json={"actor": "Maya", "expected_version": 1}).status_code == 200
    held_po = approved_order(client, lines=[order_line(description="valve", category_id="PIPE", unit="m")])
    hold = receive(client, held_po, [rline(held_po, destination_material_id="H-1", batch="LOT-H", hold_for_inspection=True)],
                   key="r2").json()["data"]["receipt"]["lines"][0]["inspection_hold"]
    client.post(f"/api/v1/inspections/{hold['id']}/release", json={"actor": "QA", "expected_version": 1, "quantity": 6})
    client.post(f"/api/v1/inspections/{hold['id']}/reject", json={"actor": "QA", "expected_version": 2, "quantity": 4,
                                                                  "reason": "Pitting", "disposition": "Scrap"})
    tid = client.post("/api/v1/transfers", json={"actor": "Leo", "material_id": "EXIST", "quantity": 3, "to_yard_id": "Y2"}).json()["data"]["id"]
    for step in ("approve", "dispatch"):
        client.post(f"/api/v1/transfers/{tid}/{step}", json={"actor": "Maya"})
    client.post(f"/api/v1/transfers/{tid}/receive", json={"actor": "Leo", "received_quantity": 2, "destination_material_id": "EXIST-Y2",
                                                         "discrepancy_reason": "1 bent"})
    v = client.get("/api/v1/materials/OTHER").json()["data"]["version"]
    client.patch("/api/v1/materials/OTHER", json={"available": 0, "reserved": 7, "expected_version": v,
                                                  "actor": "Maya", "stock_reason": "Reserved for NS Atlas"})


def test_supplier_performance(client, activity):
    (supplier,) = overview(client)["suppliers"]
    # Three placed orders; two have deliveries, both on or before their expected date.
    assert (supplier["supplier"], supplier["orders"], supplier["orders_delivered"], supplier["deliveries"]) == ("Supplier", 3, 2, 2)
    assert supplier["on_time_rate"] == 1.0
    # Order lines: 7 + 6 received, 3 rejected at receipt + 4 rejected at inspection.
    assert (supplier["received_quantity"], supplier["rejected_quantity"], supplier["rejection_rate"]) == (13, 7, 0.35)


def test_transfers_inspections_and_categories(client, activity):
    data = overview(client)
    assert {k: data["transfers"][k] for k in ("received", "with_shortage", "in_transit")} == {"received": 1, "with_shortage": 1, "in_transit": 0}
    assert data["transfers"]["average_lead_time_hours"] is not None and data["transfers"]["average_lead_time_hours"] >= 0
    assert {k: data["inspections"][k] for k in ("holds_opened", "quantity_held", "quantity_released", "quantity_rejected", "rejection_rate", "open")} == \
        {"holds_opened": 1, "quantity_held": 10, "quantity_released": 6, "quantity_rejected": 4, "rejection_rate": 0.4, "open": 0}
    by_category = {c["category"]: c for c in data["categories"]}
    assert by_category["Pipe"]["stock_but_none_available"] == 1     # OTHER: everything reserved
    assert by_category["Steel"]["batches"] == 3                     # EXIST, NEW-1 and EXIST-Y2


def test_attention_rules(client, activity):
    flags = {a["key"]: a for a in overview(client)["attention"]}
    assert flags["overdue_orders"]["count"] == 1 and flags["overdue_orders"]["examples"][0].startswith("PO-00002 · Supplier · due")
    assert flags["unavailable_stock"]["examples"] == ["OTHER · Unrelated · 7 on hand"]
    assert flags["late_transfers"]["count"] == flags["stale_holds"]["count"] == flags["waiting_requests"]["count"] == 0


def test_time_based_rules_and_age_buckets(client, world, db):
    po = approved_order(client)
    receive(client, po, [rline(po, destination_material_id="H-2", batch="LOT", hold_for_inspection=True)], key="h")
    client.post("/api/v1/transfers", json={"actor": "Leo", "material_id": "EXIST", "quantity": 1, "to_yard_id": "Y2"})
    later = datetime.now() + timedelta(days=100)
    data = analytics_service.overview(db, now=later)
    flags = {a["key"]: a["count"] for a in data["attention"]}
    assert (flags["stale_holds"], flags["waiting_requests"]) == (1, 1)
    assert {a["label"]: a["batches"] for a in data["aging"]}["91–180 days"] == 3   # EXIST, OTHER, H-2 hold stock
    assert {a["label"]: a["batches"] for a in overview(client)["aging"]}["0–90 days"] == 3
