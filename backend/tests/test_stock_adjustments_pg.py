"""PostgreSQL-only: manual stock changes and their ADJUSTMENT ledger entries commit or roll back together
(see tests/pg_support.py; runs in a throwaway schema of the dedicated test database)."""

import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.materials import create_material, update_material
from app.models import Material, MaterialTransaction, TransactionType
from app.schemas.material import MaterialCreate, MaterialUpdate
from app.services import material_service
from tests.pg_support import pg_session_factory, requires_pg
from tests.test_inspections_concurrency_pg import _seed

pytestmark = requires_pg


def _seed_batch(s):
    _seed(s)
    s.add(Material(id="M", name="Plate", category_id="C", batch="B1", unit="sheets",
                   quantity=10, available=8, reserved=2, yard_id="Y", location_id="L"))
    s.commit()


@pytest.fixture
def factory():
    with pg_session_factory("adj_test", _seed_batch) as f:
        yield f


@pytest.fixture
def colliding_ids(factory, monkeypatch):
    """The next ledger entry reuses an existing primary key, so writing it fails."""
    fixed = uuid.UUID(int=0)
    with factory() as s:
        s.add(MaterialTransaction(id=f"TXN-{fixed.hex[:24]}", material_id="M", transaction_type=TransactionType.RECEIPT,
                                  quantity=1, unit="sheets", actor="seed"))
        s.commit()
    monkeypatch.setattr(material_service, "uuid4", lambda: fixed)


def _state(factory, material_id="M"):
    with factory() as s:
        m = s.get(Material, material_id)
        rows = s.query(MaterialTransaction).filter_by(material_id=material_id).all()
        return (m.quantity, m.available, m.reserved, m.version) if m else None, sorted((r.transaction_type.name, r.quantity) for r in rows)


def _new(**over):
    data = {"id": "N", "name": "New", "category_id": "C", "batch": "B", "unit": "u", "yard_id": "Y", "location_id": "L",
            "quantity": 5, "available": 4, "reserved": 1, "actor": "Ola", "stock_reason": "Migrated"}
    data.update(over)
    return MaterialCreate(**data)


def test_edit_and_adjustment_commit_together(factory):
    with factory() as s:
        update_material("M", MaterialUpdate(quantity=7, available=5, actor="Ola", stock_reason="Water damage"), db=s)
    with factory() as s:
        row = s.query(MaterialTransaction).filter_by(material_id="M").one()
        assert (row.transaction_type, row.quantity, row.from_location_id, row.reason) == (
            TransactionType.ADJUSTMENT, -3, "L", "On hand 10→7, available 8→5 — Water damage")
    assert _state(factory)[0] == (7, 5, 2, 2)


def test_failed_ledger_write_rolls_back_the_edit(factory, colliding_ids):
    before = _state(factory)
    with factory() as s:
        with pytest.raises(HTTPException) as failed:
            update_material("M", MaterialUpdate(quantity=15, available=13, actor="Ola", stock_reason="count"), db=s)
    assert failed.value.status_code == 500
    assert _state(factory) == before


def test_create_records_the_opening_balance(factory):
    with factory() as s:
        create_material(_new(), db=s)
    with factory() as s:
        row = s.query(MaterialTransaction).filter_by(material_id="N").one()
        assert (row.transaction_type, row.quantity, row.to_location_id, row.actor, row.reason) == (
            TransactionType.ADJUSTMENT, 5, "L", "Ola", "Opening balance: on hand 5, available 4, reserved 1 — Migrated")


def test_failed_ledger_write_rolls_back_the_create(factory, colliding_ids):
    with factory() as s:
        with pytest.raises(HTTPException) as failed:
            create_material(_new(), db=s)
    assert failed.value.status_code == 500
    assert _state(factory, "N") == (None, [])
