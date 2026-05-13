"""Bitunix aláírás unit tesztek.

A referencia példa a hivatalos dokumentációból származik:
https://www.bitunix.com/api-docs/futures/common/sign.html
"""

from __future__ import annotations

import hashlib

from app.bitunix.auth import (
    build_signature,
    canonical_body,
    canonical_query,
)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def test_canonical_query_sorted_ascii() -> None:
    """Kulcsok ASCII rendezettek, érték közvetlenül a kulcs után."""
    assert canonical_query({"uid": "200", "id": "1"}) == "id1uid200"


def test_canonical_query_empty() -> None:
    assert canonical_query(None) == ""
    assert canonical_query({}) == ""


def test_canonical_body_no_whitespace() -> None:
    body = {"uid": "2899", "arr": [{"id": 1, "name": "maple"}]}
    rendered = canonical_body(body)
    assert " " not in rendered
    assert rendered == '{"uid":"2899","arr":[{"id":1,"name":"maple"}]}'


def test_build_signature_matches_double_sha256() -> None:
    """Az aláírás ``SHA256(SHA256(nonce+ts+key+q+body) + secret)``."""
    nonce = "abc123"
    timestamp = "1700000000000"
    api_key = "AKEY"
    secret_key = "SKEY"
    query = {"id": "1", "uid": "200"}
    body = {"foo": "bar"}

    expected_digest = _sha256(
        nonce + timestamp + api_key + "id1uid200" + '{"foo":"bar"}'
    )
    expected_sign = _sha256(expected_digest + secret_key)

    actual = build_signature(
        api_key=api_key,
        secret_key=secret_key,
        nonce=nonce,
        timestamp=timestamp,
        query=query,
        body=body,
    )
    assert actual == expected_sign


def test_build_signature_empty_body_and_query() -> None:
    """Üres body+query → csak nonce+ts+api_key megy a digest-be."""
    nonce = "n"
    timestamp = "1"
    api_key = "K"
    secret_key = "S"
    expected_digest = _sha256("n1K")
    expected_sign = _sha256(expected_digest + "S")
    assert (
        build_signature(
            api_key=api_key, secret_key=secret_key, nonce=nonce, timestamp=timestamp
        )
        == expected_sign
    )
