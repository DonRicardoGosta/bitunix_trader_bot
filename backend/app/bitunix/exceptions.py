"""Bitunix specifikus kivételek."""

from __future__ import annotations


class BitunixError(Exception):
    """Általános Bitunix hiba."""


class BitunixAPIError(BitunixError):
    """REST/WS hibaválasz."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class BitunixSignatureError(BitunixError):
    """Aláírás generálási hiba (pl. hiányzó kulcsok)."""
