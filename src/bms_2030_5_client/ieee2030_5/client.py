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
    EndDeviceList,
    DER,
    DERList,
    DERCapability,
    DERSettings,
    DERStatus,
    DERAvailability,
    DeviceInformation,
    Time,
    MirrorUsagePoint,
    MirrorUsagePointList,
    MirrorMeterReading,
    MirrorMeterReadingList,
    LogEvent,
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
        server_ca_file: str,
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
            server_ca_file: Path to server CA certificate for verification
            dcap_path: Device capability path
            device_id: Device identifier
        """
        self.server_url = server_url.rstrip("/")
        self.cert_file = Path(cert_file)
        self.key_file = Path(key_file)
        self.ca_file = Path(ca_file)
        self.server_ca_file = Path(server_ca_file)
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
            server_ca_file=config.ieee2030_5.server_ca_file,
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
                (self.server_ca_file, "Server CA certificate"),
            ]:
                if not path.exists():
                    raise AuthenticationError(f"{name} not found: {path}")

            # ssl_context = self._create_ssl_context()
            
            self._client = httpx.AsyncClient(
                base_url=self.server_url,
                verify=ssl.create_default_context(cafile=str(self.server_ca_file)),
                cert=(str(self.cert_file), str(self.key_file)),
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
            logger.debug(f"POST {path} Request:\n{xml_data}")
            response = await self._client.post(path, content=xml_data)
            logger.debug(f"POST {path} Response Status: {response.status_code}")
            logger.debug(f"POST {path} Response Body:\n{response.text}")
            response.raise_for_status()
            
            location = response.headers.get("Location", "")
            
            if response_type and response.text:
                result = xml_to_dataclass(response.text, response_type)
            else:
                result = None
                
            return result, location
            
        except httpx.HTTPStatusError as e:
            logger.error(f"POST {path} Request:\n{xml_data}")
            logger.error(f"POST {path} Response Status: {e.response.status_code}")
            logger.error(f"POST {path} Response Body:\n{e.response.text}")
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
            logger.debug(f"PUT {path} XML:\n{xml_data}")
            response = await self._client.put(path, content=xml_data)
            response.raise_for_status()
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"PUT error: {e.response.status_code}")
            logger.error(f"PUT request XML: {xml_data}")
            logger.error(f"Response body: {e.response.text}")
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
        
        return await self._get(time_link.href, Time)

    async def register_end_device(self, pin: int) -> EndDevice:
        """
        Register end device with server.
        
        First checks if device is already registered by fetching the EndDeviceList
        and comparing sFDI. If already registered, returns the existing device.
        Otherwise, proceeds with registration.
        
        Args:
            pin: Device PIN for registration
            
        Returns:
            Registered EndDevice
        """
        if not self._device_capability:
            await self.get_device_capability()

        edev_list_link = self._device_capability.EndDeviceListLink
        
        # Check if device is already registered by fetching EndDeviceList
        try:
            edev_list = await self._get(edev_list_link.href)
            # Search for existing device with matching sFDI
            if hasattr(edev_list, 'EndDevice') and edev_list.EndDevice:
                for existing_device in edev_list.EndDevice:
                    if existing_device.sFDI == self.sfdi:
                        logger.info(f"Device already registered with sFDI: {self.sfdi}")
                        self._end_device = existing_device
                        return self._end_device
        except IEEE2030_5ClientError as e:
            logger.debug(f"Could not fetch EndDeviceList: {e}, proceeding with registration")

        # Device not found, proceed with registration
        logger.info(f"Registering new device with sFDI: {self.sfdi}")
        end_device = EndDevice(
            sFDI=self.sfdi,
            changedTime=int(datetime.now().timestamp()),
        )
        
        _, location = await self._post(edev_list_link.href, end_device)
        
        if location:
            self._end_device = await self._get(location, EndDevice)
            return self._end_device
        
        raise IEEE2030_5ClientError("Registration failed: no location returned")

    async def find_end_device_by_sfdi(self) -> Optional[EndDevice]:
        """
        Find existing EndDevice by sFDI.
        
        Searches the EndDeviceList for a device matching this client's sFDI.
        
        Returns:
            EndDevice if found, None otherwise
        """
        if not self._device_capability:
            await self.get_device_capability()

        edev_list_link = self._device_capability.EndDeviceListLink
        if not edev_list_link:
            logger.warning("EndDeviceListLink not available")
            return None
        
        try:
            edev_list = await self._get(edev_list_link.href, EndDeviceList)
            if edev_list.EndDevice:
                # Handle both single EndDevice and list of EndDevices
                devices = edev_list.EndDevice if isinstance(edev_list.EndDevice, list) else [edev_list.EndDevice]
                for edev in devices:
                    if edev.sFDI == self.sfdi:
                        logger.info(f"Found EndDevice with sFDI {self.sfdi} at {edev.href}")
                        self._end_device = edev
                        return edev
            logger.debug(f"No EndDevice found with sFDI: {self.sfdi}")
            return None
        except IEEE2030_5ClientError as e:
            logger.warning(f"Could not fetch EndDeviceList: {e}")
            return None

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
            der_list = await self._get(self._end_device.DERListLink.href, DERList)
            # Handle both single DER and list of DERs (same issue as EndDevice)
            if der_list.DER:
                return der_list.DER if isinstance(der_list.DER, list) else [der_list.DER]
        return []

    async def get_or_create_der(self, description: str = "Battery Energy Storage System") -> Optional[DER]:
        """
        Get existing DER or create a new one.
        
        Args:
            description: DER description
            
        Returns:
            DER resource with href
        """
        if not self._end_device:
            raise IEEE2030_5ClientError("End device not registered")
        
        # Try to get existing DER
        der_list = await self.get_der_list()
        if der_list:
            logger.info(f"Found existing DER: {der_list[0].href}")
            return der_list[0]
        
        # Create new DER if none exists
        if not self._end_device.DERListLink:
            logger.warning("DERListLink not available")
            return None
        
        logger.info("Creating new DER resource...")
        new_der = DER(description=description)
        
        try:
            _, location = await self._post(self._end_device.DERListLink.href, new_der)
            if location:
                # Fetch the created DER to get full details
                created_der = await self._get(location, DER)
                logger.info(f"Created DER at: {created_der.href}")
                return created_der
        except Exception as e:
            logger.error(f"Failed to create DER: {e}")
        
        return None

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

    # =========================================================================
    # Device Information Resources
    # =========================================================================

    async def get_device_information(self, edev_href: str) -> DeviceInformation:
        """
        Get DeviceInformation for an EndDevice.
        
        Args:
            edev_href: EndDevice resource path (e.g., /edev/1)
            
        Returns:
            DeviceInformation resource
        """
        di_path = f"{edev_href}/di"
        return await self._get(di_path, DeviceInformation)

    async def update_device_information(
        self,
        edev_href: str,
        device_info: DeviceInformation,
    ) -> bool:
        """
        Update DeviceInformation for an EndDevice.
        
        Sends device information to the IEEE 2030.5 server including
        manufacturer details, serial number, software version, etc.
        
        Args:
            edev_href: EndDevice resource path (e.g., /edev/1)
            device_info: DeviceInformation object with device details
            
        Returns:
            True if successful
            
        Example:
            device_info = DeviceInformation(
                mfID=12345,
                mfModel="BMS-2000",
                mfSerialNumber="SN-001",
                mfInfo="Battery Storage Unit A",
                swVer="1.0.0",
                primaryPower=PowerSourceType.MAINS,
            )
            await client.update_device_information("/edev/1", device_info)
        """
        di_path = f"{edev_href}/di"
        return await self._put(di_path, device_info)

    async def create_device_information(
        self,
        edev_href: str,
        device_info: DeviceInformation,
    ) -> tuple[DeviceInformation, str]:
        """
        Create DeviceInformation for an EndDevice (POST).
        
        Some servers may require POST to create the DeviceInformation
        resource before it can be updated with PUT.
        
        Args:
            edev_href: EndDevice resource path (e.g., /edev/1)
            device_info: DeviceInformation object with device details
            
        Returns:
            Tuple of (created DeviceInformation, location href)
        """
        di_path = f"{edev_href}/di"
        return await self._post(di_path, device_info, DeviceInformation)

    # =========================================================================
    # Metering / MirrorUsagePoint Resources
    # =========================================================================

    async def get_mirror_usage_point_list(self) -> MirrorUsagePointList:
        """
        Get list of MirrorUsagePoint resources.
        
        Returns:
            MirrorUsagePointList containing all mirror usage points
        """
        if not self._device_capability:
            await self.get_device_capability()
            
        if self._device_capability.MirrorUsagePointListLink:
            return await self._get(
                self._device_capability.MirrorUsagePointListLink.href,
                MirrorUsagePointList,
            )
        raise IEEE2030_5ClientError("MirrorUsagePointListLink not available")

    async def create_mirror_usage_point(
        self,
        mup: MirrorUsagePoint,
    ) -> tuple[MirrorUsagePoint, str]:
        """
        Create a new MirrorUsagePoint (meter) on the server.
        
        This registers a new meter with the server. The server will
        return a location header with the href for the created resource.
        
        Args:
            mup: MirrorUsagePoint to create
            
        Returns:
            Tuple of (created MirrorUsagePoint, location href)
        """
        if not self._device_capability:
            await self.get_device_capability()
            
        if not self._device_capability.MirrorUsagePointListLink:
            raise IEEE2030_5ClientError("MirrorUsagePointListLink not available")
            
        # Set device LFDI if not already set
        if not mup.deviceLFDI:
            mup.deviceLFDI = self.lfdi
            
        result, location = await self._post(
            self._device_capability.MirrorUsagePointListLink.href,
            mup,
            MirrorUsagePoint,
        )
        
        logger.info(f"Created MirrorUsagePoint at {location}")
        return result, location

    async def get_mirror_usage_point(self, mup_href: str) -> MirrorUsagePoint:
        """
        Get a specific MirrorUsagePoint by href.
        
        Args:
            mup_href: The href of the MirrorUsagePoint
            
        Returns:
            MirrorUsagePoint resource
        """
        return await self._get(mup_href, MirrorUsagePoint)

    async def update_mirror_usage_point(
        self,
        mup_href: str,
        mup: MirrorUsagePoint,
    ) -> bool:
        """
        Update a MirrorUsagePoint on the server (PUT).
        
        This is used to add MirrorMeterReading to an existing MirrorUsagePoint.
        The server requires a two-step process:
        1. POST to create MirrorUsagePoint (without MirrorMeterReading)
        2. PUT to update with MirrorMeterReading
        
        Args:
            mup_href: The href of the MirrorUsagePoint to update
            mup: MirrorUsagePoint with updated data
            
        Returns:
            True if successful
        """
        return await self._put(mup_href, mup)

    async def update_mirror_meter_reading(
        self,
        mup_href: str,
        reading: MirrorMeterReading,
    ) -> bool:
        """
        Update/post a meter reading to a MirrorUsagePoint.
        
        This uploads new reading data to the server.
        
        Args:
            mup_href: The href of the MirrorUsagePoint
            reading: MirrorMeterReading with the new data
            
        Returns:
            True if successful
        """
        # POST to the MirrorUsagePoint to add reading
        try:
            _, location = await self._post(mup_href, reading, None)
            logger.info(f"Posted meter reading to {mup_href}")
            return True
        except Exception as e:
            logger.error(f"Failed to post meter reading: {e}")
            return False

    async def post_meter_readings(
        self,
        mup_href: str,
        readings: list[MirrorMeterReading],
    ) -> bool:
        """
        Post multiple meter readings to a MirrorUsagePoint.
        
        Args:
            mup_href: The href of the MirrorUsagePoint
            readings: List of MirrorMeterReading objects
            
        Returns:
            True if all readings posted successfully
        """
        success = True
        for reading in readings:
            if not await self.update_mirror_meter_reading(mup_href, reading):
                success = False
        return success

    async def post_mirror_meter_reading_list(
        self,
        mup_href: str,
        readings: list[MirrorMeterReading],
    ) -> bool:
        """
        Post a MirrorMeterReadingList to a MirrorUsagePoint.
        
        This method wraps multiple MirrorMeterReading objects in a
        MirrorMeterReadingList and posts them all at once, which is
        more efficient than posting individually.
        
        Args:
            mup_href: The href of the MirrorUsagePoint
            readings: List of MirrorMeterReading objects
            
        Returns:
            True if successful
        """
        if not readings:
            logger.warning("No readings to post")
            return False
        
        # Create MirrorMeterReadingList wrapper
        reading_list = MirrorMeterReadingList(
            all=len(readings),
            results=len(readings),
            MirrorMeterReading=readings,
        )
        
        try:
            _, location = await self._post(mup_href, reading_list, None)
            logger.info(f"Posted MirrorMeterReadingList ({len(readings)} readings) to {mup_href}")
            return True
        except Exception as e:
            logger.error(f"Failed to post MirrorMeterReadingList: {e}")
            return False

    # =========================================================================
    # LogEvent Operations
    # =========================================================================

    async def post_log_event(
        self,
        edev_path: str,
        log_event: LogEvent,
    ) -> bool:
        """
        Post a LogEvent to the server's Log Event List (lel).
        
        Args:
            edev_path: End device path (e.g., "/edev/123")
            log_event: LogEvent object to post
            
        Returns:
            True if successful
        """
        lel_path = f"{edev_path}/lel"
        try:
            _, location = await self._post(lel_path, log_event, None)
            logger.info(
                f"Posted LogEvent: code={log_event.logEventCode}, "
                f"id={log_event.logEventID}, details={log_event.details}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to post LogEvent: {e}")
            return False

    async def post_log_events(
        self,
        edev_path: str,
        log_events: list[LogEvent],
    ) -> bool:
        """
        Post multiple LogEvents to the server.
        
        Args:
            edev_path: End device path (e.g., "/edev/123")
            log_events: List of LogEvent objects
            
        Returns:
            True if all events posted successfully
        """
        success = True
        for event in log_events:
            if not await self.post_log_event(edev_path, event):
                success = False
        return success
