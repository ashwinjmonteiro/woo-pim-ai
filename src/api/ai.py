"""AI enrichment endpoint."""

# FastAPI dependency calls are intentionally expressed as parameter defaults.
# ruff: noqa: B008

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query

from src.agents.ai_enricher import AIEnricher
from src.api.dependencies import get_pim_service
from src.config import Settings, get_settings
from src.llm.factory import get_llm_client
from src.models.schemas import ProductRead
from src.services.pim_service import PimService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/enrich")
def enrich_product(
    payload: dict[str, Any],
    persist: bool = Query(default=False),
    service: PimService = Depends(get_pim_service),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Enrich a partial product and optionally persist it as enriched."""
    definitions = [
        {"name": item.name, "type": item.type, "required": item.required, "allowed_values": item.allowed_values, "category_scope": item.category_scope}
        for item in service.list_attributes()
    ]
    result = AIEnricher(get_llm_client(settings)).enrich(payload, definitions)
    if persist and result["status"] != "failed":
        product = dict(result["product"])
        product["sku"] = product.get("sku") or f"AI-{uuid4().hex[:10].upper()}"
        product["title"] = product.get("title") or "Enriched product"
        product["status"] = "enriched"
        created = service.create_product({key: product[key] for key in ("sku", "title", "description", "price", "tags", "category", "attributes", "status") if key in product})
        result["persisted"] = ProductRead.from_product(created).model_dump()
    else:
        result["persisted"] = None
    return result
