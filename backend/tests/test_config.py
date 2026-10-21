"""The backend refuses to start without DATABASE_URL instead of silently using a local SQLite file."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert "database_url" in str(error.value)


def test_explicit_database_url_is_used(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./explicit.db")
    assert Settings(_env_file=None).database_url == "sqlite:///./explicit.db"
