"""GET /api/v1/audit-events: one feed over the stock ledger, transfer, purchase-order and inspection events."""

from datetime import date, timedelta

import pytest

from tests.test_goods_receipts import approved_order, receive, rline, world  # noqa: F401

URL = "/api/v1/audit-events"


@pytest.fixture
def history(client, world):
    """Real events from every source, created through the API."""
    po = approved_order(client)                                          # PO-00001: created, approved
    hold = receive(client, po, [rline(po, destination_material_id="H-1", batch="LOT-H", hold_for_inspection=True)]
                   ).json()["data"]["receipt"]["lines"][0]["inspection_hold"]  # received; RECEIPT + INSPECTION; QI held
    assert client.post(f"/api/v1/inspections/{hold['id']}/release",
                       json={"actor": "Nadia King", "expected_version": 1, "quantity": 10}).status_code == 200
    tid = client.post("/api/v1/transfers", json={"actor": "Leo Anders", "material_id": "EXIST", "quantity": 2,
                                                  "to_yard_id": "Y2"}).json()["data"]["id"]
    client.post(f"/api/v1/transfers/{tid}/approve", json={"actor": "Maya"})
    client.post(f"/api/v1/transfers/{tid}/dispatch", json={"actor": "Maya"})          # TR-00001 + TRANSFER_OUT
    v = client.get("/api/v1/materials/OTHER").json()["data"]["version"]
    assert client.patch("/api/v1/materials/OTHER", json={"quantity": 6, "available": 6, "expected_version": v,
                                                         "actor": "Ola Berg", "stock_reason": "Cycle count"}).status_code == 200


