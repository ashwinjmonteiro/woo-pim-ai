"""Dynamic attribute definition model."""

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AttributeDefinition(Base):
    """Defines an allowed typed attribute for products."""

    __tablename__ = "attribute_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allowed_values: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    category_scope: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
