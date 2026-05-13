"""Közös pytest fixture-ök."""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///:memory:"
)
os.environ.setdefault("BITUNIX_API_KEY", "test_api_key")
os.environ.setdefault("BITUNIX_API_SECRET", "test_secret_key")
os.environ.setdefault("BITUNIX_LIVE_TRADING", "false")
os.environ.setdefault("CALIBRATION_ENABLED", "false")
os.environ.setdefault("STRATEGY_RUNNER_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c
