"""
IEEE 2030.5 HTTPS client for server communication.

Implements TLS mutual authentication and REST operations.
"""

import asyncio
import hashlib
import logging
import ssl
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar
from datetime import datetime

import httpx
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from bms_2030_5_client.config import Config, IEEE2030_5Config
from bms_2030_5_client.models import (
    DeviceCapability,
    EndDevice,
    DER,
    DERCapability,
    DERSettings,
    DERStatus,
    DERAvailability,
    Time,
)
from bms_2030_5_client.ieee2030_5.xml_utils import (
    dataclass_to_xml,
    xml_to_dataclass,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class IEEE2030_5ClientError(Exception):
    """IEEE 2030.5 client error."""
    pass


class AuthenticationError(IEEE2030_5ClientError):
    """Authentication/TLS error."""
    pass


class IEEE2030_5Client:
    """
    IEEE 2030.5 HTTPS client.
    
    Handles secure communication with IEEE 2030.5 servers using
    TLS mutual authentication (X.509 certificates).
    """

    def __init__(
        self,
        server_url: str,
        cert_file: str,
        key_file: str,
        ca_file: str,
        dcap_path: str = "/dcap",
        device_id: str = "client",
    ):
        """
        Initialize IEEE 2030.5 client.
        
        Args:
            server_url: Server URL (e.g., https://localhost:7443)
            cert_file: Path to client certificate
            key_file: Path to client private key
            ca_file: Path to CA certificate
            dcap_path: Device capability path
            device_id: Device identifier
        """
        self.server_url = server_url.rstrip("/")
        self.cert_file = Path(cert_file)
        self.key_file = Path(key_file)
        self.ca_file = Path(ca_file)
        self.dcap_path = dcap_path
        self.device_id = device_id
        
        self._client: Optional[httpx.AsyncClient] = None
        self._device_capability: Optional[DeviceCapability] = None
        self._end_device: Optional[EndDevice] = None
        self._lfdi: Optional[str] = None
        self._sfdi: Optional[int] = None

    @classmethod
    def from_config(cls, config: Config) -> "IEEE2030_5Client":
        """Create client from configuration."""
        return cls(
            server_url=config.ieee2030_5.server_url,
            cert_file=config.ieee2030_5.cert_file,
            key_file=config.ieee2030_5.key_file,
            ca_file=config.ieee2030_5.ca_file,
            dcap_path=config.ieee2030_5.dcap_path,
            device_id=config.ieee2030_5.device_id,
        )

    @property
    def lfdi(self) -> Optional[str]:
        """Get Long-Form Device Identifier from certificate."""
        if self._lfdi is None:
            self._lfdi = self._calculate_lfdi()
        return self._lfdi

    @property
    def sfdi(self) -> Optional[int]:
        """Get Short-Form Device Identifier."""
        if self._sfdi is None and self.lfdi:
            self._sfdi = self._calculate_sfdi(self.lfdi)
        return self._sfdi

    def _calculate_lfdi(self) -> str:
        """Calculate LFDI from certificate fingerprint."""
        try:
            with open(self.cert_file, "rb") as f:
                cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            fingerprint = cert.fingerprint(cert.signature_hash_algorithm)
            # LFDI is first 160 bits (40 hex chars) of SHA-256 fingerprint
            return fingerprint.hex()[:40].upper()
        except Exception as e:
            logger.error(f"Failed to calculate LFDI: {e}")
            return ""

    def _calculate_sfdi(self, lfdi: str) -> int:
        """Calculate SFDI from LFDI."""
        # SFDI is first 36 bits of LFDI plus check digit
        hex_str = str(int(lfdi[:9], 16))
        check_bit = 0
        full_sum = sum(int(x) for x in hex_str)
        while (full_sum + check_bit) % 10 != 0:
            check_bit += 1
        return int(hex_str + str(check_bit))

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for mutual TLS authentication."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        
        # Load CA certificate
        ctx.load_verify_locations(cafile=str(self.ca_file))
        
        # Load client certificate and key
        ctx.load_cert_chain(
            certfile=str(self.cert_file),
            keyfile=str(self.key_file),
        )
        
        return ctx

    async def connect(self) -> bool:
        """
        Connect to IEEE 2030.5 server.
        
        Returns:
            True if connection successful
        """
        try:
            # Validate certificate files exist
            for path, name in [
                (self.cert_file, "Certificate"),
                (self.key_file, "Private key"),
                (self.ca_file, "CA certificate"),
            ]:
                if not path.exists():
                    raise AuthenticationError(f"{name} not found: {path}")

            ssl_context = self._create_ssl_context()
            
            self._client = httpx.AsyncClient(
                base_url=self.server_url,
                verify=ssl_context,
                timeout=30.0,
                headers={
                    "Accept": "application/sep+xml",
                    "Content-Type": "application/sep+xml",
                },
            )
            
            # Test connection by fetching device capability
            self._device_capability = await self.get_device_capability()
            logger.info(f"Connected to IEEE 2030.5 server at {self.server_url}")
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from server."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("Disconnected from IEEE 2030.5 server")

    async def _get(
        self,
        path: str,
        response_type: Optional[Type[T]] = None,
    ) -> T:
        """
        Perform GET request.
        
        Args:
            path: Resource path
            response_type: Expected response dataclass type
            
        Returns:
            Parsed response object
        """
        if not self._client:
            raise IEEE2030_5ClientError("Not connected")

        try:
            response = await self._client.get(path)
            response.raise_for_status()
            
            if response_type:
                return xml_to_dataclass(response.text, response_type)
            return response.text
            
        except httpx.HTTPStatusError as e:
            raise IEEE2030_5ClientError(f"HTTP error: {e.response.status_code}") from e
        except Exception as e:
            raise IEEE2030_5ClientError(f"Request failed: {e}") from e

    async def _post(
        self,
        path: str,
        data: Any,
        response_type: Optional[Type[T]] = None,
    ) -> tuple[T, str]:
        """
        Perform POST request.
        
        Args:
            path: Resource path
            data: Data object to post
            response_type: Expected response dataclass type
            
        Returns:
            Tuple of (response object, location header)
        """
        if not self._client:
            raise IEEE2030_5ClientError("Not connected")

        try:
            xml_data = dataclass_to_xml(data)
            response = await self._client.post(path, content=xml_data)
            response.raise_for_status()
            
            location = response.headers.get("Location", "")
            
            if response_type and response.text:
                result = xml_to_dataclass(response.text, response_type)
            else:
                result = None
                
            return result, location
            
        except httpx.HTTPStatusError as e:
            raise IEEE2030_5ClientError(f"HTTP error: {e.response.status_code}") from e

    async def _put(
        self,
        path: str,
        data: Any,
    ) -> bool:
        """
        Perform PUT request.
        
        Args:
            path: Resource path
            data: Data object to put
            
        Returns:
            True if successful
        """
        if not self._client:
            raise IEEE2030_5ClientError("Not connected")

        try:
            xml_data = dataclass_to_xml(data)
            response = await self._client.put(path, content=xml_data)
            response.raise_for_status()
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"PUT error: {e.response.status_code}")
            return False

    # =========================================================================
    # IEEE 2030.5 Resources
    # =========================================================================

    async def get_device_capability(self) -> DeviceCapability:
        """Get device capability resource (entry point)."""
        return await self._get(self.dcap_path, DeviceCapability)

    async def get_time(self) -> Time:
        """Get server time."""
        if not self._device_capability or not self._device_capability.TimeLink:
            dcap = await self.get_device_capability()
            time_link = dcap.TimeLink
        else:
            time_link = self._device_capability.TimeLink
        
        return await self._get(time_link, Time)

    async def register_end_device(self, pin: int) -> EndDevice:
        """
        Register end device with server.
        
        Args:
            pin: Device PIN for registration
            
        Returns:
            Registered EndDevice
        """
        if not self._device_capability:
            await self.get_device_capability()

        end_device = EndDevice(
            sFDI=self.sfdi,
            changedTime=int(datetime.now().timestamp()),
        )
        
        edev_list_link = self._device_capability.EndDeviceListLink
        _, location = await self._post(edev_list_link, end_device)
        
        if location:
            self._end_device = await self._get(location, EndDevice)
            return self._end_device
        
        raise IEEE2030_5ClientError("Registration failed: no location returned")

    async def get_self_device(self) -> EndDevice:
        """Get self device resource."""
        if not self._device_capability:
            await self.get_device_capability()
            
        if self._device_capability.SelfDeviceLink:
            return await self._get(
                self._device_capability.SelfDeviceLink,
                EndDevice,
            )
        raise IEEE2030_5ClientError("SelfDeviceLink not available")

    async def get_der_list(self) -> list:
        """Get DER list for end device."""
        if not self._end_device:
            raise IEEE2030_5ClientError("End device not registered")
        
        if self._end_device.DERListLink:
            # Returns DERList, extract DER items
            return await self._get(self._end_device.DERListLink)
        return []

    async def update_der_status(self, der_path: str, status: DERStatus) -> bool:
        """
        Update DER status on server.
        
        Args:
            der_path: DER resource path
            status: DERStatus object
            
        Returns:
            True if successful
        """
        status_path = f"{der_path}/ders"
        return await self._put(status_path, status)

    async def update_der_availability(
        self,
        der_path: str,
        availability: DERAvailability,
    ) -> bool:
        """
        Update DER availability on server.
        
        Args:
            der_path: DER resource path
            availability: DERAvailability object
            
        Returns:
            True if successful
        """
        avail_path = f"{der_path}/dera"
        return await self._put(avail_path, availability)

    async def update_der_settings(
        self,
        der_path: str,
        settings: DERSettings,
    ) -> bool:
        """
        Update DER settings on server.
        
        Args:
            der_path: DER resource path
            settings: DERSettings object
            
        Returns:
            True if successful
        """
        settings_path = f"{der_path}/derg"
        return await self._put(settings_path, settings)

    async def get_der_capability(self, der_path: str) -> DERCapability:
        """Get DER capability."""
        cap_path = f"{der_path}/dercap"
        return await self._get(cap_path, DERCapability)

    async def get_der_programs(self) -> list:
        """Get DER programs assigned to this device."""
        if not self._device_capability:
            await self.get_device_capability()
            
        if self._device_capability.DERProgramListLink:
            return await self._get(self._device_capability.DERProgramListLink)
        return []
