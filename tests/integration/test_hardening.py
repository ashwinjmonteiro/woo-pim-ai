"""Health, error envelope, and request logging integration tests."""

import logging

from fastapi.testclient import TestClient

from src.main import create_app


def test_health_and_unmatched_routes_use_consistent_envelope(client):
    health = client.get("/health")
    missing = client.get("/unknown-route")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_request_middleware_logs_status_and_unhandled_errors_become_generic(caplog):
    app = create_app(create_tables=False)

    @app.get("/boom")
    def boom():
        raise RuntimeError("private exception message")

    with caplog.at_level(logging.INFO, logger="pim.api"), TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "An unexpected error occurred", "details": None}}
    assert "private exception message" not in response.text
    assert "request failed method=GET path=/boom status=500" in caplog.text
