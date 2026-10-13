"""Production wiring regressions using the real retry callback and client."""

from src.config import Settings, get_settings
from src.services.woocommerce_client import WooCommerceClient
from src.services.woocommerce_sync import WooCommerceSyncService

CONFIG_ERROR = "WooCommerce is not configured. Set WOO_MODE=mock or fill in WOO_BASE_URL, WOO_CONSUMER_KEY and WOO_CONSUMER_SECRET."


def test_push_rejects_missing_woocommerce_configuration(client):
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        woo_mode="live",
        woo_base_url="https://your-store.example.com",
        woo_consumer_key="",
        woo_consumer_secret="",
    )
    response = client.post("/sync/push/1")
    assert response.status_code == 422
    assert response.json()["error"]["message"] == CONFIG_ERROR


def test_pull_rejects_placeholder_woocommerce_url(client):
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        woo_mode="live",
        woo_base_url="https://your-store.example.com",
        woo_consumer_key="consumer-key",
        woo_consumer_secret="consumer-secret",
    )
    response = client.post("/sync/pull")
    assert response.status_code == 422
    assert response.json()["error"]["message"] == CONFIG_ERROR


def test_unreachable_store_uses_default_retry_sleep_and_records_failure(session_factory):
    session = session_factory()
    client = WooCommerceClient(
        "http://127.0.0.1:1",
        "test-key",
        "test-secret",
        timeout=0.1,
    )
    try:
        service = WooCommerceSyncService(session, client)
        records = service.pull_products()
        assert len(records) == 1
        assert records[0].status == "failed"
        assert records[0].direction == "pull"
        assert records[0].attempts == 5
        assert records[0].error == "Could not connect to WooCommerce at http://127.0.0.1:1"
    finally:
        client.close()
        session.close()
