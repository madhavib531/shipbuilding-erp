"""Exchange rates into INR: admin-only changes, conversion of stock and order totals, missing rates."""

import pytest

from app.models.material import Material
from app.models.user import UserRole
from app.services import auth_service
from tests.test_goods_receipts import PO, approved_order, order_line, world  # noqa: F401

R = "/api/v1/exchange-rates"


def cost(client, mid, amount, currency):
    v = client.get(f"/api/v1/materials/{mid}").json()["data"]["version"]
    assert client.patch(f"/api/v1/materials/{mid}", json={"unit_cost": amount, "cost_currency": currency, "expected_version": v}).status_code == 200


def base_total(client):
    return client.get("/api/v1/materials/summary").json()["data"]["stock_value_base"]


class TestRates:
    def test_set_list_update_and_delete(self, client):
        assert client.get(R).json()["data"] == {"base": "INR", "rates": []}
        r = client.put(f"{R}/usd", json={"rate": "83.25"})
        assert r.status_code == 200
        assert [(x["currency"], x["rate"]) for x in r.json()["data"]["rates"]] == [("USD", "83.250000")]
        client.put(f"{R}/USD", json={"rate": "83.5"})
        assert client.get(R).json()["data"]["rates"][0]["rate"] == "83.500000"
        assert client.delete(f"{R}/USD").status_code == 200
        assert client.delete(f"{R}/USD").status_code == 404

    @pytest.mark.parametrize("currency, body", [("INR", {"rate": "1"}), ("US", {"rate": "1"}), ("USD", {"rate": "0"}),
                                                ("USD", {"rate": "-2"}), ("USD", {"rate": "1.1234567"})])
    def test_invalid_rates(self, client, currency, body):
        assert client.put(f"{R}/{currency}", json=body).status_code == 422

    def test_only_admins_change_rates(self, client, db, real_auth):
        auth_service.create_user(db, "pia", "Pia", UserRole.PROCUREMENT, "long password 1")
        token = client.post("/api/v1/auth/login", json={"username": "pia", "password": "long password 1"}).json()["data"]["token"]
        h = {"Authorization": f"Bearer {token}"}
        assert client.get(R, headers=h).status_code == 200
        assert client.put(f"{R}/USD", json={"rate": "83"}, headers=h).status_code == 403


class TestConversion:
    def test_stock_value_in_rupees(self, client, world):
        cost(client, "EXIST", "100", "INR")   # 5 x ₹100 = ₹500
        cost(client, "OTHER", "2", "USD")     # 7 x $2 = $14
        t = base_total(client)
        assert t["amount"] == "500.00" and t["missing_rates"] == [{"currency": "USD", "amount": "14.00"}]
        client.put(f"{R}/USD", json={"rate": "83.5"})
        t = base_total(client)
        assert t["amount"] == "1669.00"  # 500 + 14 x 83.5
        assert {p["currency"]: p["in_base"] for p in t["parts"]} == {"INR": "500.00", "USD": "1169.00"}
        assert t["missing_rates"] == []

    def test_open_order_value_in_rupees(self, client, world):
        approved_order(client, lines=[order_line(unit_price="10", currency="EUR")])  # 10 x €10 = €100 open
        s = client.get(f"{PO}/summary").json()["data"]["open_value_base"]
        assert (s["amount"], s["missing_rates"]) == ("0.00", [{"currency": "EUR", "amount": "100.00"}])
        client.put(f"{R}/EUR", json={"rate": "90"})
        assert client.get(f"{PO}/summary").json()["data"]["open_value_base"]["amount"] == "9000.00"
