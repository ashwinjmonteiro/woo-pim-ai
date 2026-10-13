"""WooCommerce sync and retry integration tests with respx HTTP mocks."""

from datetime import UTC, datetime

import respx
from httpx import Response

from src.models.product import Product
from src.services.pim_service import PimService
from src.services.woocommerce_client import WooCommerceClient
from src.services.woocommerce_sync import WooCommerceSyncService

WOO_URL = "https://woo.test/wp-json/wc/v3"


def _client():
    return WooCommerceClient("https://woo.test", "key", "secret", sleep=lambda _: None)


def _service(session_factory):
    session = session_factory()
    return session, WooCommerceSyncService(session, _client(), "test-webhook-secret")


def _valid_product(service):
    return service.create_product({"sku": "SKU-1", "title": "Wireless Mouse", "description": "A useful mouse", "price": 19.99, "tags": ["wireless"], "category": "Electronics", "attributes": {}, "status": "draft"})


def test_push_create_and_update_map_payload_and_store_woo_id(session_factory):
    with respx.mock(base_url=WOO_URL) as router:
        post_route = router.post("/products").mock(return_value=Response(201, json={"id": 123}))
        put_route = router.put("/products/123").mock(return_value=Response(200, json={"id": 123}))
        session, service = _service(session_factory)
        try:
            product = _valid_product(PimService(session))
            created = service.push_product(product.id)
            assert created.status == "success"
            assert created.attempts == 1
            assert post_route.calls.last.request.read()
            assert session.get(Product, product.id).woo_id == 123
            updated = service.push_product(product.id)
            assert updated.status == "success"
            assert put_route.called
        finally:
            session.close()


def test_retry_503_then_success_records_actual_attempts(session_factory):
    with respx.mock(base_url=WOO_URL) as router:
        router.post("/products").mock(side_effect=[Response(503), Response(201, json={"id": 5})])
        session, service = _service(session_factory)
        try:
            product = _valid_product(PimService(session))
            record = service.push_product(product.id)
            assert record.status == "success"
            assert record.attempts == 2
        finally:
            session.close()


def test_retry_exhaustion_records_failed_sync(session_factory):
    with respx.mock(base_url=WOO_URL) as router:
        route = router.post("/products").mock(return_value=Response(503, text="down"))
        session, service = _service(session_factory)
        try:
            product = _valid_product(PimService(session))
            record = service.push_product(product.id)
            assert record.status == "failed"
            assert record.attempts == 5
            assert route.call_count == 5
        finally:
            session.close()


def test_400_is_not_retried(session_factory):
    with respx.mock(base_url=WOO_URL) as router:
        route = router.post("/products").mock(return_value=Response(400, json={"message": "invalid"}))
        session, service = _service(session_factory)
        try:
            record = service.push_product(_valid_product(PimService(session)).id)
            assert record.status == "failed"
            assert record.attempts == 1
            assert route.call_count == 1
        finally:
            session.close()


def test_429_honors_retry_after_header(session_factory):
    waits = []
    client = WooCommerceClient("https://woo.test", "key", "secret", sleep=waits.append)
    with respx.mock(base_url=WOO_URL) as router:
        route = router.post("/products").mock(side_effect=[Response(429, headers={"Retry-After": "0"}), Response(201, json={"id": 9})])
        session = session_factory()
        try:
            service = WooCommerceSyncService(session, client)
            record = service.push_product(_valid_product(PimService(session)).id)
            assert record.status == "success"
            assert route.call_count == 2
            assert waits == [0.0]
        finally:
            session.close()


def test_invalid_payload_is_blocked_before_http_and_a_failed_record_is_written(session_factory):
    with respx.mock(base_url=WOO_URL, assert_all_called=False) as router:
        route = router.post("/products").mock(return_value=Response(201, json={"id": 1}))
        session = session_factory()
        try:
            product = PimService(session).create_product({"sku": "BAD", "title": "Incomplete"})
            record = WooCommerceSyncService(session, _client()).push_product(product.id)
            assert record.status == "failed"
            assert "Invalid product" in record.error
            assert record.attempts == 0
            assert route.call_count == 0
        finally:
            session.close()


def test_pull_upserts_by_sku_and_uses_last_write_wins_with_pim_ties(session_factory):
    item = {"id": 42, "sku": "SKU-1", "name": "Woo title", "description": "Woo desc", "regular_price": "10.5", "date_modified": "2025-01-01T00:00:00Z", "categories": [{"name": "Office"}], "tags": [{"name": "office"}], "attributes": [], "status": "publish"}
    with respx.mock(base_url=WOO_URL) as router:
        router.get("/products").mock(return_value=Response(200, json=[item]))
        session, service = _service(session_factory)
        try:
            existing = PimService(session).create_product({"sku": "SKU-1", "title": "PIM title", "description": "PIM desc", "category": "PIM", "status": "draft"})
            existing.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
            session.commit()
            record = service.pull_products()[0]
            assert record.status == "success"
            assert session.get(Product, existing.id).title == "PIM title"
            item["date_modified"] = "2999-01-01T00:00:00Z"
            router.get("/products").mock(return_value=Response(200, json=[item]))
            service.pull_products()
            assert session.get(Product, existing.id).title == "Woo title"
            assert session.get(Product, existing.id).woo_id == 42
        finally:
            session.close()


def test_webhook_signature_idempotency_and_ping(client):
    import base64
    import hashlib
    import hmac

    body = b'{"id": 8, "sku": "WEB-8", "name": "Webhook Mouse", "description": "From Woo", "date_modified": "2999-01-01T00:00:00Z", "status": "publish"}'
    signature = base64.b64encode(hmac.new(b"test-webhook-secret", body, hashlib.sha256).digest()).decode()
    headers = {"X-WC-Webhook-Signature": signature, "X-WC-Webhook-Topic": "product.created", "X-WC-Webhook-Delivery-ID": "delivery-8"}
    first = client.post("/sync/webhook/woocommerce", content=body, headers=headers)
    second = client.post("/sync/webhook/woocommerce", content=body, headers=headers)
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "duplicate"
    assert client.post("/sync/webhook/woocommerce", content=b"{}").json()["status"] == "ping"


def test_invalid_webhook_signature_is_rejected(client):
    response = client.post("/sync/webhook/woocommerce", content=b"{}", headers={"X-WC-Webhook-Topic": "product.created", "X-WC-Webhook-Signature": "bad"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_webhook_signature"


def test_end_to_end_enrich_then_push_and_record_sync(client):
    with respx.mock(base_url=WOO_URL) as router:
        route = router.post("/products").mock(return_value=Response(201, json={"id": 875}))
        enriched = client.post("/ai/enrich?persist=true", json={"title": "Wireless Ergonomic Mouse"})
        product_id = enriched.json()["persisted"]["id"]
        pushed = client.post(f"/sync/push/{product_id}")
        assert pushed.json()["status"] == "success"
        assert pushed.json()["attempts"] == 1
        assert route.called
        assert client.get(f"/sync/status/{product_id}").json()[0]["status"] == "success"
