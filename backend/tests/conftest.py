"""Pytest configuration and fixtures."""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import Request
from fastapi.testclient import TestClient
from app.main import app
from app.auth import current_user
from app.database import get_db
from app.models.base import Base
from app.models.user import User, UserRole


async def signed_in_test_user(request: Request) -> User:
    """Stands in for sign-in in API tests: an admin named after the request body's `actor` (the name the
    tests already send), or "Test Admin". Tests of sign-in itself use the `real_auth` fixture instead."""
    name = "Test Admin"
    if request.method in ("POST", "PATCH", "PUT"):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - empty or non-JSON body
            body = None
        if isinstance(body, dict) and isinstance(body.get("actor"), str) and body["actor"].strip():
            name = body["actor"].strip()
    return User(id=0, username="test", display_name=name, role=UserRole.ADMIN, is_active=True)


@pytest.fixture(scope="function")
def client_and_db():
    """Provide a test client and a session that share one temporary SQLite database file."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = None

    try:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def override_get_db():
            db_session = TestingSessionLocal()
            try:
                yield db_session
            finally:
                db_session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[current_user] = signed_in_test_user

        db_session = TestingSessionLocal()
        try:
            yield TestClient(app), db_session
        finally:
            db_session.close()

    finally:
        app.dependency_overrides.clear()
        if engine is not None:
            engine.dispose()
        os.close(db_fd)
        os.unlink(db_path)


@pytest.fixture
def client(client_and_db):
    """Extract client from combined fixture."""
    return client_and_db[0]


@pytest.fixture
def db(client_and_db):
    """Extract db session from combined fixture."""
    return client_and_db[1]


@pytest.fixture
def real_auth(client_and_db):
    """Turns the sign-in stand-in off, so requests need a real bearer token."""
    app.dependency_overrides.pop(current_user, None)
    from app.services import auth_service
    auth_service.reset_throttle()
    yield
    auth_service.reset_throttle()
