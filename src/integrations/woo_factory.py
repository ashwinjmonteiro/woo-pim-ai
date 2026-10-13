"""Factory for mock and live WooCommerce clients."""

import httpx

from src.config import Settings
from src.integrations.fake_woo import FakeWooStore
from src.services.woocommerce_client import WooCommerceClient
from src.services.woocommerce_sync import WooCommerceNotConfigured

LIVE_CONFIG_ERROR = "WooCommerce is not configured. Set WOO_MODE=mock or fill in WOO_BASE_URL, WOO_CONSUMER_KEY and WOO_CONSUMER_SECRET."


def _live_configuration_is_valid(settings: Settings) -> bool:
    base_url = settings.woo_base_url.strip().rstrip("/")
    hostname = base_url.split("://", 1)[-1].split("/", 1)[0].lower()
    credentials = (settings.woo_consumer_key.strip(), settings.woo_consumer_secret.strip())
    placeholders = hostname in {"your-store.example.com", "example.com", "www.example.com"} or any(
        value.lower() in {"consumer_key", "consumer_secret"}
        or value.lower().startswith("your-")
        or "placeholder" in value.lower()
        for value in credentials
    )
    return bool(base_url and all(credentials) and not placeholders)


def get_woo_client(settings: Settings, mock_store: FakeWooStore | None = None) -> WooCommerceClient:
    """Build a real WooCommerce client configured for live or in-memory mock mode."""
    mode = settings.woo_mode.strip().lower()
    if mode == "mock":
        store = mock_store or FakeWooStore(settings.woo_mock_fail_first)
        return WooCommerceClient(
            "https://mock-woocommerce.local",
            "mock-consumer-key",
            "mock-consumer-secret",
            transport=httpx.MockTransport(store.handle),
        )
    if mode == "live":
        if not _live_configuration_is_valid(settings):
            raise WooCommerceNotConfigured(LIVE_CONFIG_ERROR)
        return WooCommerceClient(settings.woo_base_url, settings.woo_consumer_key, settings.woo_consumer_secret)
    raise ValueError("WOO_MODE must be either 'mock' or 'live'")
