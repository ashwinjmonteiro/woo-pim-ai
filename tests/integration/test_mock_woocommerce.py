"""Mock WooCommerce workflows through the public HTTP API."""

from src.config import Settings, get_settings


def _settings(client, **changes):
    values = {"woo_mode": "mock", "woo_mock_fail_first": 0, "woo_webhook_secret": "demo-secret"}
    values.update(changes)
    client.app.dependency_overrides[get_settings] = lambda: Settings(**values)


def _product(client, sku="MOCK-MOUSE-001"):
    return client.post("/products", json={
        "sku": sku,
        "title": "Demo Wireless Mouse",
        "description": "A wireless mouse for this mock sync.",
        "price": 25.0,
        "tags": ["wireless"],
        "category": "Accessories",
        "attributes": {},
        "status": "draft",
    }).json()


def test_mock_push_creates_then_updates_same_woo_product(client):
    _settings(client)
    product = _product(client)

    created = client.post(f"/sync/push/{product['id']}").json()
    first = client.get(f"/products/{product['id']}").json()
    assert created["status"] == "success"
    assert first["woo_id"] is not None

    client.patch(f"/products/{product['id']}", json={"title": "Updated Demo Mouse"})
    updated = client.post(f"/sync/push/{product['id']}").json()
    second = client.get(f"/products/{product['id']}").json()
    assert updated["status"] == "success"
    assert second["woo_id"] == first["woo_id"]


def test_mock_pull_imports_seed_products(client):
    _settings(client)

    records = client.post("/sync/pull").json()
    products = client.get("/products?limit=100").json()
    assert len(records) == 3
    assert all(record["status"] == "success" for record in records)
    assert {product["sku"] for product in products} >= {"DEMO-MOUSE-001", "DEMO-KEYBOARD-002", "DEMO-HUB-003"}


def test_mock_retries_first_two_failures_and_records_attempt_count(client):
    _settings(client, woo_mock_fail_first=2)
    product = _product(client)

    record = client.post(f"/sync/push/{product['id']}").json()
    assert record["status"] == "success"
    assert record["attempts"] == 3


def test_live_mode_without_credentials_returns_actionable_configuration_error(client):
    _settings(client, woo_mode="live", woo_base_url="https://your-store.example.com", woo_consumer_key="", woo_consumer_secret="")

    response = client.post("/sync/pull")
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "WooCommerce is not configured. Set WOO_MODE=mock or fill in WOO_BASE_URL, WOO_CONSUMER_KEY and WOO_CONSUMER_SECRET."


def test_simulated_webhook_uses_signed_webhook_handler(client):
    _settings(client)

    response = client.post("/sync/webhook/simulate")
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert client.get("/products").json()[0]["sku"] == "DEMO-WEBHOOK-9900"
