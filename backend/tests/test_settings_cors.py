"""Settings: CORS originek env / .env kompatibilitása (nem JSON list)."""

import pytest

from app.config import Settings


def test_cors_csv_string_parses() -> None:
    s = Settings(backend_cors_origins="http://a.com, http://b.com ")
    assert s.backend_cors_origins == "http://a.com,http://b.com"


def test_cors_json_array_string_parses() -> None:
    s = Settings(backend_cors_origins='["http://x.com", "http://y.com"]')
    assert s.backend_cors_origins == "http://x.com,http://y.com"


def test_cors_list_input_parses() -> None:
    s = Settings(backend_cors_origins=["http://m.com", "http://n.com"])
    assert s.backend_cors_origins == "http://m.com,http://n.com"


def test_cors_empty_env_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "")
    s = Settings()
    assert "localhost" in s.backend_cors_origins


def test_cors_reads_from_os_environ_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS", "http://one.example,http://two.example"
    )
    s = Settings()
    assert "one.example" in s.backend_cors_origins
    assert "two.example" in s.backend_cors_origins
