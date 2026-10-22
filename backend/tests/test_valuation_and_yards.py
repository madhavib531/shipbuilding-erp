"""Stock valuation (unit cost from purchase prices), purchase-order delivery yards, and yard filters."""

from decimal import Decimal

import pytest

from app.models.material import Material
from app.models.program import Ship, ShipSeries
from tests.test_goods_receipts import PO, approved_order, order_line, receive, rline, world  # noqa: F401

M = "/api/v1/materials"


def cost(db, mid):
    db.expire_all()
    m = db.get(Material, mid)
    return (None if m.unit_cost is None else Decimal(m.unit_cost).quantize(Decimal("0.0001")), m.cost_currency)


def patch(client, mid, **body):
    v = client.get(f"{M}/{mid}").json()["data"]["version"]
    return client.patch(f"{M}/{mid}", json={**body, "expected_version": v})


class TestUnitCost:
    def test_receipt_into_a_new_batch_takes_the_order_price(self, client, world, db):
        po = approved_order(client, lines=[order_line(unit_price="123.45")])
        assert receive(client, po, [rline(po)]).status_code == 201
        assert cost(db, "NEW-1") == (Decimal("123.4500"), "EUR")

    def test_existing_batch_without_cost_stays_unvalued(self, client, world, db):
        po = approved_order(client)
        assert receive(client, po, [rline(po, destination_material_id="EXIST", batch="LOT-1")]).status_code == 201
        assert cost(db, "EXIST") == (None, None)

    def test_same_currency_gives_a_weighted_average(self, client, world, db):
        assert patch(client, "EXIST", unit_cost="50", cost_currency="EUR").status_code == 200  # 5 sheets at 50
        po = approved_order(client)  # 10 at 100 EUR
        assert receive(client, po, [rline(po, destination_material_id="EXIST", batch="LOT-1")]).status_code == 201
        assert cost(db, "EXIST") == (Decimal("83.3333"), "EUR")

    def test_other_currency_keeps_the_cost(self, client, world, db):
        assert patch(client, "EXIST", unit_cost="50", cost_currency="EUR").status_code == 200
        po = approved_order(client, lines=[order_line(currency="USD")])
        assert receive(client, po, [rline(po, destination_material_id="EXIST", batch="LOT-1")]).status_code == 201
        assert cost(db, "EXIST") == (Decimal("50.0000"), "EUR")

    @pytest.mark.parametrize("body, code", [
        ({"unit_cost": "10"}, 422),                             # cost without currency
        ({"cost_currency": "EUR"}, 422),
        ({"unit_cost": "-1", "cost_currency": "EUR"}, 422),
        ({"unit_cost": "1.23456", "cost_currency": "EUR"}, 422),  # more than four decimals
        ({"unit_cost": "10", "cost_currency": "euro"}, 422),
        ({"unit_cost": "10", "cost_currency": "eur"}, 200),     # upper-cased
    ])
    def test_cost_validation(self, client, world, db, body, code):
        assert patch(client, "EXIST", **body).status_code == code
        if code == 200:
            assert cost(db, "EXIST") == (Decimal("10.0000"), "EUR")

    def test_cost_can_be_cleared_and_changes_no_stock(self, client, world, db):
        assert patch(client, "EXIST", unit_cost="10", cost_currency="EUR").status_code == 200
        assert patch(client, "EXIST", unit_cost=None, cost_currency=None).status_code == 200
        db.expire_all()
        m = db.get(Material, "EXIST")
        assert (m.unit_cost, m.cost_currency, m.quantity, m.available) == (None, None, 5, 5)

    def test_transfer_into_a_new_batch_carries_the_cost(self, client, world, db):
        assert patch(client, "EXIST", unit_cost="12.5", cost_currency="EUR").status_code == 200
        t = client.post("/api/v1/transfers", json={"actor": "t", "material_id": "EXIST", "quantity": 2, "to_yard_id": "Y2"}).json()["data"]
        for step in ("approve", "dispatch"):
            assert client.post(f"/api/v1/transfers/{t['id']}/{step}", json={"actor": "t"}).status_code == 200
        r = client.post(f"/api/v1/transfers/{t['id']}/receive", json={"actor": "t", "destination_material_id": "EXIST-Y2"})
        assert r.status_code == 200, r.text
        assert cost(db, "EXIST-Y2") == (Decimal("12.5000"), "EUR")


