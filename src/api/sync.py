"""WooCommerce synchronization endpoints and webhook receiver."""

# FastAPI dependency calls are intentionally expressed as parameter defaults.
# ruff: noqa: B008

from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.database import get_db
from src.models.sync import SyncRecord
from src.services.pim_service import NotFoundError
from src.services.woocommerce_client import WooCommerceClient
from src.services.woocommerce_sync import WebhookSignatureError, WooCommerceSyncService

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync_service(session: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Generator[WooCommerceSyncService, None, None]:
    """Build a request scoped WooCommerce sync service."""
    client = WooCommerceClient(settings.woo_base_url, settings.woo_consumer_key, settings.woo_consumer_secret)
    try:
        yield WooCommerceSyncService(session, client, settings.woo_webhook_secret)
    finally:
        client.close()


def _record_data(record: SyncRecord) -> dict[str, Any]:
    return {"id": record.id, "product_id": record.product_id, "direction": record.direction, "status": record.status, "attempts": record.attempts, "error": record.error, "created_at": record.created_at.isoformat(), "completed_at": record.completed_at.isoformat() if record.completed_at else None}


@router.post("/push/{product_id}")
def push_product(product_id: int, service: WooCommerceSyncService = Depends(get_sync_service)) -> dict[str, Any]:
    """Push one product to WooCommerce."""
    try:
        return _record_data(service.push_product(product_id))
    except LookupError as error:
        raise NotFoundError(str(error)) from error


@router.post("/push-all")
def push_all(service: WooCommerceSyncService = Depends(get_sync_service)) -> list[dict[str, Any]]:
    """Push all products to WooCommerce."""
    return [_record_data(record) for record in service.push_all()]


@router.post("/pull")
def pull_products(service: WooCommerceSyncService = Depends(get_sync_service)) -> list[dict[str, Any]]:
    """Pull and upsert all pages of WooCommerce products."""
    return [_record_data(record) for record in service.pull_products()]


@router.get("/status")
def sync_status(service: WooCommerceSyncService = Depends(get_sync_service)) -> list[dict[str, Any]]:
    """List all sync audit records, newest first."""
    return [_record_data(record) for record in service.sync_records.list_records()]


@router.get("/status/{product_id}")
def product_sync_status(product_id: int, service: WooCommerceSyncService = Depends(get_sync_service)) -> list[dict[str, Any]]:
    """List sync audit records for a product."""
    return [_record_data(record) for record in service.sync_records.list_records(product_id)]


@router.post("/webhook/woocommerce")
async def woo_webhook(
    request: Request,
    service: WooCommerceSyncService = Depends(get_sync_service),
    signature: str | None = Header(default=None, alias="X-WC-Webhook-Signature"),
    topic: str | None = Header(default=None, alias="X-WC-Webhook-Topic"),
    delivery_id: str | None = Header(default=None, alias="X-WC-Webhook-Delivery-ID"),
) -> JSONResponse:
    """Verify and process an idempotent WooCommerce product webhook."""
    body = await request.body()
    if not topic:
        return JSONResponse({"status": "ping"})
    try:
        service.verify_signature(body, signature)
        result = service.handle_webhook(body, topic, delivery_id)
        return JSONResponse(jsonable_encoder(result))
    except WebhookSignatureError as error:
        return JSONResponse(status_code=401, content={"error": {"code": "invalid_webhook_signature", "message": str(error), "details": None}})
    except (TypeError, ValueError) as error:
        return JSONResponse(status_code=400, content={"error": {"code": "invalid_webhook_payload", "message": str(error), "details": None}})
