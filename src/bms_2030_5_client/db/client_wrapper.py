"""
Database-integrated IEEE 2030.5 client wrapper.

Provides automatic persistence of IEEE 2030.5 resources to SQLite:
- On connect: Check SQLite for existing data, use cached paths if available
- On registration: Save EndDevice, DER to SQLite
- On resource fetch: Cache responses in SQLite
- Quick path lookup from SQLite instead of server requests

Usage:
    from bms_2030_5_client.db.client_wrapper import DatabaseIEEE2030_5Client
    
    client = DatabaseIEEE2030_5Client(
        ieee_client=ieee_client,
        db_path="data/ieee2030_5.db"
    )
    await client.connect()
    
    # Uses cached path from SQLite if available
    edev = await client.get_or_register_end_device()
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from bms_2030_5_client.db.database import IEEE2030_5Database, init_database
from bms_2030_5_client.db.models import (
    DeviceCapabilityRecord,
    EndDeviceRecord,
    DERRecord,
    MirrorUsagePointRecord,
    MirrorMeterReadingRecord,
    FSARecord,
    DERProgramRecord,
)

if TYPE_CHECKING:
    from bms_2030_5_client.ieee2030_5.client import IEEE2030_5Client
    from bms_2030_5_client.models import (
        DeviceCapability,
        EndDevice,
        DER,
        MirrorUsagePoint,
        MirrorMeterReading,
    )

logger = logging.getLogger(__name__)


class DatabaseIEEE2030_5Client:
    """
    IEEE 2030.5 client wrapper with SQLite persistence.
    
    Wraps the base IEEE2030_5Client to provide:
    - Automatic caching of resources to SQLite
    - Quick path lookup from database
    - Offline-capable path resolution
    - Automatic resource synchronization
    
    Flow:
    1. On connect: Load DeviceCapability, check for cached EndDevice
    2. If cached EndDevice exists with matching sFDI: Use cached paths
    3. If not cached: Register with server, save to SQLite
    4. All subsequent operations use cached paths for quick access
    """
    
    def __init__(
        self,
        ieee_client: "IEEE2030_5Client",
        db_path: str = "data/ieee2030_5.db",
    ):
        """
        Initialize database-integrated client.
        
        Args:
            ieee_client: Base IEEE 2030.5 client
            db_path: Path to SQLite database
        """
        self.ieee_client = ieee_client
        self.db = init_database(db_path)
        
        # Cached resources
        self._device_capability: Optional[DeviceCapabilityRecord] = None
        self._end_device: Optional[EndDeviceRecord] = None
        self._der: Optional[DERRecord] = None
        
        logger.info(f"DatabaseIEEE2030_5Client initialized with db: {db_path}")
    
    @property
    def lfdi(self) -> Optional[str]:
        """Get LFDI from underlying client."""
        return self.ieee_client.lfdi
    
    @property
    def sfdi(self) -> Optional[int]:
        """Get sFDI from underlying client."""
        return self.ieee_client.sfdi
    
    @property
    def end_device(self) -> Optional[EndDeviceRecord]:
        """Get cached EndDevice record."""
        return self._end_device
    
    @property
    def end_device_href(self) -> Optional[str]:
        """Get EndDevice href path."""
        if self._end_device:
            return self._end_device.href
        if self.ieee_client._end_device:
            return self.ieee_client._end_device.href
        return None
    
    @property
    def der(self) -> Optional[DERRecord]:
        """Get cached DER record."""
        return self._der
    
    @property
    def der_href(self) -> Optional[str]:
        """Get DER href path."""
        if self._der:
            return self._der.href
        return None
    
    async def connect(self) -> bool:
        """
        Connect to IEEE 2030.5 server with database integration.
        
        Flow:
        1. Connect underlying client (TLS, get DeviceCapability)
        2. Save DeviceCapability to SQLite
        3. Check SQLite for existing EndDevice with matching sFDI
        4. If found, load cached paths
        5. If not found, will need to register
        
        Returns:
            True if connected successfully
        """
        # Connect underlying client
        if not await self.ieee_client.connect():
            return False
        
        # Save DeviceCapability to SQLite
        dcap = self.ieee_client._device_capability
        if dcap:
            self._save_device_capability(dcap)
        
        # Try to load cached EndDevice
        if self.sfdi:
            cached_edev = self.db.get_end_device_by_sfdi(self.sfdi)
            if cached_edev:
                logger.info(f"Found cached EndDevice: {cached_edev.href}")
                self._end_device = cached_edev
                
                # Load cached DER
                ders = self.db.get_ders_by_end_device(cached_edev.href)
                if ders:
                    self._der = ders[0]
                    logger.info(f"Found cached DER: {self._der.href}")
        
        return True
    
    async def get_or_register_end_device(self, pin: int = 0) -> Optional[EndDeviceRecord]:
        """
        Get existing or register new EndDevice.
        
        Flow:
        1. Check SQLite for cached EndDevice
        2. If cached, verify it exists on server
        3. If not cached or not on server, register new one
        4. Save to SQLite
        
        Args:
            pin: Device PIN for registration
            
        Returns:
            EndDeviceRecord or None if failed
        """
        # Check cache first
        if self._end_device:
            logger.info(f"Using cached EndDevice: {self._end_device.href}")
            return self._end_device
        
        # Try to find on server
        try:
            existing = await self.ieee_client.find_end_device_by_sfdi()
            if existing:
                record = self._save_end_device(existing)
                self._end_device = record
                
                # Also update ieee_client reference
                self.ieee_client._end_device = existing
                
                logger.info(f"Found existing EndDevice on server: {record.href}")
                return record
        except Exception as e:
            logger.debug(f"Could not find existing EndDevice: {e}")
        
        # Register new EndDevice
        try:
            new_edev = await self.ieee_client.register_end_device(pin=pin)
            record = self._save_end_device(new_edev)
            self._end_device = record
            logger.info(f"Registered new EndDevice: {record.href}")
            return record
        except Exception as e:
            logger.error(f"Failed to register EndDevice: {e}")
            return None
    
    async def get_or_create_der(
        self,
        description: str = "Battery Energy Storage System"
    ) -> Optional[DERRecord]:
        """
        Get existing or create new DER.
        
        Args:
            description: DER description
            
        Returns:
            DERRecord or None if failed
        """
        # Check cache first
        if self._der:
            logger.info(f"Using cached DER: {self._der.href}")
            return self._der
        
        # Need EndDevice first
        if not self._end_device:
            logger.error("EndDevice not available, cannot get/create DER")
            return None
        
        # Check SQLite for cached DER
        ders = self.db.get_ders_by_end_device(self._end_device.href)
        if ders:
            self._der = ders[0]
            logger.info(f"Found cached DER: {self._der.href}")
            return self._der
        
        # Try to get from server
        try:
            der = await self.ieee_client.get_or_create_der(description)
            if der:
                record = self._save_der(der, self._end_device.href)
                self._der = record
                logger.info(f"Got/created DER: {record.href}")
                return record
        except Exception as e:
            logger.error(f"Failed to get/create DER: {e}")
        
        return None
    
    async def get_or_create_mirror_usage_point(
        self,
        mup: "MirrorUsagePoint",
    ) -> Optional[MirrorUsagePointRecord]:
        """
        Get existing or create new MirrorUsagePoint.
        
        Args:
            mup: MirrorUsagePoint to create
            
        Returns:
            MirrorUsagePointRecord or None if failed
        """
        # Check SQLite for existing MUP with same mRID
        if mup.mRID:
            existing = self.db.get_all_mirror_usage_points()
            for record in existing:
                if record.mrid == mup.mRID:
                    logger.info(f"Found cached MirrorUsagePoint: {record.href}")
                    return record
        
        # Create on server
        try:
            created, location = await self.ieee_client.create_mirror_usage_point(mup)
            if location:
                record = MirrorUsagePointRecord(
                    href=location,
                    mrid=mup.mRID,
                    description=mup.description,
                    version=mup.version,
                    role_flags=mup.roleFlags,
                    service_category_kind=mup.serviceCategoryKind,
                    status=mup.status,
                    device_lfdi=mup.deviceLFDI,
                    post_rate=mup.postRate,
                )
                self.db.save_mirror_usage_point(record)
                logger.info(f"Created MirrorUsagePoint: {location}")
                return record
        except Exception as e:
            logger.error(f"Failed to create MirrorUsagePoint: {e}")
        
        return None
    
    def get_all_mirror_usage_points(self) -> List[MirrorUsagePointRecord]:
        """Get all cached MirrorUsagePoints."""
        return self.db.get_all_mirror_usage_points()
    
    def get_mirror_usage_point(self, href: str) -> Optional[MirrorUsagePointRecord]:
        """Get MirrorUsagePoint by href."""
        return self.db.get_mirror_usage_point_by_href(href)
    
    def delete_mirror_usage_point(self, href: str) -> bool:
        """Delete MirrorUsagePoint from database."""
        return self.db.delete_mirror_usage_point(href)
    
    def get_resource_by_path(self, path: str) -> Optional[dict]:
        """
        Quick path lookup from SQLite.
        
        Args:
            path: Resource path (e.g., /edev/1, /edev/1/der/1)
            
        Returns:
            Resource dict or None if not found
        """
        return self.db.get_resource_by_path(path)
    
    def get_database_summary(self) -> dict:
        """Get summary of stored resources."""
        return self.db.get_summary()
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    def _save_device_capability(self, dcap: "DeviceCapability") -> DeviceCapabilityRecord:
        """Save DeviceCapability to SQLite."""
        record = DeviceCapabilityRecord(
            server_url=self.ieee_client.server_url,
            href=dcap.href or "/dcap",
            poll_rate=dcap.pollRate,
            end_device_list_link=dcap.EndDeviceListLink.href if dcap.EndDeviceListLink else None,
            mirror_usage_point_list_link=dcap.MirrorUsagePointListLink.href if dcap.MirrorUsagePointListLink else None,
            self_device_link=dcap.SelfDeviceLink.href if dcap.SelfDeviceLink else None,
            time_link=dcap.TimeLink.href if dcap.TimeLink else None,
            der_program_list_link=dcap.DERProgramListLink.href if dcap.DERProgramListLink else None,
            response_set_list_link=dcap.ResponseSetListLink.href if dcap.ResponseSetListLink else None,
        )
        self.db.save_device_capability(record)
        self._device_capability = record
        logger.debug(f"Saved DeviceCapability for {self.ieee_client.server_url}")
        return record
    
    def _save_end_device(self, edev: "EndDevice") -> EndDeviceRecord:
        """Save EndDevice to SQLite."""
        record = EndDeviceRecord(
            href=edev.href or "",
            lfdi=edev.lFDI,
            sfdi=edev.sFDI,
            changed_time=edev.changedTime,
            enabled=edev.enabled,
            der_list_link=edev.DERListLink if isinstance(edev.DERListLink, str) else (edev.DERListLink.href if edev.DERListLink else None),
            device_information_link=edev.DeviceInformationLink if isinstance(edev.DeviceInformationLink, str) else (edev.DeviceInformationLink.href if edev.DeviceInformationLink else None),
            fsa_list_link=edev.FunctionSetAssignmentsListLink if isinstance(edev.FunctionSetAssignmentsListLink, str) else (edev.FunctionSetAssignmentsListLink.href if edev.FunctionSetAssignmentsListLink else None),
            registration_link=edev.RegistrationLink if isinstance(edev.RegistrationLink, str) else (edev.RegistrationLink.href if edev.RegistrationLink else None),
        )
        self.db.save_end_device(record)
        logger.debug(f"Saved EndDevice: {record.href}")
        return record
    
    def _save_der(self, der: "DER", end_device_href: str) -> DERRecord:
        """Save DER to SQLite."""
        record = DERRecord(
            href=der.href or "",
            mrid=der.mRID.hex() if der.mRID else None,
            description=der.description,
            version=der.version,
            end_device_href=end_device_href,
            der_capability_link=der.DERCapabilityLink if isinstance(der.DERCapabilityLink, str) else (der.DERCapabilityLink.href if der.DERCapabilityLink else None),
            der_settings_link=der.DERSettingsLink if isinstance(der.DERSettingsLink, str) else (der.DERSettingsLink.href if der.DERSettingsLink else None),
            der_status_link=der.DERStatusLink if isinstance(der.DERStatusLink, str) else (der.DERStatusLink.href if der.DERStatusLink else None),
            der_availability_link=der.DERAvailabilityLink if isinstance(der.DERAvailabilityLink, str) else (der.DERAvailabilityLink.href if der.DERAvailabilityLink else None),
        )
        self.db.save_der(record)
        logger.debug(f"Saved DER: {record.href}")
        return record
    
    def save_mirror_usage_point(
        self,
        href: str,
        mup: "MirrorUsagePoint",
        meter_name: Optional[str] = None,
        meter_type: Optional[str] = None,
    ) -> MirrorUsagePointRecord:
        """
        Save MirrorUsagePoint to SQLite.
        
        Args:
            href: MUP href path
            mup: MirrorUsagePoint object
            meter_name: Optional meter name
            meter_type: Optional meter type
            
        Returns:
            Saved record
        """
        record = MirrorUsagePointRecord(
            href=href,
            mrid=mup.mRID,
            description=mup.description,
            version=mup.version,
            role_flags=mup.roleFlags,
            service_category_kind=mup.serviceCategoryKind,
            status=mup.status,
            device_lfdi=mup.deviceLFDI,
            post_rate=mup.postRate,
            meter_name=meter_name,
            meter_type=meter_type,
        )
        self.db.save_mirror_usage_point(record)
        logger.debug(f"Saved MirrorUsagePoint: {record.href}")
        return record
