"""WooCommerce push, pull, webhook, and sync audit workflows."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.agents.ai_enricher import AIEnricher
from src.models.attribute import AttributeDefinition
from src.models.product import Product
from src.models.sync import SyncRecord, sync_now
from src.repositories.product_repo import ProductRepository
from src.repositories.sync_repo import SyncRepository
from src.services.pim_service import PimError
from src.services.woocommerce_client import WooCommerceClient, WooRequestError


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class WebhookSignatureError(Exception):
    """WooCommerce webhook signature was missing or invalid."""


class WooCommerceNotConfigured(PimError):
    """WooCommerce credentials or store URL have not been configured."""

    code = "woocommerce_not_configured"


class WooCommerceSyncService:
    """Coordinate Woo API operations with product state and sync history."""

    def __init__(self, session: Session, client: WooCommerceClient, webhook_secret: str = "") -> None:
        self.session = session
        self.client = client
        self.webhook_secret = webhook_secret
        self.products = ProductRepository(session)
        self.sync_records = SyncRepository(session)

    def push_product(self, product_id: int) -> SyncRecord:
        """Validate and push a product, recording success or failure."""
        product = self.products.get(product_id)
        if product is None:
            raise LookupError(f"Product {product_id} was not found")
        definitions = self.session.query(AttributeDefinition).all()
        definition_data = [self._definition_data(item) for item in definitions if item.category_scope is None or item.category_scope == product.category]
        validation = AIEnricher.validate_payload(self._product_data(product), definition_data)
        if not validation["valid"]:
            return self._record(product.id, "push", "failed", 0, f"Invalid product: {validation}")
        payload = self._to_woo_payload(product)
        try:
            if product.woo_id is None:
                response = self.client.request("POST", "/products", json=payload)
            else:
                response = self.client.request("PUT", f"/products/{product.woo_id}", json=payload)
            product.woo_id = int(response["id"])
            record = self._record(product.id, "push", "success", self.client.last_attempts, None)
            return record
        except Exception as error:  # noqa: BLE001 - a sync failure must be persisted as an audit record
            attempts = error.attempts if isinstance(error, WooRequestError) else max(1, self.client.last_attempts)
            return self._record(product.id, "push", "failed", attempts, self._error_message(error))

    def push_all(self) -> list[SyncRecord]:
        """Push every product currently managed by the PIM."""
        return [self.push_product(product.id) for product in self.products.all()]

    def pull_products(self, per_page: int = 100) -> list[SyncRecord]:
        """Fetch Woo products page by page and upsert them by SKU."""
        records: list[SyncRecord] = []
        page = 1
        while True:
            try:
                batch = self.client.request("GET", "/products", params={"page": page, "per_page": per_page})
            except Exception as error:  # noqa: BLE001 - a sync failure must be persisted as an audit record
                attempts = error.attempts if isinstance(error, WooRequestError) else max(1, self.client.last_attempts)
                records.append(self._record(None, "pull", "failed", attempts, self._error_message(error)))
                break
            for item in batch:
                try:
                    product = self._upsert_from_woo(item)
                    records.append(self._record(product.id, "pull", "success", self.client.last_attempts, None))
                except Exception as error:  # noqa: BLE001 - malformed remote products get failed records
                    records.append(self._record(None, "pull", "failed", self.client.last_attempts, str(error)))
            if len(batch) < per_page:
                break
            page += 1
        return records

    def verify_signature(self, body: bytes, signature: str | None) -> None:
        """Verify a base64 HMAC-SHA256 WooCommerce webhook signature."""
        if not self.webhook_secret or not signature:
            raise WebhookSignatureError("Webhook signature or configured secret is missing")
        digest = base64.b64encode(hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(digest, signature):
            raise WebhookSignatureError("Webhook signature is invalid")

    def handle_webhook(self, body: bytes, topic: str, delivery_id: str | None) -> dict[str, Any]:
        """Process one signed, de-duplicated product webhook event."""
        delivery_key = delivery_id or hashlib.sha256(body).hexdigest()
        if self.sync_records.has_delivery(delivery_key):
            return {"status": "duplicate", "delivery_id": delivery_key}
        try:
            item = json.loads(body)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("Webhook body must be valid JSON") from error
        if not isinstance(item, dict):
            raise TypeError("Webhook body must be a JSON object")
        if topic in {"product.created", "product.updated"}:
            product = self._upsert_from_woo(item)
            self._record(product.id, "pull", "success", 1, None)
        elif topic == "product.deleted":
            try:
                woo_id = int(item["id"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("Deleted product webhook is missing a valid id") from error
            product = self.session.query(Product).filter(Product.woo_id == woo_id).first()
            if product is None:
                self._record(None, "pull", "success", 1, None)
            if product is not None:
                product_id = product.id
                self.session.delete(product)
                self._record(product_id, "pull", "success", 1, None)
                self.session.commit()
        self.sync_records.record_delivery(delivery_key, topic)
        return {"status": "processed", "delivery_id": delivery_key}

    def _upsert_from_woo(self, item: dict[str, Any]) -> Product:
        sku = str(item.get("sku") or "").strip()
        if not sku:
            raise ValueError("WooCommerce product is missing SKU")
        if not item.get("id"):
            raise ValueError("WooCommerce product is missing id")
        product = self.products.get_by_sku(sku)
        woo_modified = _parse_datetime(item.get("date_modified_gmt") or item.get("date_modified"))
        if product is None:
            product = Product(sku=sku, title=str(item.get("name") or sku), description=str(item.get("description") or ""), price=self._price(item.get("regular_price")), tags=[tag["name"] for tag in item.get("tags", []) if tag.get("name")], category=(item.get("categories") or [{}])[0].get("name"), attributes={attribute["name"]: self._attribute_value(attribute) for attribute in item.get("attributes", [])}, status="published" if item.get("status") == "publish" else str(item.get("status") or "draft"), woo_id=int(item["id"]))
            if woo_modified is not None:
                product.updated_at = woo_modified
            self.session.add(product)
        elif woo_modified is not None and woo_modified > _as_utc(product.updated_at):
            product.title = str(item.get("name") or product.title)
            product.description = str(item.get("description") or "")
            product.price = self._price(item.get("regular_price"))
            product.tags = [tag["name"] for tag in item.get("tags", []) if tag.get("name")]
            product.category = (item.get("categories") or [{}])[0].get("name")
            product.attributes = {attribute["name"]: self._attribute_value(attribute) for attribute in item.get("attributes", [])}
            product.status = "published" if item.get("status") == "publish" else str(item.get("status") or "draft")
            product.woo_id = int(item["id"])
            product.updated_at = woo_modified
        elif product.woo_id is None:
            product.woo_id = int(item["id"])
        self.session.commit()
        self.session.refresh(product)
        return product

    @staticmethod
    def _price(value: Any) -> float | None:
        return float(value) if value not in (None, "") else None

    @staticmethod
    def _attribute_value(attribute: dict[str, Any]) -> Any:
        options = attribute.get("options") or []
        return options[0] if len(options) == 1 else options

    @staticmethod
    def _definition_data(definition: AttributeDefinition) -> dict[str, Any]:
        return {"name": definition.name, "type": definition.type, "required": definition.required, "allowed_values": definition.allowed_values}

    @staticmethod
    def _product_data(product: Product) -> dict[str, Any]:
        return {"title": product.title, "description": product.description, "category": product.category, "attributes": product.attributes}

    @staticmethod
    def _to_woo_payload(product: Product) -> dict[str, Any]:
        return {
            "name": product.title,
            "sku": product.sku,
            "regular_price": str(product.price) if product.price is not None else "",
            "description": product.description,
            "categories": [{"name": product.category}] if product.category else [],
            "tags": [{"name": tag} for tag in product.tags],
            "attributes": [{"name": name, "options": [str(value)], "visible": True, "variation": False} for name, value in product.attributes.items()],
            "status": "publish" if product.status == "published" else "draft",
        }

    def _record(self, product_id: int | None, direction: str, status: str, attempts: int, error: str | None) -> SyncRecord:
        record = SyncRecord(product_id=product_id, direction=direction, status=status, attempts=attempts, error=error, completed_at=sync_now())
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def _error_message(self, error: Exception) -> str:
        """Replace low-level connection details with a readable store error."""
        if isinstance(error, WooRequestError) and error.status_code is None:
            return f"Could not connect to WooCommerce at {self.client.base_url}"
        return str(error)
