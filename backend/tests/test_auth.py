"""Sign-in, sessions, roles and user administration, with the real authentication (no test stand-in)."""

from datetime import datetime, timedelta

import pytest

from app.models.facility import Yard
from app.models.material import MaterialCategory
from app.models.transaction import MaterialTransaction
from app.models.user import User, UserRole, UserSession
from app.services import auth_service

PASSWORD = "correct horse battery"


@pytest.fixture
def users(db, real_auth):
    for name, role in [("admin", UserRole.ADMIN), ("sam", UserRole.STOREKEEPER), ("pia", UserRole.PROCUREMENT),
                       ("ivan", UserRole.INSPECTOR), ("vera", UserRole.VIEWER)]:
        auth_service.create_user(db, name, name.title() + " Example", role, PASSWORD)
    db.add_all([MaterialCategory(id="C", name="Cat"), Yard(id="Y", name="Yard", location="x", capacity=1.0)])
    db.commit()


def login(client, username, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def headers(client, username):
    r = login(client, username)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def batch(i="N", **over):
    return {"id": i, "name": "Plate", "category_id": "C", "batch": "B", "unit": "u", "yard_id": "Y",
            "quantity": 3, "available": 3, "reserved": 0, **over}


class TestSignIn:
    def test_everything_but_health_and_login_needs_a_session(self, client, users):
        assert client.get("/health").status_code == 200
        for path in ["/api/v1/materials", "/api/v1/audit-events", "/api/v1/dashboard/movements", "/api/v1/auth/me", "/api/v1/users"]:
            r = client.get(path)
            assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", path
        assert client.post("/api/v1/materials", json=batch()).status_code == 401

    def test_login_returns_a_working_token_and_profile(self, client, users):
        r = login(client, "  SAM ")  # usernames are case- and space-insensitive
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["user"]["role"] == "Storekeeper" and "transfers" in data["user"]["permissions"]
        assert "password_hash" not in data["user"]
        h = {"Authorization": f"Bearer {data['token']}"}
        assert client.get("/api/v1/auth/me", headers=h).json()["data"]["username"] == "sam"
        assert client.get("/api/v1/materials", headers=h).status_code == 200

    @pytest.mark.parametrize("username, password", [("sam", "wrong password"), ("nobody", PASSWORD)])
    def test_bad_credentials_are_refused_without_saying_which_part(self, client, users, username, password):
        r = login(client, username, password)
        assert r.status_code == 401 and "Incorrect username or password" in r.json()["detail"]

    def test_only_hashes_are_stored(self, db, users):
        stored = db.query(User).filter_by(username="sam").one().password_hash
        assert stored.startswith("scrypt$") and PASSWORD not in stored
        assert all(len(s.token_hash) == 64 for s in db.query(UserSession))

    def test_logout_and_expiry_end_the_session(self, client, db, users):
        h = headers(client, "sam")
        assert client.post("/api/v1/auth/logout", headers=h).status_code == 200
        assert client.get("/api/v1/materials", headers=h).status_code == 401
        h = headers(client, "sam")
        for s in db.query(UserSession).filter(UserSession.revoked_at.is_(None)):
            s.expires_at = datetime.now() - timedelta(seconds=1)
        db.commit()
        assert client.get("/api/v1/materials", headers=h).status_code == 401

    def test_repeated_failures_are_throttled(self, client, users):
        for _ in range(5):
            assert login(client, "sam", "nope").status_code == 401
        r = login(client, "sam")  # even the right password waits
        assert r.status_code == 429 and "Retry-After" in r.headers

    def test_malformed_authorization_header(self, client, users):
        for value in ["Bearer", "Basic abc", "Bearer not-a-token", ""]:
            assert client.get("/api/v1/materials", headers={"Authorization": value}).status_code == 401


class TestRoles:
    def test_viewer_reads_but_cannot_change(self, client, users):
        h = headers(client, "vera")
        assert client.get("/api/v1/materials", headers=h).status_code == 200
        r = client.post("/api/v1/materials", json=batch(), headers=h)
        assert r.status_code == 403 and "Viewer" in r.json()["detail"]

    @pytest.mark.parametrize("who, path, body, allowed", [
        ("sam", "/api/v1/materials", batch(), True),
        ("pia", "/api/v1/materials", batch(), False),
        ("pia", "/api/v1/suppliers", {"id": "S1", "name": "Supplier"}, True),
        ("sam", "/api/v1/suppliers", {"id": "S1", "name": "Supplier"}, False),
        ("ivan", "/api/v1/suppliers", {"id": "S1", "name": "Supplier"}, False),
        ("admin", "/api/v1/suppliers", {"id": "S1", "name": "Supplier"}, True),
    ])
    def test_role_permissions(self, client, users, who, path, body, allowed):
        r = client.post(path, json=body, headers=headers(client, who))
        assert (r.status_code < 400) == allowed, r.text
        if not allowed:
            assert r.status_code == 403

    def test_holds_need_storekeeper_or_inspector(self, client, users):
        assert client.post("/api/v1/materials", json=batch(), headers=headers(client, "sam")).status_code == 201
        hold = {"material_id": "N", "quantity": 1, "reason": "Check"}
        assert client.post("/api/v1/inspections", json=hold, headers=headers(client, "pia")).status_code == 403
        assert client.post("/api/v1/inspections", json=hold, headers=headers(client, "ivan")).status_code == 201

    def test_the_signed_in_user_is_recorded_whatever_the_body_says(self, client, db, users):
        r = client.post("/api/v1/materials", json=batch(actor="Mallory"), headers=headers(client, "sam"))
        assert r.status_code == 201
        db.expire_all()
        assert db.query(MaterialTransaction).one().actor == "Sam Example"


class TestUserAdmin:
    def test_only_admins_manage_users(self, client, users):
        assert client.get("/api/v1/users", headers=headers(client, "sam")).status_code == 403
        listed = client.get("/api/v1/users", headers=headers(client, "admin")).json()["data"]
        assert {u["username"] for u in listed} == {"admin", "sam", "pia", "ivan", "vera"}
        assert all("password_hash" not in u for u in listed)

    def test_create_validate_and_sign_in(self, client, users):
        h = headers(client, "admin")
        new = {"username": "nina", "display_name": "Nina Berg", "role": "Inspector", "password": "long enough pw"}
        assert client.post("/api/v1/users", json=new, headers=h).status_code == 201
        assert client.post("/api/v1/users", json=new, headers=h).status_code == 409
        assert client.post("/api/v1/users", json={**new, "username": "x2", "password": "short"}, headers=h).status_code == 422
        assert client.post("/api/v1/users", json={**new, "username": "bad name!"}, headers=h).status_code == 422
        assert login(client, "nina", "long enough pw").json()["data"]["user"]["role"] == "Inspector"

    def test_deactivating_ends_sessions_and_blocks_sign_in(self, client, db, users):
        sam = headers(client, "sam")
        sam_id = db.query(User).filter_by(username="sam").one().id
        r = client.patch(f"/api/v1/users/{sam_id}", json={"is_active": False}, headers=headers(client, "admin"))
        assert r.status_code == 200 and r.json()["data"]["is_active"] is False
        assert client.get("/api/v1/materials", headers=sam).status_code == 401
        assert login(client, "sam").status_code == 401

    def test_the_last_admin_cannot_be_demoted_or_deactivate_themselves(self, client, db, users):
        h = headers(client, "admin")
        admin_id = db.query(User).filter_by(username="admin").one().id
        assert client.patch(f"/api/v1/users/{admin_id}", json={"role": "Viewer"}, headers=h).status_code == 409
        assert client.patch(f"/api/v1/users/{admin_id}", json={"is_active": False}, headers=h).status_code == 409
        pia_id = db.query(User).filter_by(username="pia").one().id
        assert client.patch(f"/api/v1/users/{pia_id}", json={"role": "Admin"}, headers=h).status_code == 200
        assert client.patch(f"/api/v1/users/{admin_id}", json={"role": "Viewer"}, headers=h).status_code == 200

    def test_password_change_and_reset(self, client, db, users):
        h = headers(client, "sam")
        r = client.post("/api/v1/auth/password", json={"current_password": "wrong", "new_password": "new password 1"}, headers=h)
        assert r.status_code == 422
        r = client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "new password 1"}, headers=h)
        assert r.status_code == 200
        assert client.get("/api/v1/materials", headers=h).status_code == 401  # signed out everywhere
        assert login(client, "sam").status_code == 401 and login(client, "sam", "new password 1").status_code == 200
        sam_id = db.query(User).filter_by(username="sam").one().id
        assert client.post(f"/api/v1/users/{sam_id}/password", json={"new_password": "reset by admin"}, headers=headers(client, "admin")).status_code == 200
        assert login(client, "sam", "reset by admin").status_code == 200
