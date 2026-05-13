"""Bitunix Futures REST aláírás generálás.

Hivatalos algoritmus (https://www.bitunix.com/api-docs/futures/common/sign.html):

    digest = SHA256(nonce + timestamp + api_key + queryParams + body)
    sign   = SHA256(digest + secret_key)

Megkötések:
* A ``queryParams`` ASCII sorrendben rendezett ``kulcsÉrtékkulcsÉrtek`` formátum.
* A ``body`` JSON whitespace nélkül legyen.
* A nonce 32 karakter, a timestamp milliszekundum.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Mapping
from typing import Any


def generate_nonce(length: int = 32) -> str:
    """Random hex nonce – alapértelmezetten 32 karakter."""
    return secrets.token_hex(length // 2)


def current_timestamp_ms() -> str:
    """Aktuális Unix idő milliszekundumban, stringként."""
    return str(int(time.time() * 1000))


def canonical_query(params: Mapping[str, Any] | None) -> str:
    """Query paraméterek ASCII rendezett kulcsÉrtékkulcsÉrtek formába."""
    if not params:
        return ""
    parts = []
    for key in sorted(params):
        value = params[key]
        if value is None:
            continue
        parts.append(f"{key}{value}")
    return "".join(parts)


def canonical_body(body: Mapping[str, Any] | None) -> str:
    """JSON body whitespace nélküli reprezentációja."""
    if not body:
        return ""
    return json.dumps(body, separators=(",", ":"), sort_keys=False)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_signature(
    *,
    api_key: str,
    secret_key: str,
    nonce: str,
    timestamp: str,
    query: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
) -> str:
    """Bitunix aláírás (dupla SHA256).

    Args:
        api_key: A Bitunix oldalon kiállított public kulcs.
        secret_key: A privát kulcs (sosem mehet ki a szerverről!).
        nonce: 32 karakteres random string.
        timestamp: Unix ms timestamp string.
        query: Query paraméterek (GET kéréseknél).
        body: JSON body (POST kéréseknél).

    Returns:
        Hexadecimális aláírás string.
    """
    query_str = canonical_query(query)
    body_str = canonical_body(body)
    digest = _sha256_hex(nonce + timestamp + api_key + query_str + body_str)
    return _sha256_hex(digest + secret_key)


def build_auth_headers(
    *,
    api_key: str,
    secret_key: str,
    query: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> dict[str, str]:
    """Komplett HTTP header set egy autentikált REST hívásra."""
    nonce = nonce or generate_nonce()
    timestamp = timestamp or current_timestamp_ms()
    sign = build_signature(
        api_key=api_key,
        secret_key=secret_key,
        nonce=nonce,
        timestamp=timestamp,
        query=query,
        body=body,
    )
    return {
        "api-key": api_key,
        "nonce": nonce,
        "timestamp": timestamp,
        "sign": sign,
        "Content-Type": "application/json",
    }
