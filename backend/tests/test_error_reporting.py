"""Bitunix hibák strukturált naplózáshoz."""

from __future__ import annotations

from app.bitunix.error_reporting import format_strategy_run_error, structured_exception
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError


def test_structured_bitunix_api_error_includes_body() -> None:
    exc = BitunixAPIError(
        "Parameter error [Bitunix code=40001]",
        code="40001",
        path="/api/v1/futures/trade/place_order",
        response_body={"code": 40001, "msg": "Parameter error", "data": {"field": "qty"}},
    )
    d = structured_exception(exc)
    assert d["exception_type"] == "BitunixAPIError"
    assert d["bitunix_code"] == "40001"
    assert d["path"] == "/api/v1/futures/trade/place_order"
    assert d["response_body"]["msg"] == "Parameter error"


def test_format_strategy_run_error_includes_path_and_body_snippet() -> None:
    exc = BitunixAPIError(
        "Parameter error [Bitunix code=40001] | {\"data\": 1}",
        code="40001",
        path="/api/v1/x",
        response_body={"code": 40001, "msg": "Parameter error"},
    )
    s = format_strategy_run_error(exc)
    assert "BitunixAPIError" in s
    assert "path=/api/v1/x" in s
    assert "api_code=40001" in s
    assert "Parameter error" in s


def test_structured_signature_error() -> None:
    exc = BitunixSignatureError("missing key")
    d = structured_exception(exc)
    assert d["exception_type"] == "BitunixSignatureError"
    assert "missing key" in d["message"]