def feed(client, **params):
    r = client.get(URL, params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def keys(data):
    return [e["key"] for e in data["events"]]


def test_empty_feed(client, world):
    assert feed(client) == {"events": [], "total": 0, "skip": 0, "limit": 50}


def test_combines_all_four_sources_with_references(client, history):
    data = feed(client, limit=200)
    by_source = {}
    for e in data["events"]:
        by_source.setdefault(e["source"], []).append(e)
    assert set(by_source) == {"stock", "transfer", "purchase_order", "inspection"}
    assert data["total"] == len(data["events"]) == 13  # 3 order + 3 transfer + 2 inspection + 5 ledger
    assert sorted((e["action"], e["record"], e["quantity"]) for e in by_source["stock"]) == [
        ("Adjustment", "OTHER", -1), ("Inspection", "H-1", 10), ("Receipt", "H-1", 10),
        ("Release", "H-1", 10), ("Transfer out", "EXIST", 2)]
    assert sorted((e["action"], e["record"]) for e in by_source["transfer"]) == [
        ("Approved", "TR-00001"), ("Dispatched", "TR-00001"), ("Requested", "TR-00001")]
    assert sorted((e["action"], e["record"]) for e in by_source["inspection"]) == [("Held", "QI-00001"), ("Released", "QI-00001")]
    po = {e["action"]: e for e in by_source["purchase_order"]}
    assert set(po) == {"Created", "Approved", "Received"}
    assert po["Received"]["detail"] == "GR-00001: 10 accepted, 0 rejected, 10 held for inspection"
    assert (po["Approved"]["from_status"], po["Approved"]["to_status"], po["Approved"]["subject"]) == ("Draft", "Approved", "Supplier")
    adjustment = next(e for e in by_source["stock"] if e["action"] == "Adjustment")
    assert (adjustment["actor"], adjustment["reason"], adjustment["unit"]) == ("Ola Berg", "On hand 7→6, available 7→6 — Cycle count", "m")
    assert next(e for e in by_source["inspection"] if e["action"] == "Released")["actor"] == "Nadia King"


def test_ordering_is_newest_first_and_deterministic(client, history):
    first = feed(client, limit=200)["events"]
    assert all(keys(feed(client, limit=200)) == [e["key"] for e in first] for _ in range(3))
    # created_at descending; identical timestamps broken by source, then event key descending.
    expected = sorted(first, key=lambda e: e["key"].split(":", 1)[1], reverse=True)
    expected = sorted(expected, key=lambda e: e["source"])
    expected = sorted(expected, key=lambda e: e["created_at"], reverse=True)
    assert [e["key"] for e in first] == [e["key"] for e in expected]


def test_pagination_walks_the_feed_without_gaps_or_repeats(client, history):
    full = keys(feed(client, limit=200))
    pages = [feed(client, skip=s, limit=4) for s in range(0, len(full), 4)]
    assert all(p["total"] == len(full) for p in pages)
    assert [k for p in pages for k in keys(p)] == full
    assert feed(client, skip=100)["events"] == []


@pytest.mark.parametrize("sources, expected", [
    (["stock"], {"stock"}),
    (["transfer", "inspection"], {"transfer", "inspection"}),
    (["purchase_order"], {"purchase_order"}),
])
def test_source_filter(client, history, sources, expected):
    data = feed(client, source=sources, limit=200)
    assert {e["source"] for e in data["events"]} == expected and data["total"] == len(data["events"])


@pytest.mark.parametrize("term, expected_sources, records", [
    ("PO-00001", {"purchase_order", "stock"}, {"PO-00001", "H-1"}),   # the order and the receipt rows naming it
    ("po-1", {"purchase_order", "stock"}, {"PO-00001", "H-1"}),
    ("TR-00001", {"transfer", "stock"}, {"TR-00001", "EXIST"}),       # the transfer and its TRANSFER_OUT row
    ("QI-00001", {"inspection", "stock"}, {"QI-00001", "H-1"}),       # the hold and its INSPECTION/RELEASE rows
    ("GR-00001", {"stock", "inspection"}, {"H-1", "QI-00001"}),  # receipt row and "Received on GR-00001"
    ("LOT-H", {"stock", "inspection"}, {"H-1", "QI-00001"}),          # batch number
    ("AH36", {"stock", "inspection", "transfer"}, {"H-1", "QI-00001", "EXIST", "TR-00001"}),  # name: both AH36 batches
    ("other", {"stock"}, {"OTHER"}),                                  # material ID
    ("cycle count", {"stock"}, {"OTHER"}),                            # reason
])
def test_search(client, history, term, expected_sources, records):
    events = feed(client, search=term, limit=200)["events"]
    assert {e["source"] for e in events} == expected_sources, events
    assert {e["record"] for e in events} == records


def test_search_and_actor_filters_with_no_match(client, history):
    assert feed(client, search="no-such-thing")["total"] == 0
    assert feed(client, search="TR-00099")["total"] == 0
    assert {e["actor"] for e in feed(client, actor="nadia", limit=200)["events"]} == {"Nadia King"}


def test_date_filters(client, history):
    today = date.today()
    total = feed(client)["total"]
    assert feed(client, date_from=str(today), date_to=str(today))["total"] == total
    assert feed(client, date_from=str(today + timedelta(days=1)))["total"] == 0
    assert feed(client, date_to=str(today - timedelta(days=1)))["total"] == 0


@pytest.mark.parametrize("params", [
    {"source": "suppliers"}, {"date_from": "2026-13-01"}, {"date_from": "2026-10-02", "date_to": "2026-10-01"},
    {"limit": 0}, {"limit": 201}, {"skip": -1},
])
def test_invalid_parameters_are_rejected(client, world, params):
    assert client.get(URL, params=params).status_code == 422


def test_identical_timestamps_order_by_numeric_event_id(client, world, db):
    from datetime import datetime
    from app.models.transfer import MaterialTransfer, MaterialTransferEvent, TransferStatus
    db.add(MaterialTransfer(id=1, material_id="EXIST", quantity=1, unit="sheets", from_yard_id="Y1", to_yard_id="Y2",
                            status=TransferStatus.REQUESTED, requested_by="t"))
    db.commit()
    same = datetime(2026, 10, 20, 9, 0, 0)
    for event_id in (9, 10, 2):
        db.add(MaterialTransferEvent(id=event_id, transfer_id=1, action="requested", to_status="Requested",
                                     actor="t", created_at=same))
    db.commit()
    assert keys(feed(client, source="transfer")) == ["transfer:10", "transfer:9", "transfer:2"]


def test_purchase_order_event_summaries(client, world):
    from tests.test_goods_receipts import PO, order_line
    draft = client.post(PO, json={"actor": "Maya", "supplier_id": "SUP", "lines": [order_line()]}).json()["data"]
    assert client.patch(f"{PO}/{draft['id']}", json={"actor": "Maya", "expected_version": 1, "notes": "Rush",
                                                     "lines": [order_line(), order_line(description="b")]}).status_code == 200
    po = approved_order(client)
    o = receive(client, po, [rline(po, accepted_quantity=4)], key="part").json()["data"]["purchase_order"]
    assert client.post(f"{PO}/{po['id']}/close", json={"actor": "Maya", "expected_version": o["version"], "reason": "Short"}).status_code == 200
    held_po = approved_order(client)
    hold = receive(client, held_po, [rline(held_po, destination_material_id="H-2", batch="LOT-2", hold_for_inspection=True)],
                   key="held").json()["data"]["receipt"]["lines"][0]["inspection_hold"]
    assert client.post(f"/api/v1/inspections/{hold['id']}/reject", json={
        "actor": "QA", "expected_version": 1, "quantity": 3, "reason": "Pitting", "disposition": "Scrap"}).status_code == 200
    details = {e["action"]: e["detail"] for e in feed(client, source="purchase_order", limit=200)["events"]
               if e["action"] in ("Edited", "Closed", "Inspection rejected")}
    assert details == {
        "Edited": "changed notes; lines 1→2",
        "Closed": "Outstanding quantity cancelled on line 1: 6",
        "Inspection rejected": f"{hold['display_id']}: 3 rejected on line 1 (Scrap)",
    }


def test_wildcard_characters_are_matched_literally(client, history):
    v = client.get("/api/v1/materials/OTHER").json()["data"]["version"]
    client.patch("/api/v1/materials/OTHER", json={"quantity": 5, "available": 5, "expected_version": v,
                                                  "actor": "Ola Berg", "stock_reason": "Shrinkage 5%"})
    everything = feed(client)["total"]
    pct = feed(client, search="%", limit=200)["events"]
    assert [e["reason"] for e in pct] == ["On hand 6→5, available 6→5 — Shrinkage 5%"]
    underscore = feed(client, search="_", limit=200)
    assert 0 < underscore["total"] < everything, "_ must not act as a wildcard"
    assert all(e["source"] == "stock" and e["action"] == "Transfer out" for e in underscore["events"])  # stored TRANSFER_OUT
    assert feed(client, actor="%")["total"] == 0


@pytest.mark.parametrize("term, action", [("Transfer out", "Transfer out"), ("transfer OUT", "Transfer out"),
                                          ("transfer_out", "Transfer out"), ("Released", "Released")])
def test_actions_match_their_displayed_names(client, history, term, action):
    assert action in {e["action"] for e in feed(client, search=term, limit=200)["events"]}
