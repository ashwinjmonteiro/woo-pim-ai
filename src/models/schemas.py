"""Pydantic API schemas and input validation."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductFields(BaseModel):
    """Fields accepted when creating or updating a product."""

    sku: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    description: str = ""
    price: float | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=256)
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="draft", min_length=1, max_length=32)


class ProductCreate(ProductFields):
    """Product creation payload."""


class ProductUpdate(BaseModel):
    """Partial product update payload."""

    sku: str | None = Field(default=None, min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    tags: list[str] | None = None
    category: str | None = Field(default=None, max_length=256)
    attributes: dict[str, Any] | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)


class ProductRead(ProductFields):
    """Product response schema."""

    id: int
    woo_id: int | None
    updated_at: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_product(cls, product: Any) -> "ProductRead":
        """Serialize a product while normalizing its timestamp."""
        values = {name: getattr(product, name) for name in ProductFields.model_fields}
        values.update(id=product.id, woo_id=product.woo_id, updated_at=product.updated_at.isoformat())
        return cls(**values)


class AttributeCreate(BaseModel):
    """Attribute definition creation payload."""

    name: str = Field(min_length=1, max_length=128)
    type: Literal["string", "number", "boolean", "enum"]
    required: bool = False
    allowed_values: list[str] | None = None
    category_scope: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def enum_values_required(self) -> "AttributeCreate":
        """Require values for enum definitions and reject them for other types."""
        if self.type == "enum" and not self.allowed_values:
            raise ValueError("allowed_values is required for enum attributes")
        if self.type != "enum" and self.allowed_values:
            raise ValueError("allowed_values is only valid for enum attributes")
        return self


class AttributeUpdate(BaseModel):
    """Partial attribute definition update payload."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    type: Literal["string", "number", "boolean", "enum"] | None = None
    required: bool | None = None
    allowed_values: list[str] | None = None
    category_scope: str | None = Field(default=None, max_length=256)


class AttributeRead(BaseModel):
    """Attribute definition response schema."""

    id: int
    name: str
    type: Literal["string", "number", "boolean", "enum"]
    required: bool
    allowed_values: list[str] | None = None
    category_scope: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    """Standard API error envelope."""

    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    """Standard API error response."""

    error: ErrorDetail
