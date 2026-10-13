"""Dynamic attribute definition CRUD endpoints."""

# FastAPI dependency calls are intentionally expressed as parameter defaults.
# ruff: noqa: B008

from fastapi import APIRouter, Depends, Response, status

from src.api.dependencies import get_pim_service
from src.models.schemas import AttributeCreate, AttributeRead, AttributeUpdate
from src.services.pim_service import PimService

router = APIRouter(prefix="/attributes", tags=["attributes"])


@router.post("", response_model=AttributeRead, status_code=status.HTTP_201_CREATED)
def create_attribute(payload: AttributeCreate, service: PimService = Depends(get_pim_service)) -> AttributeRead:
    """Create a typed dynamic attribute definition."""
    return service.create_attribute(payload.model_dump())


@router.get("", response_model=list[AttributeRead])
def list_attributes(service: PimService = Depends(get_pim_service)) -> list[AttributeRead]:
    """List attribute definitions."""
    return service.list_attributes()


@router.get("/{attribute_id}", response_model=AttributeRead)
def get_attribute(attribute_id: int, service: PimService = Depends(get_pim_service)) -> AttributeRead:
    """Return an attribute definition by identifier."""
    return service.get_attribute(attribute_id)


@router.patch("/{attribute_id}", response_model=AttributeRead)
def update_attribute(attribute_id: int, payload: AttributeUpdate, service: PimService = Depends(get_pim_service)) -> AttributeRead:
    """Partially update an attribute definition."""
    changes = payload.model_dump(exclude_unset=True)
    return service.update_attribute(attribute_id, changes)


@router.delete("/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attribute(attribute_id: int, service: PimService = Depends(get_pim_service)) -> Response:
    """Delete an attribute definition."""
    service.delete_attribute(attribute_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
