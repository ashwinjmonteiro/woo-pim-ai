"""Product repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.product import Product
from src.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """Product-specific queries."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Product)

    def get_by_sku(self, sku: str) -> Product | None:
        """Return a product matching a SKU."""
        return self.session.scalar(select(Product).where(Product.sku == sku))

    def list_page(self, offset: int, limit: int, status: str | None, category: str | None) -> list[Product]:
        """Return a page of products with optional status and category filters."""
        query = select(Product)
        if status:
            query = query.where(Product.status == status)
        if category:
            query = query.where(Product.category == category)
        return list(self.session.scalars(query.order_by(Product.id).offset(offset).limit(limit)).all())
