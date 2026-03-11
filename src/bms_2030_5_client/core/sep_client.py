"""
IEEE 2030.5 Smart Energy Profile HTTP Client.

Provides a clean, reusable HTTP client with mTLS support for
communicating with IEEE 2030.5 servers.

Features:
- mTLS (mutual TLS) authentication with client certificates
- Configurable content type (application/sep+xml by default)
- Clear exception hierarchy for error handling
- Latency tracking for performance monitoring
"""

from __future__ import annotations

import logging
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import httpx

from bms_2030_5_client.runtime_config import ProfileConfig, TLSConfig

logger = logging.getLogger(__name__)


# ============================================
# Response Types
# ============================================

@dataclass
class SepResponse:
    """
    IEEE 2030.5 HTTP response.
    
    Encapsulates the response data with timing information.
    """
    status_code: int
    headers: Dict[str, str]
    body: str
    latency_ms: float
    
    @property
    def is_success(self) -> bool:
        """Check if response was successful (2xx status)."""
        return 200 <= self.status_code < 300
    
    @property
    def is_created(self) -> bool:
        """Check if resource was created (201 status)."""
        return self.status_code == 201
    
    @property
    def is_not_found(self) -> bool:
        """Check if resource was not found (404 status)."""
        return self.status_code == 404
    
    def to_tuple(self) -> Tuple[int, Dict[str, str], str, float]:
        """Convert to tuple (status_code, headers, body, latency_ms)."""
        return (self.status_code, self.headers, self.body, self.latency_ms)


# ============================================
# Exception Hierarchy
# ============================================

class SepClientError(Exception):
    """Base exception for SEP client errors."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause
        self.user_message = message  # Friendly message for UI display
    
    def __str__(self) -> str:
        if self.cause:
            return f"{self.user_message} (原因: {self.cause})"
        return self.user_message


class TLSError(SepClientError):
    """TLS/SSL related errors (certificate issues, handshake failures)."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.user_message = f"TLS 憑證錯誤: {message}"


class CertificateNotFoundError(TLSError):
    """Certificate or key file not found."""
    
    def __init__(self, path: str, file_type: str = "憑證"):
        super().__init__(f"{file_type}檔案不存在: {path}")
        self.path = path
        self.file_type = file_type


class CertificateInvalidError(TLSError):
    """Certificate is invalid or cannot be loaded."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(f"憑證無效: {message}", cause)


class HandshakeError(TLSError):
    """TLS handshake failed."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(f"TLS 握手失敗: {message}", cause)


