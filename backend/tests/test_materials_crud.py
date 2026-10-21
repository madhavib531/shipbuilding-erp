"""Tests for Material CRUD endpoints."""

import pytest
from fastapi import status
from app.models.material import Material, MaterialCategory, MaterialStatusEnum
from app.models.facility import Yard, StorageLocation
from app.models.program import Ship, ShipSeries
from app.models.transaction import MaterialTransaction, TransactionType


class TestMaterialsCRUD:
    """Material CRUD endpoint tests."""

    def test_list_empty(self, client):
        """GET /api/v1/materials - empty database."""
        response = client.get("/api/v1/materials")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["total"] == 0
        assert data["data"]["materials"] == []

    def test_create_material(self, client, db):
        """POST /api/v1/materials - create valid material."""
        # Create prerequisites
        category = MaterialCategory(
            id="STEEL",
            name="Structural Steel",
        )
        yard = Yard(
            id="YARD-1",
            name="Yard 1",
            location="Location",
            capacity=1000.0,
        )
        db.add(category)
        db.add(yard)
        db.commit()

        response = client.post(
            "/api/v1/materials",
            json={
                "id": "MAT-001",
                "name": "Test Material",
                "category_id": "STEEL",
                "batch": "B-001",
                "quantity": 100,
                "available": 80,
                "reserved": 20,
                "unit": "units",
                "yard_id": "YARD-1",
                "actor": "Maya Chen",
            }
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["data"]["id"] == "MAT-001"

    def test_create_duplicate_id(self, client, db):
        """POST /api/v1/materials - duplicate ID error."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        db.add_all([category, yard])
        db.commit()

        # Create first material
        material = Material(
            id="MAT-001",
            name="Material 1",
            category_id="STEEL",
            batch="B-001",
            quantity=100,
            available=100,
            reserved=0,
            unit="units",
            yard_id="YARD-1",
        )
        db.add(material)
        db.commit()

        # Try to create with same ID
        response = client.post(
            "/api/v1/materials",
            json={
                "id": "MAT-001",
                "name": "Material 2",
                "category_id": "STEEL",
                "batch": "B-002",
                "quantity": 100,
                "available": 100,
                "reserved": 0,
                "unit": "units",
                "yard_id": "YARD-1",
            }
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_create_invalid_quantities(self, client, db):
        """POST /api/v1/materials - invalid quantity validation."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        db.add_all([category, yard])
        db.commit()

        response = client.post(
            "/api/v1/materials",
            json={
                "id": "MAT-001",
                "name": "Material 1",
                "category_id": "STEEL",
                "batch": "B-001",
                "quantity": 100,
                "available": 70,
                "reserved": 40,  # 70 + 40 = 110 > 100
                "unit": "units",
                "yard_id": "YARD-1",
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        # Detail is a list of errors from Pydantic validation
        errors = response.json()["detail"]
        assert any("cannot exceed" in str(err.get("msg", "")) for err in errors)

    def test_get_material(self, client, db):
        """GET /api/v1/materials/{id} - retrieve material."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        material = Material(
            id="MAT-001",
            name="Test Material",
            category_id="STEEL",
            batch="B-001",
            quantity=100,
            available=80,
            reserved=20,
            unit="units",
            yard_id="YARD-1",
        )
        db.add_all([category, yard, material])
        db.commit()

        response = client.get("/api/v1/materials/MAT-001")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["id"] == "MAT-001"
        assert data["data"]["name"] == "Test Material"

    def test_get_nonexistent(self, client):
        """GET /api/v1/materials/{id} - 404 for nonexistent."""
        response = client.get("/api/v1/materials/NONEXISTENT")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_with_search(self, client, db):
        """GET /api/v1/materials?search= - search functionality."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        material = Material(
            id="STL-10084",
            name="AH36 Steel Plate",
            category_id="STEEL",
            batch="B-2408-19",
            quantity=100,
            available=80,
            reserved=20,
            unit="sheets",
            yard_id="YARD-1",
        )
        db.add_all([category, yard, material])
        db.commit()

        # Search by ID
        response = client.get("/api/v1/materials?search=STL-10084")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["total"] == 1

        # Search by name
        response = client.get("/api/v1/materials?search=AH36")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["total"] == 1

        # Search by batch
        response = client.get("/api/v1/materials?search=B-2408-19")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["total"] == 1

    def test_update_material(self, client, db):
        """PATCH /api/v1/materials/{id} - update material."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        material = Material(
            id="MAT-001",
            name="Original Name",
            category_id="STEEL",
            batch="B-001",
            quantity=100,
            available=80,
            reserved=20,
            unit="units",
            yard_id="YARD-1",
        )
        db.add_all([category, yard, material])
        db.commit()

        response = client.patch(
            "/api/v1/materials/MAT-001",
            json={"name": "Updated Name"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["name"] == "Updated Name"

    def test_update_nonexistent(self, client):
        """PATCH /api/v1/materials/{id} - 404 for nonexistent."""
        response = client.patch(
            "/api/v1/materials/NONEXISTENT",
            json={"name": "Updated"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_material(self, client, db):
        """DELETE /api/v1/materials/{id} - delete material."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        material = Material(
            id="MAT-001",
            name="Test Material",
            category_id="STEEL",
            batch="B-001",
            quantity=100,
            available=80,
            reserved=20,
            unit="units",
            yard_id="YARD-1",
        )
        db.add_all([category, yard, material])
        db.commit()

        response = client.delete("/api/v1/materials/MAT-001")
        assert response.status_code == status.HTTP_200_OK

        # Verify deleted
        response = client.get("/api/v1/materials/MAT-001")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_nonexistent(self, client):
        """DELETE /api/v1/materials/{id} - 404 for nonexistent."""
        response = client.delete("/api/v1/materials/NONEXISTENT")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_with_transactions(self, client, db):
        """DELETE /api/v1/materials/{id} - prevent if has transactions."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        material = Material(
            id="MAT-001",
            name="Test Material",
            category_id="STEEL",
            batch="B-001",
            quantity=100,
            available=80,
            reserved=20,
            unit="units",
            yard_id="YARD-1",
        )
        transaction = MaterialTransaction(
            id="TXN-001",
            material_id="MAT-001",
            transaction_type=TransactionType.RECEIPT,
            quantity=10,
            unit="units",
            actor="user",
        )
        db.add_all([category, yard, material, transaction])
        db.commit()

        response = client.delete("/api/v1/materials/MAT-001")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "transaction" in response.json()["detail"].lower()

        # Material should still exist
        response = client.get("/api/v1/materials/MAT-001")
        assert response.status_code == status.HTTP_200_OK

    def test_pagination(self, client, db):
        """GET /api/v1/materials - pagination works."""
        category = MaterialCategory(id="STEEL", name="Steel")
        yard = Yard(id="YARD-1", name="Yard 1", location="Loc", capacity=1000.0)
        db.add_all([category, yard])
        db.commit()

        # Create 25 materials
        for i in range(25):
            material = Material(
                id=f"MAT-{i:03d}",
                name=f"Material {i}",
                category_id="STEEL",
                batch=f"B-{i}",
                quantity=100,
                available=80,
                reserved=20,
                unit="units",
                yard_id="YARD-1",
            )
            db.add(material)
        db.commit()

        # Test first page
        response = client.get("/api/v1/materials?skip=0&limit=10")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert len(data["materials"]) == 10
        assert data["total"] == 25

        # Test second page
        response = client.get("/api/v1/materials?skip=10&limit=10")
        data = response.json()["data"]
        assert len(data["materials"]) == 10

        # Test last page (partial)
        response = client.get("/api/v1/materials?skip=20&limit=10")
        data = response.json()["data"]
        assert len(data["materials"]) == 5
