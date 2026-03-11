"""
Core modules for BMS IEEE 2030.5 Client.

This package contains the foundational components:
- sep_client: IEEE 2030.5 HTTP client with mTLS support
"""

from bms_2030_5_client.core.sep_client import (
    SepClient,
    SepResponse,
    SepClientError,
    TLSError,
    CertificateNotFoundError,
    CertificateInvalidError,
    HandshakeError,
    ConnectionError,
    HostUnreachableError,
    ConnectionRefusedError,
    TimeoutError,
    HTTPError,
)

__all__ = [
    # Client
    "SepClient",
    "SepResponse",
    # Exceptions
    "SepClientError",
    "TLSError",
    "CertificateNotFoundError",
    "CertificateInvalidError",
    "HandshakeError",
    "ConnectionError",
    "HostUnreachableError",
    "ConnectionRefusedError",
    "TimeoutError",
    "HTTPError",
]
