"""Bitunix / HTTP hibák strukturált formázása audit és UI számára."""

from __future__ import annotations

import json
import traceback
from typing import Any

from app.bitunix.exceptions import BitunixAPIError


def structured_exception(exc: BaseException) -> dict[str, Any]:
    """JSON-kompatibilis dict: ``strategy_run.details['failure']``, audit payload."""
    out: dict[str, Any] = {
        "exception_type": type(exc).__name__,
        "message": str(exc),
    }
    if isinstance(exc, BitunixAPIError):
        out["bitunix_code"] = exc.code
        out["http_status"] = exc.status_code
        out["path"] = exc.path
        out["response_body"] = exc.response_body
    if exc.__cause__ is not None:
        out["cause_type"] = type(exc.__cause__).__name__
        out["cause_message"] = str(exc.__cause__)
    if exc.__traceback__ is not None:
        tb = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        out["traceback"] = tb[-8000:]
    return out


def format_strategy_run_error(exc: BaseException) -> str:
    """Egy soros + rövid kiegészítő szöveg a ``StrategyRun.error`` mezőbe."""
    if isinstance(exc, BitunixAPIError):
        parts = [f"{type(exc).__name__}: {exc}"]
        if exc.path:
            parts.append(f"path={exc.path}")
        if exc.code is not None:
            parts.append(f"api_code={exc.code}")
        if exc.status_code is not None:
            parts.append(f"http={exc.status_code}")
        if exc.response_body is not None:
            try:
                blob = json.dumps(exc.response_body, ensure_ascii=False)[:2000]
            except (TypeError, ValueError):
                blob = repr(exc.response_body)[:2000]
            parts.append(f"body={blob}")
        return " | ".join(parts)
    return f"{type(exc).__name__}: {exc}"
