"""PIM service validation and CRUD tests."""

import pytest

from src.services.pim_service import (
    AttributeValidationError,
    ConflictError,
    NotFoundError,
    PimService,
)


def test_create_product_validates_required_enum_attributes(session_factory):
    with session_factory() as session:
        service = PimService(session)
        service.create_attribute({"name": "color", "type": "enum", "required": True, "allowed_values": ["black", "white"], "category_scope": "Mice"})
        with pytest.raises(AttributeValidationError):
            service.create_product({"sku": "M-1", "title": "Mouse", "category": "Mice", "attributes": {"color": "blue"}})
        product = service.create_product({"sku": "M-1", "title": "Mouse", "category": "Mice", "attributes": {"color": "black"}})
        assert product.attributes == {"color": "black"}


def test_create_duplicate_sku_and_update_conflict(session_factory):
    with session_factory() as session:
        service = PimService(session)
        one = service.create_product({"sku": "A", "title": "One"})
        service.create_product({"sku": "B", "title": "Two"})
        with pytest.raises(ConflictError):
            service.create_product({"sku": "A", "title": "Duplicate"})
        with pytest.raises(ConflictError):
            service.update_product(one.id, {"sku": "B"})


def test_not_found_for_missing_product(session_factory):
    with session_factory() as session, pytest.raises(NotFoundError):
        PimService(session).get_product(50)
