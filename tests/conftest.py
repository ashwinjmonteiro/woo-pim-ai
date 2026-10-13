"""Shared isolated database and API fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import models  # noqa: F401
from src.config import Settings, get_settings
from src.database import Base, get_db
from src.main import create_app


@pytest.fixture
def session_factory():
    """Create an in-memory SQLite database for one test."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    """Build a test client backed by the test database."""
    app = create_app(create_tables=False)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        woo_base_url="https://woo.test",
        woo_consumer_key="test-key",
        woo_consumer_secret="test-secret",
        woo_webhook_secret="test-webhook-secret",
    )
    with TestClient(app) as test_client:
        yield test_client
