"""Pytest configuration and fixtures."""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.models.base import Base


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
