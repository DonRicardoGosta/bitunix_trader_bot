"""Bitunix specifikus kivételek."""

from __future__ import annotations


class BitunixError(Exception):
    """Általános Bitunix hiba."""


class BitunixAPIError(BitunixError):
    """REST/WS hibaválasz.

    A ``response_body`` tartalmazhatja a teljes Bitunix JSON választ
    (code/msg/data/…), hogy az audit / UI ne csak a rövid ``msg``-et mutassa.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        path: str | None = None,
        response_body: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.path = path
        self.response_body = response_body


class BitunixSignatureError(BitunixError):
    """Aláírás generálási hiba (pl. hiányzó kulcsok)."""
