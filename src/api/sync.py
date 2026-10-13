"""WooCommerce synchronization endpoints and webhook receiver."""

# FastAPI dependency calls are intentionally expressed as parameter defaults.
# ruff: noqa: B008

import base64
import hashlib
import hmac
import json
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.database import get_db
from src.integrations.fake_woo import FakeWooStore
from src.integrations.woo_factory import get_woo_client
from src.models.sync import SyncRecord
from src.repositories.sync_repo import SyncRepository
from src.services.pim_service import NotFoundError
from src.services.woocommerce_sync import (
    WebhookSignatureError,
    WooCommerceSyncService,
)

router = APIRouter(prefix="/sync", tags=["sync"])


def get_sync_service(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Generator[WooCommerceSyncService, None, None]:
    """Build a request scoped WooCommerce sync service."""
    mock_store: FakeWooStore = request.app.state.fake_woo_store
    if mock_store.request_count == 0:
        mock_store.fail_first = max(0, settings.woo_mock_fail_first)
    client = get_woo_client(settings, mock_store)
    webhook_secret = settings.woo_webhook_secret or ("mock-webhook-secret" if settings.woo_mode.lower() == "mock" else "")
    try:
        yield WooCommerceSyncService(session, client, webhook_secret)
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
def sync_status(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List all sync audit records, newest first."""
    return [_record_data(record) for record in SyncRepository(session).list_records()]


@router.get("/status/{product_id}")
def product_sync_status(product_id: int, session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List sync audit records for a product."""
    return [_record_data(record) for record in SyncRepository(session).list_records(product_id)]


@router.get("/mode")
def sync_mode(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Report the configured WooCommerce mode to the browser UI."""
    mode = settings.woo_mode.strip().lower()
    if mode not in {"mock", "live"}:
        raise ValueError("WOO_MODE must be either 'mock' or 'live'")
    return {"mode": mode, "label": "Mock WooCommerce" if mode == "mock" else "Live WooCommerce"}


@router.post("/webhook/simulate")
async def simulate_webhook(request: Request, settings: Settings = Depends(get_settings)) -> JSONResponse:
    """Send a correctly signed demo product.updated event through our webhook endpoint."""
    if settings.woo_mode.strip().lower() != "mock":
        return JSONResponse(status_code=400, content={"error": {"code": "mock_mode_required", "message": "Webhook simulation is available only in mock mode.", "details": None}})
    webhook_secret = settings.woo_webhook_secret or "mock-webhook-secret"
    body = json.dumps({
        "id": 9900,
        "name": "Webhook demo product",
        "sku": "DEMO-WEBHOOK-9900",
        "description": "A product imported through the simulated WooCommerce webhook.",
        "regular_price": "12.00",
        "categories": [{"name": "Demo"}],
        "tags": [{"name": "webhook"}],
        "attributes": [],
        "status": "publish",
        "date_modified": datetime.now(UTC).isoformat(),
    }, separators=(",", ":")).encode()
    signature = base64.b64encode(hmac.new(webhook_secret.encode(), body, hashlib.sha256).digest()).decode()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=request.app), base_url="http://mock-app") as client:
        response = await client.post(
            "/sync/webhook/woocommerce",
            content=body,
            headers={
                "X-WC-Webhook-Signature": signature,
                "X-WC-Webhook-Topic": "product.updated",
                "X-WC-Webhook-Delivery-ID": f"mock-demo-{uuid4().hex}",
            },
        )
    return JSONResponse(status_code=response.status_code, content=response.json())


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
