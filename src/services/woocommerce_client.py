"""Retrying httpx client for the WooCommerce REST API."""

from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)


class WooRequestError(Exception):
    """WooCommerce request failed after the applicable retry policy."""

    def __init__(self, message: str, attempts: int, status_code: int | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.status_code = status_code


def _is_retryable(error: BaseException) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 429 or error.response.status_code >= 500
    return isinstance(error, (httpx.TimeoutException, httpx.NetworkError))


def _retry_wait(retry_state: Any) -> float:
    """Use WooCommerce's Retry-After response header when it is numeric."""
    outcome = retry_state.outcome
    error = outcome.exception() if outcome else None
    retry_after = error.response.headers.get("retry-after") if isinstance(error, httpx.HTTPStatusError) else None
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_time = parsedate_to_datetime(retry_after)
                return max(0.0, (retry_time - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError):
                pass
    return wait_random_exponential(multiplier=0.5, max=8)(retry_state)


class WooCommerceClient:
    """Make authenticated WooCommerce REST API requests with bounded retries."""

    def __init__(
        self,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        timeout: float = 20,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/wp-json/wc/v3",
            auth=(consumer_key, consumer_secret),
            timeout=timeout,
            transport=transport,
        )
        self.sleep = sleep
        self.last_attempts = 0

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Execute a request and decode JSON, retrying only transient failures."""
        self.last_attempts = 0

        def attempt() -> Any:
            self.last_attempts += 1
            response = self.client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None

        retrying = Retrying(
            retry=retry_if_exception(_is_retryable),
            wait=_retry_wait,
            stop=stop_after_attempt(5),
            reraise=True,
            sleep=self.sleep,
        )
        try:
            return retrying(attempt)
        except (httpx.HTTPError, httpx.TimeoutException) as error:
            status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            raise WooRequestError(str(error), self.last_attempts, status_code) from error

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self.client.close()
