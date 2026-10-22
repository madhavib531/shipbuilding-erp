"""Stored notifications: who gets them, de-duplication, read state, the overdue sweep and optional email."""

from datetime import date, timedelta

import pytest

from app.config import settings
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.services import auth_service, notification_service
from tests.test_goods_receipts import PO, approved_order, order_line, world  # noqa: F401

PASSWORD = "correct horse battery"


@pytest.fixture
def staff(db, world):
    """One user per role; the storekeeper and inspector have email addresses."""
    made = {}
    for name, role, email in [("admin", UserRole.ADMIN, None), ("sam", UserRole.STOREKEEPER, "sam@yard.example"),
                              ("pia", UserRole.PROCUREMENT, None), ("ivan", UserRole.INSPECTOR, "ivan@yard.example"),
                              ("vera", UserRole.VIEWER, None)]:
        made[name] = auth_service.create_user(db, name, name.title(), role, PASSWORD, email).id
    return made


def inbox(db, staff):
    db.expire_all()
    by_id = {v: k for k, v in staff.items()}
    out: dict[str, list[str]] = {}
    for n in db.query(Notification).order_by(Notification.id):
        out.setdefault(by_id[n.user_id], []).append(n.kind)
    return out


def flag_low(client, mid="EXIST"):
    v = client.get(f"/api/v1/materials/{mid}").json()["data"]["version"]
    return client.patch(f"/api/v1/materials/{mid}", json={"status": "Low stock", "expected_version": v})


class TestWhoIsNotified:
    def test_low_stock_goes_to_stores_procurement_and_admin_once(self, client, db, staff):
        assert flag_low(client).status_code == 200
        assert inbox(db, staff) == {"admin": ["low_stock"], "sam": ["low_stock"], "pia": ["low_stock"]}
        v = client.get("/api/v1/materials/EXIST").json()["data"]["version"]
        client.patch("/api/v1/materials/EXIST", json={"name": "Renamed", "expected_version": v})  # still Low stock
        assert sum(len(k) for k in inbox(db, staff).values()) == 3

    def test_inspection_hold_goes_to_inspectors(self, client, db, staff):
        r = client.post("/api/v1/inspections", json={"material_id": "EXIST", "quantity": 1, "reason": "Check"})
        assert r.status_code == 201
        assert inbox(db, staff) == {"admin": ["inspection_opened"], "ivan": ["inspection_opened"]}
        note = db.query(Notification).filter_by(user_id=staff["ivan"]).one()
        assert note.page == "Quality" and note.record == r.json()["data"]["display_id"]

    def test_transfer_steps_notify_storekeepers(self, client, db, staff):
        t = client.post("/api/v1/transfers", json={"material_id": "EXIST", "quantity": 1, "to_yard_id": "Y2"}).json()["data"]
        client.post(f"/api/v1/transfers/{t['id']}/approve", json={})
        client.post(f"/api/v1/transfers/{t['id']}/dispatch", json={})
        assert inbox(db, staff)["sam"] == ["transfer_requested", "transfer_approved", "transfer_dispatched"]
        assert inbox(db, staff)["admin"] == ["transfer_requested"]

    def test_the_person_who_acted_is_not_notified(self, client, db, staff, real_auth):
        login = client.post("/api/v1/auth/login", json={"username": "sam", "password": PASSWORD}).json()["data"]
        h = {"Authorization": f"Bearer {login['token']}"}
        v = client.get("/api/v1/materials/EXIST", headers=h).json()["data"]["version"]
        assert client.patch("/api/v1/materials/EXIST", json={"status": "Low stock", "expected_version": v}, headers=h).status_code == 200
        assert "sam" not in inbox(db, staff) and inbox(db, staff)["pia"] == ["low_stock"]

    def test_disabled_users_get_nothing(self, client, db, staff):
        db.get(User, staff["pia"]).is_active = False
        db.commit()
        flag_low(client)
        assert "pia" not in inbox(db, staff)


class TestReading:
    def headers(self, client, who):
        token = client.post("/api/v1/auth/login", json={"username": who, "password": PASSWORD}).json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_list_mark_read_and_privacy(self, client, db, staff, real_auth):
        notification_service.notify(db, "low_stock", "A", dedupe_key="a")
        notification_service.notify(db, "low_stock", "B", dedupe_key="b")
        sam, pia = self.headers(client, "sam"), self.headers(client, "pia")
        data = client.get("/api/v1/notifications", headers=sam).json()["data"]
        assert [n["title"] for n in data["notifications"]] == ["B", "A"] and data["unread"] == 2
        first = data["notifications"][0]["id"]
        assert client.post(f"/api/v1/notifications/{first}/read", headers=pia).json()["data"]["updated"] == 0  # not hers
        assert client.post(f"/api/v1/notifications/{first}/read", headers=sam).json()["data"]["updated"] == 1
        assert client.get("/api/v1/notifications", headers=sam).json()["data"]["unread"] == 1
        assert client.post("/api/v1/notifications/read-all", headers=sam).json()["data"]["updated"] == 1
        assert client.get("/api/v1/notifications", headers=pia).json()["data"]["unread"] == 2
        assert client.get("/api/v1/notifications").status_code == 401

    def test_overdue_orders_are_swept_once(self, client, db, staff, real_auth):
        admin = self.headers(client, "admin")
        po = approved_order_as(client, admin)
        from app.models.purchase_order import PurchaseOrder
        db.get(PurchaseOrder, po["id"]).expected_delivery_date = date.today() - timedelta(days=2)
        db.commit()
        pia = self.headers(client, "pia")
        for _ in range(2):
            items = client.get("/api/v1/notifications", headers=pia).json()["data"]["notifications"]
        assert [(n["kind"], n["record"]) for n in items] == [("order_overdue", po["display_id"])]


def approved_order_as(client, headers):
    r = client.post(PO, json={"supplier_id": "SUP", "lines": [order_line()], "expected_delivery_date": str(date.today() + timedelta(days=5))}, headers=headers)
    po = r.json()["data"]
    return client.post(f"{PO}/{po['id']}/approve", json={"expected_version": 1}, headers=headers).json()["data"]


class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout):
        self.host = host
        if FakeSMTP.fail:
            raise OSError("connection refused")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append((msg["To"], msg["Subject"]))


class TestEmail:
    @pytest.fixture(autouse=True)
    def smtp(self, monkeypatch):
        FakeSMTP.sent, FakeSMTP.fail = [], False
        monkeypatch.setattr(notification_service.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(settings, "smtp_host", "mail.example")
        monkeypatch.setattr(settings, "smtp_from", "dockyard@yard.example")

    def test_only_users_with_an_address_are_emailed(self, client, db, staff):
        assert flag_low(client).status_code == 200
        assert FakeSMTP.sent == [("sam@yard.example", "[Dockyard] AH36 plate (EXIST) flagged Low stock")]
        db.expire_all()
        assert db.query(Notification).filter_by(user_id=staff["sam"]).one().emailed_at is not None

    def test_a_mail_failure_never_fails_the_change(self, client, db, staff):
        FakeSMTP.fail = True
        assert flag_low(client).status_code == 200
        db.expire_all()
        note = db.query(Notification).filter_by(user_id=staff["sam"]).one()
        assert note.emailed_at is None  # stored in-app, not emailed

    def test_no_email_without_smtp_settings(self, client, db, staff, monkeypatch):
        monkeypatch.setattr(settings, "smtp_host", None)
        flag_low(client)
        assert FakeSMTP.sent == []
