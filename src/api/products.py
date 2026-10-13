"""Product CRUD endpoints."""

# FastAPI dependency calls are intentionally expressed as parameter defaults.
# ruff: noqa: B008

from fastapi import APIRouter, Depends, Query, Response, status

from src.api.dependencies import get_pim_service
from src.models.schemas import ProductCreate, ProductRead, ProductUpdate
from src.services.pim_service import PimService

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, service: PimService = Depends(get_pim_service)) -> ProductRead:
    """Create a validated catalog product."""
    return ProductRead.from_product(service.create_product(payload.model_dump()))


@router.get("", response_model=list[ProductRead])
def list_products(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    service: PimService = Depends(get_pim_service),
) -> list[ProductRead]:
    """List products with pagination and optional filters."""
    return [ProductRead.from_product(p) for p in service.list_products(offset, limit, status_filter, category)]


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, service: PimService = Depends(get_pim_service)) -> ProductRead:
    """Return one product by identifier."""
    return ProductRead.from_product(service.get_product(product_id))


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, service: PimService = Depends(get_pim_service)) -> ProductRead:
    """Partially update a product."""
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        changes = {key: value for key, value in changes.items() if value is not None}
    return ProductRead.from_product(service.update_product(product_id, changes))


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, service: PimService = Depends(get_pim_service)) -> Response:
    """Delete a product."""
    service.delete_product(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
