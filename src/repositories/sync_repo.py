"""Sync audit and webhook delivery repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.sync import SyncRecord, WebhookEvent
from src.repositories.base import BaseRepository


class SyncRepository(BaseRepository[SyncRecord]):
    """Queries for sync records and webhook idempotency keys."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, SyncRecord)

    def list_records(self, product_id: int | None = None) -> list[SyncRecord]:
        """List sync records, optionally filtered by product."""
        query = select(SyncRecord)
        if product_id is not None:
            query = query.where(SyncRecord.product_id == product_id)
        return list(self.session.scalars(query.order_by(SyncRecord.id.desc())).all())

    def has_delivery(self, delivery_key: str) -> bool:
        """Return whether a webhook delivery key was already processed."""
        return self.session.scalar(select(WebhookEvent.id).where(WebhookEvent.delivery_key == delivery_key)) is not None

    def record_delivery(self, delivery_key: str, topic: str) -> WebhookEvent:
        """Persist a processed webhook delivery key."""
        return self.add(WebhookEvent(delivery_key=delivery_key, topic=topic))
