"""Small in-memory WooCommerce REST API used for local demos."""

import json
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

import httpx


def _woo_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "")


class FakeWooStore:
    """Serve the subset of WooCommerce products endpoints used by this app."""

    def __init__(self, fail_first: int = 0) -> None:
        self.fail_first = max(0, fail_first)
        self._request_count = 0
        self._lock = Lock()
        now = datetime.now(UTC)
        self._products: dict[int, dict[str, Any]] = {
            product_id: {
                "id": product_id,
                "name": name,
                "sku": sku,
                "description": description,
                "regular_price": price,
                "categories": [{"id": category_id, "name": category}],
                "tags": [{"id": tag_id, "name": tag} for tag_id, tag in enumerate(tags, 1)],
                "attributes": [],
                "status": "publish",
                "date_modified": _woo_timestamp(now - timedelta(days=2 - index)),
            }
            for index, (product_id, name, sku, description, price, category_id, category, tags) in enumerate(
                [
                    (1001, "Wireless Ergonomic Mouse", "DEMO-MOUSE-001", "A comfortable wireless mouse for everyday work.", "29.99", 11, "Electronics > Accessories", ["wireless", "ergonomic"]),
                    (1002, "Mechanical Keyboard", "DEMO-KEYBOARD-002", "A responsive mechanical keyboard with tactile keys.", "79.00", 12, "Computer Accessories", ["keyboard", "mechanical"]),
                    (1003, "USB-C Hub", "DEMO-HUB-003", "A compact multiport USB-C hub for laptops.", "39.50", 13, "Computer Accessories", ["usb-c", "hub"]),
                ]
            )
        }
        self._next_id = max(self._products) + 1

    @property
    def request_count(self) -> int:
        """Number of requests received by this in-memory store."""
        return self._request_count

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Handle a WooCommerce REST request and return a JSON response."""
        with self._lock:
            self._request_count += 1
            if self._request_count <= self.fail_first:
                return httpx.Response(503, json={"code": "mock_temporary_error", "message": "Temporary mock WooCommerce failure"}, request=request)
            path = request.url.path.rstrip("/")
            if not path.endswith("/products") and "/products/" not in path:
                return httpx.Response(404, json={"message": "Route not found"}, request=request)
            suffix = path.split("/products", 1)[1].strip("/")
            if request.method == "GET" and not suffix:
                page = max(1, int(request.url.params.get("page", "1")))
                per_page = max(1, int(request.url.params.get("per_page", "100")))
                products = sorted(self._products.values(), key=lambda item: item["id"])
                start = (page - 1) * per_page
                return httpx.Response(200, json=products[start : start + per_page], request=request)
            if request.method == "POST" and not suffix:
                data = self._read_json(request)
                product_id = self._next_id
                self._next_id += 1
                product = self._normalize(data, product_id)
                self._products[product_id] = product
                return httpx.Response(201, json=product, request=request)
            try:
                product_id = int(suffix)
            except ValueError:
                return httpx.Response(404, json={"message": "Product not found"}, request=request)
            existing = self._products.get(product_id)
            if existing is None:
                return httpx.Response(404, json={"message": "Product not found"}, request=request)
            if request.method == "PUT":
                product = self._normalize(self._read_json(request), product_id, existing)
                self._products[product_id] = product
                return httpx.Response(200, json=product, request=request)
            if request.method == "DELETE":
                del self._products[product_id]
                return httpx.Response(200, json={"deleted": True, "previous": existing}, request=request)
            if request.method == "GET":
                return httpx.Response(200, json=existing, request=request)
            return httpx.Response(405, json={"message": "Method not allowed"}, request=request)

    @staticmethod
    def _read_json(request: httpx.Request) -> dict[str, Any]:
        data = request.read()
        return json.loads(data) if data else {}

    @staticmethod
    def _normalize(data: dict[str, Any], product_id: int, existing: dict[str, Any] | None = None) -> dict[str, Any]:
        result = dict(existing or {})
        result.update(data)
        result["id"] = product_id
        result["date_modified"] = _woo_timestamp(datetime.now(UTC))
        result.setdefault("categories", [])
        result.setdefault("tags", [])
        result.setdefault("attributes", [])
        result.setdefault("status", "draft")
        return result