class TestStockValue:
    def test_value_per_currency_and_unvalued_batches(self, client, world):
        patch(client, "EXIST", unit_cost="10", cost_currency="EUR")       # 5 x 10 EUR
        patch(client, "OTHER", unit_cost="2.5", cost_currency="USD")      # 7 x 2.5 USD
        s = client.get(f"{M}/summary").json()["data"]
        assert s["stock_value"] == [{"currency": "EUR", "amount": "50.00"}, {"currency": "USD", "amount": "17.50"}]
        assert s["unvalued_batches"] == 0
        patch(client, "OTHER", unit_cost=None, cost_currency=None)
        s = client.get(f"{M}/summary").json()["data"]
        assert s["stock_value"] == [{"currency": "EUR", "amount": "50.00"}] and s["unvalued_batches"] == 1

    def test_summary_by_yard(self, client, world, db):
        db.add(Material(id="FAR", name="Far", category_id="STEEL", batch="F", unit="u", quantity=3, available=3, reserved=0, yard_id="Y2"))
        db.commit()
        y2 = client.get(f"{M}/summary", params={"yard": "Y2"}).json()["data"]
        assert (y2["total_batches"], y2["active_yards"], y2["unvalued_batches"]) == (1, 1, 1)
        assert client.get(f"{M}/summary").json()["data"]["total_batches"] == 3


class TestDeliveryYard:
    def make(self, client, **over):
        body = {"actor": "Maya", "supplier_id": "SUP", "lines": [order_line()], **over}
        return client.post(PO, json=body)

    def test_set_validate_filter_and_clear(self, client, world):
        r = self.make(client, delivery_yard_id="Y2")
        assert r.status_code == 201 and r.json()["data"]["delivery_yard"] == {"id": "Y2", "name": "Yard 2"}
        assert self.make(client, delivery_yard_id="NOPE").status_code == 422
        self.make(client)  # no yard
        assert client.get(PO, params={"yard": "Y2"}).json()["data"]["total"] == 1
        assert client.get(PO).json()["data"]["total"] == 2
        assert client.get(f"{PO}/summary", params={"yard": "Y2"}).json()["data"]["by_status"]["Draft"] == 1
        po = r.json()["data"]
        r = client.patch(f"{PO}/{po['id']}", json={"actor": "Maya", "expected_version": po["version"], "delivery_yard_id": None})
        assert r.status_code == 200 and r.json()["data"]["delivery_yard"] is None


class TestYardFilters:
    def test_transfers_inspections_audit_dashboard(self, client, world, db):
        db.add_all([ShipSeries(id="S", name="Series")])
        db.commit()
        db.add_all([Ship(id="SH1", name="Ship 1", series_id="S", yard_id="Y1", allocated_value=0.0),
                    Ship(id="SH2", name="Ship 2", series_id="S", yard_id="Y2", allocated_value=0.0)])
        db.commit()
        assert client.post("/api/v1/transfers", json={"actor": "t", "material_id": "EXIST", "quantity": 1, "to_yard_id": "Y2"}).status_code == 201
        assert client.post("/api/v1/inspections", json={"actor": "i", "material_id": "OTHER", "quantity": 1, "reason": "r"}).status_code == 201

        summary = lambda yard: client.get("/api/v1/transfers/summary", params={"yard": yard}).json()["data"]["awaiting_approval"]  # noqa: E731
        assert (summary("Y1"), summary("Y2"), summary("NOPE")) == (1, 1, 0)
        holds = lambda yard: client.get("/api/v1/inspections", params={"yard": yard}).json()["data"]["total"]  # noqa: E731
        assert (holds("Y1"), holds("Y2")) == (1, 0)
        assert client.get("/api/v1/inspections/summary", params={"yard": "Y2"}).json()["data"]["open"] == 0
        audit = lambda yard: {e["source"] for e in client.get("/api/v1/audit-events", params={"yard": yard}).json()["data"]["events"]}  # noqa: E731
        assert audit("Y1") == {"transfer", "inspection", "stock"}
        assert audit("Y2") == {"transfer"}  # the transfer goes to Y2; the held batch is in Y1
        ships = client.get("/api/v1/dashboard/ships", params={"yard": "Y2"}).json()["data"]["ships"]
        assert [s["id"] for s in ships] == ["SH2"]
        months = client.get("/api/v1/dashboard/movements", params={"yard": "Y2", "months": 1}).json()["data"]["months"]
        assert months[-1] == {"month": months[-1]["month"], "stock_in": 0, "stock_out": 0}
