"""Shared repository operations."""

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Provide common session-backed lookup and persistence operations."""

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get(self, object_id: int) -> ModelT | None:
        """Return an entity by its primary key."""
        return self.session.get(self.model, object_id)

    def add(self, entity: ModelT) -> ModelT:
        """Persist an entity and return its refreshed instance."""
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        """Delete an entity and commit the change."""
        self.session.delete(entity)
        self.session.commit()

    def all(self) -> list[ModelT]:
        """Return all entities of the repository's model."""
        return list(self.session.scalars(select(self.model)).all())
