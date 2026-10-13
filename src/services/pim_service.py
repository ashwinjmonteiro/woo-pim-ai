"""Product and dynamic attribute business rules."""

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.attribute import AttributeDefinition
from src.models.product import Product
from src.repositories.attribute_repo import AttributeRepository
from src.repositories.product_repo import ProductRepository


class PimError(Exception):
    """Base error for expected PIM service failures."""

    code = "pim_error"

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(PimError):
    """Requested entity does not exist."""

    code = "not_found"


class ConflictError(PimError):
    """Unique product or attribute key already exists."""

    code = "conflict"


class AttributeValidationError(PimError):
    """Product attributes do not satisfy their definitions."""

    code = "attribute_validation_error"


class PimService:
    """Apply PIM validation and coordinate repository operations."""

    def __init__(self, session: Session) -> None:
        self.products = ProductRepository(session)
        self.attributes = AttributeRepository(session)
        self.session = session

    def create_attribute(self, values: dict[str, Any]) -> AttributeDefinition:
        """Create a unique dynamic attribute definition."""
        if self.attributes.get_by_name(values["name"]):
            raise ConflictError(f"Attribute '{values['name']}' already exists")
        return self.attributes.add(AttributeDefinition(**values))

    def list_attributes(self) -> list[AttributeDefinition]:
        """List all dynamic attribute definitions."""
        return self.attributes.all()

    def get_attribute(self, attribute_id: int) -> AttributeDefinition:
        """Get a definition or raise a not found error."""
        attribute = self.attributes.get(attribute_id)
        if attribute is None:
            raise NotFoundError(f"Attribute {attribute_id} was not found")
        return attribute

    def update_attribute(self, attribute_id: int, changes: dict[str, Any]) -> AttributeDefinition:
        """Update a definition while preserving its type and uniqueness rules."""
        attribute = self.get_attribute(attribute_id)
        merged = {key: getattr(attribute, key) for key in ("name", "type", "required", "allowed_values", "category_scope")}
        merged.update(changes)
        if merged["type"] == "enum" and not merged["allowed_values"]:
            raise AttributeValidationError("Enum attributes require allowed_values")
        if merged["type"] != "enum" and merged["allowed_values"]:
            raise AttributeValidationError("allowed_values is only valid for enum attributes")
        duplicate = self.attributes.get_by_name(merged["name"])
        if duplicate is not None and duplicate.id != attribute.id:
            raise ConflictError(f"Attribute '{merged['name']}' already exists")
        for key, value in changes.items():
            setattr(attribute, key, value)
        try:
            self.session.commit()
            self.session.refresh(attribute)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Attribute conflicts with an existing definition") from exc
        return attribute

    def delete_attribute(self, attribute_id: int) -> None:
        """Delete an attribute definition."""
        self.attributes.delete(self.get_attribute(attribute_id))

    def validate_attributes(self, values: dict[str, Any], category: str | None) -> None:
        """Validate supplied and required product attributes against definitions."""
        errors: list[dict[str, str]] = []
        definitions = self.attributes.all()
        applicable = [d for d in definitions if d.category_scope is None or d.category_scope == category]
        by_name = {d.name: d for d in applicable}
        for name in values:
            if name not in by_name:
                errors.append({"attribute": name, "message": "No applicable attribute definition"})
        for definition in applicable:
            present = definition.name in values
            if definition.required and not present:
                errors.append({"attribute": definition.name, "message": "Required attribute is missing"})
            if present and not self._value_matches(definition, values[definition.name]):
                errors.append({"attribute": definition.name, "message": f"Expected {definition.type}"})
        if errors:
            raise AttributeValidationError("Product attributes are invalid", errors)

    @staticmethod
    def _value_matches(definition: AttributeDefinition, value: Any) -> bool:
        if definition.type == "string":
            return isinstance(value, str)
        if definition.type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if definition.type == "boolean":
            return isinstance(value, bool)
        if definition.type == "enum":
            return isinstance(value, str) and value in (definition.allowed_values or [])
        return False

    def create_product(self, values: dict[str, Any]) -> Product:
        """Validate and create a product."""
        self.validate_attributes(values.get("attributes", {}), values.get("category"))
        if self.products.get_by_sku(values["sku"]):
            raise ConflictError(f"SKU '{values['sku']}' already exists")
        return self.products.add(Product(**values))

    def update_product(self, product_id: int, changes: dict[str, Any]) -> Product:
        """Apply a partial update after validating the final product state."""
        product = self.get_product(product_id)
        merged = {key: getattr(product, key) for key in ("sku", "title", "description", "price", "tags", "category", "attributes", "status")}
        merged.update(changes)
        self.validate_attributes(merged["attributes"], merged["category"])
        duplicate = self.products.get_by_sku(merged["sku"])
        if duplicate is not None and duplicate.id != product.id:
            raise ConflictError(f"SKU '{merged['sku']}' already exists")
        for key, value in changes.items():
            setattr(product, key, value)
        try:
            self.session.commit()
            self.session.refresh(product)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Product conflicts with an existing record") from exc
        return product

    def get_product(self, product_id: int) -> Product:
        """Get a product or raise a not found error."""
        product = self.products.get(product_id)
        if product is None:
            raise NotFoundError(f"Product {product_id} was not found")
        return product

    def list_products(self, offset: int, limit: int, status: str | None, category: str | None) -> list[Product]:
        """List a filtered page of products."""
        return self.products.list_page(offset, limit, status, category)

    def delete_product(self, product_id: int) -> None:
        """Delete a product."""
        self.products.delete(self.get_product(product_id))