class ConnectionError(SepClientError):
    """Network connection errors."""
    
    def __init__(self, message: str, host: str = "", cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.host = host
        self.user_message = f"連線錯誤: {message}"


class HostUnreachableError(ConnectionError):
    """Cannot reach the host."""
    
    def __init__(self, host: str, cause: Optional[Exception] = None):
        super().__init__(f"無法連線到 {host}", host, cause)


class ConnectionRefusedError(ConnectionError):
    """Connection was refused by the server."""
    
    def __init__(self, host: str, port: int, cause: Optional[Exception] = None):
        super().__init__(f"連線被拒絕: {host}:{port}", host, cause)
        self.port = port


class TimeoutError(SepClientError):
    """Request timeout."""
    
    def __init__(self, timeout_seconds: float, operation: str = "請求"):
        super().__init__(f"{operation}逾時 ({timeout_seconds}秒)")
        self.timeout_seconds = timeout_seconds
        self.operation = operation


class HTTPError(SepClientError):
    """HTTP protocol errors."""
    
    def __init__(self, status_code: int, reason: str = "", body: str = ""):
        message = f"HTTP {status_code}"
        if reason:
            message += f": {reason}"
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason
        self.body = body
        self.user_message = f"伺服器回應錯誤: HTTP {status_code} {reason}"


# ============================================
# SEP Client
# ============================================

class SepClient:
    """
    IEEE 2030.5 Smart Energy Profile HTTP Client.
    
    Provides GET, POST, DELETE methods with mTLS support for
    communicating with IEEE 2030.5 servers.
    
    Usage:
        profile = ProfileConfig(
            name="production",
            server_base_url="https://sep.example.com",
            tls=TLSConfig(
                client_cert_path="certs/client.crt",
                client_key_path="certs/client.key",
                ca_bundle_path="certs/ca.crt",
            ),
        )
        
        async with SepClient(profile) as client:
            response = await client.get("/dcap")
            print(response.body)
    """
    
    # Default content type for IEEE 2030.5
    DEFAULT_CONTENT_TYPE = "application/sep+xml"
    
    # Default timeout in seconds
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(
        self,
        profile: ProfileConfig,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize SEP client.
        
        Args:
            profile: Server profile configuration
            timeout: Request timeout in seconds
        """
        self.profile = profile
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
        # Extract settings from profile
        self.base_url = profile.server_base_url.rstrip("/")
        self.content_type = profile.content_type_preference or self.DEFAULT_CONTENT_TYPE
        
        # TLS settings
        self.tls = profile.tls
        self.verify_server = profile.tls.verify_server
    
    async def __aenter__(self) -> "SepClient":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    def _validate_certificates(self) -> None:
        """
        Validate that all certificate files exist.
        
        Raises:
            CertificateNotFoundError: If any certificate file is missing
        """
        cert_path = Path(self.tls.client_cert_path)
        key_path = Path(self.tls.client_key_path)
        ca_path = Path(self.tls.ca_bundle_path)
        
        if not cert_path.exists():
            raise CertificateNotFoundError(str(cert_path), "用戶端憑證")
        if not key_path.exists():
            raise CertificateNotFoundError(str(key_path), "用戶端私鑰")
        if self.verify_server and not ca_path.exists():
            raise CertificateNotFoundError(str(ca_path), "CA 憑證")
    
    def _create_ssl_context(self) -> Union[ssl.SSLContext, bool]:
        """
        Create SSL context for mTLS.
        
        Returns:
            SSL context or False if verification disabled
            
        Raises:
            CertificateInvalidError: If certificates cannot be loaded
        """
        if not self.verify_server:
            return False
        
        try:
            ctx = ssl.create_default_context(
                cafile=str(self.tls.ca_bundle_path)
            )
            return ctx
        except ssl.SSLError as e:
            raise CertificateInvalidError(f"無法載入 CA 憑證: {e}", e)
        except Exception as e:
            raise CertificateInvalidError(str(e), e)
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default HTTP headers."""
        return {
            "Accept": self.content_type,
            "Content-Type": self.content_type,
        }
    
    async def connect(self) -> None:
        """
        Establish connection to the server.
        
        Validates certificates and creates the HTTP client.
        
        Raises:
            CertificateNotFoundError: If certificate files are missing
            CertificateInvalidError: If certificates are invalid
        """
        if self._client is not None:
            return
        
        # Validate certificate files
        self._validate_certificates()
        
        # Create SSL context
        ssl_context = self._create_ssl_context()
        
        # Create HTTP client with mTLS
        try:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                verify=ssl_context,
                cert=(
                    str(self.tls.client_cert_path),
                    str(self.tls.client_key_path),
                ),
                timeout=self.timeout,
                headers=self._get_default_headers(),
            )
            logger.info(f"SepClient connected to {self.base_url}")
        except Exception as e:
            raise ConnectionError(f"無法建立 HTTP client: {e}", self.base_url, e)
    
    async def close(self) -> None:
        """Close the connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info(f"SepClient disconnected from {self.base_url}")
    
    def _handle_exception(self, e: Exception, uri: str) -> SepClientError:
        """
        Convert httpx exceptions to SepClient exceptions.
        
        Args:
            e: Original exception
            uri: Request URI for context
            
        Returns:
            Appropriate SepClientError subclass
        """
        # TLS/SSL errors
        if isinstance(e, ssl.SSLError):
            if "certificate" in str(e).lower():
                return CertificateInvalidError(str(e), e)
            return HandshakeError(str(e), e)
        
        # Connection errors
        if isinstance(e, httpx.ConnectError):
            error_str = str(e).lower()
            if "refused" in error_str:
                # Extract host and port from base_url
                from urllib.parse import urlparse
                parsed = urlparse(self.base_url)
                return ConnectionRefusedError(
                    parsed.hostname or self.base_url,
                    parsed.port or 443,
                    e,
                )
            if "unreachable" in error_str or "no route" in error_str:
                return HostUnreachableError(self.base_url, e)
            return ConnectionError(str(e), self.base_url, e)
        
        # Timeout errors
        if isinstance(e, httpx.TimeoutException):
            return TimeoutError(self.timeout, f"請求 {uri}")
        
        # HTTP status errors
        if isinstance(e, httpx.HTTPStatusError):
            return HTTPError(
                e.response.status_code,
                e.response.reason_phrase,
                e.response.text,
            )
        
        # Generic error
        return SepClientError(f"請求失敗: {e}", e)
    
    async def get(
        self,
        uri: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> SepResponse:
        """
        Perform GET request.
        
        Args:
            uri: Resource URI (relative to base_url)
            headers: Additional headers to include
            
        Returns:
            SepResponse with status, headers, body, and latency
            
        Raises:
            SepClientError: On any error (TLS, connection, timeout)
        """
        if self._client is None:
            await self.connect()
        
        merged_headers = self._get_default_headers()
        if headers:
            merged_headers.update(headers)
        
        start_time = time.perf_counter()
        
        try:
            response = await self._client.get(uri, headers=merged_headers)
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            logger.debug(f"GET {uri} -> {response.status_code} ({latency_ms:.1f}ms)")
            
            return SepResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            raise self._handle_exception(e, uri)
    
    async def post(
        self,
        uri: str,
        body: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> SepResponse:
        """
        Perform POST request.
        
        Args:
            uri: Resource URI (relative to base_url)
            body: Request body (XML string)
            headers: Additional headers to include
            
        Returns:
            SepResponse with status, headers, body, and latency
            
        Raises:
            SepClientError: On any error (TLS, connection, timeout)
        """
        if self._client is None:
            await self.connect()
        
        merged_headers = self._get_default_headers()
        if headers:
            merged_headers.update(headers)
        
        start_time = time.perf_counter()
        
        try:
            response = await self._client.post(
                uri,
                content=body,
                headers=merged_headers,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            logger.debug(f"POST {uri} -> {response.status_code} ({latency_ms:.1f}ms)")
            
            return SepResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            raise self._handle_exception(e, uri)
    
    async def put(
        self,
        uri: str,
        body: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> SepResponse:
        """
        Perform PUT request.
        
        Args:
            uri: Resource URI (relative to base_url)
            body: Request body (XML string)
            headers: Additional headers to include
            
        Returns:
            SepResponse with status, headers, body, and latency
            
        Raises:
            SepClientError: On any error (TLS, connection, timeout)
        """
        if self._client is None:
            await self.connect()
        
        merged_headers = self._get_default_headers()
        if headers:
            merged_headers.update(headers)
        
        start_time = time.perf_counter()
        
        try:
            response = await self._client.put(
                uri,
                content=body,
                headers=merged_headers,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            logger.debug(f"PUT {uri} -> {response.status_code} ({latency_ms:.1f}ms)")
            
            return SepResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            raise self._handle_exception(e, uri)
    
    async def delete(
        self,
        uri: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> SepResponse:
        """
        Perform DELETE request.
        
        Args:
            uri: Resource URI (relative to base_url)
            headers: Additional headers to include
            
        Returns:
            SepResponse with status, headers, body, and latency
            
        Raises:
            SepClientError: On any error (TLS, connection, timeout)
        """
        if self._client is None:
            await self.connect()
        
        merged_headers = self._get_default_headers()
        if headers:
            merged_headers.update(headers)
        
        start_time = time.perf_counter()
        
        try:
            response = await self._client.delete(uri, headers=merged_headers)
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            logger.debug(f"DELETE {uri} -> {response.status_code} ({latency_ms:.1f}ms)")
            
            return SepResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            raise self._handle_exception(e, uri)
    
    async def head(
        self,
        uri: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> SepResponse:
        """
        Perform HEAD request (check resource existence).
        
        Args:
            uri: Resource URI (relative to base_url)
            headers: Additional headers to include
            
        Returns:
            SepResponse with status, headers, empty body, and latency
            
        Raises:
            SepClientError: On any error (TLS, connection, timeout)
        """
        if self._client is None:
            await self.connect()
        
        merged_headers = self._get_default_headers()
        if headers:
            merged_headers.update(headers)
        
        start_time = time.perf_counter()
        
        try:
            response = await self._client.head(uri, headers=merged_headers)
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            logger.debug(f"HEAD {uri} -> {response.status_code} ({latency_ms:.1f}ms)")
            
            return SepResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body="",
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            raise self._handle_exception(e, uri)
