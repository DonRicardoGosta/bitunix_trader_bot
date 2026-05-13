"""Bitunix Futures integráció.

Tartalmazza a REST + WebSocket klienst és az aláírási logikát.
A hivatalos dokumentáció: https://openapidoc.bitunix.com/
"""

from app.bitunix.auth import build_signature
from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError

__all__ = [
    "BitunixClient",
    "BitunixAPIError",
    "BitunixSignatureError",
    "build_signature",
]
