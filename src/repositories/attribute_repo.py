"""Attribute definition repository."""

from sqlalchemy import select

from src.models.attribute import AttributeDefinition
from src.repositories.base import BaseRepository


class AttributeRepository(BaseRepository[AttributeDefinition]):
    """Attribute-specific queries."""

    def __init__(self, session):
        super().__init__(session, AttributeDefinition)

    def get_by_name(self, name: str) -> AttributeDefinition | None:
        """Return an attribute definition by its unique name."""
        return self.session.scalar(select(AttributeDefinition).where(AttributeDefinition.name == name))
