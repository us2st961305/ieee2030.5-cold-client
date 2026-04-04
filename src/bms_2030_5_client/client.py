"""
Main BMS IEEE 2030.5 Client.

Integrates Modbus BMS communication with IEEE 2030.5 server reporting.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Callable, List, Union, Dict
from pathlib import Path

import httpx

from bms_2030_5_client.config import Config
from bms_2030_5_client.modbus import ModbusBMSClient, BMSDataCollector
from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client
from bms_2030_5_client.adapters import BMSAdapter
from bms_2030_5_client.models import (
    BMSSnapshot,
    DERStatus,
    DERAvailability,
    MirrorUsagePoint,
    MirrorMeterReading,
    DeviceInformation,
    PowerSourceType,
    LogEvent,
)
from bms_2030_5_client.protocols import (
    FunctionSetIdentifier,
    LogEventCode,
    LOG_EVENT_CODE_DESCRIPTIONS,
    AlarmStatusType,
)
from bms_2030_5_client.dera import DERClient, DERClientConfig
from bms_2030_5_client.power_control import (
    SafePowerController,
    PowerControlConfig,
    PowerLimits,
    create_power_controller_from_runtime,
)
from bms_2030_5_client.modbus.power_writer import (
    ModbusPowerWriter,
    ModbusPowerWriterConfig,
    PCSRegisterAddress,
)
from bms_2030_5_client.subscription import (
    NotificationServer,
    NotificationServerConfig,
    SubscriptionManager,
    SubscriptionManagerConfig,
    NotificationHandler,
    NotificationHandlerConfig,
)
from bms_2030_5_client.db import (
    IEEE2030_5Database,
    init_database,
    get_database,
    EndDeviceRecord,
    DERRecord,
    MirrorUsagePointRecord,
    MirrorMeterReadingRecord,
    MeterTypeRecord,
)
from bms_2030_5_client.cycle_storage import (
    CycleStorage,
    CycleTrackingData,
)
from bms_2030_5_client.task_supervisor import TaskSupervisor

logger = logging.getLogger(__name__)


class BMSClient:
    """
    Main BMS IEEE 2030.5 Client.
    
    Orchestrates:
    - Modbus TCP communication with CUBE BMS
    - IEEE 2030.5 communication with utility server
    - Data transformation between BMS and DER models
    - Periodic status reporting
    - Push-based DER control via subscription/notification (optional)
    """

    def __init__(
        self,
        config: Config,
        auto_register: bool = True,
        enable_metering: bool = True,
        enable_der_control: bool = True,
        enable_subscription: Optional[bool] = None,
        notification_host: Optional[str] = None,
        notification_port: Optional[int] = None,
    ):
        """
        Initialize BMS Client.
        
        Args:
            config: Configuration object
            auto_register: Automatically register with 2030.5 server
            enable_metering: Enable meter data upload (MirrorUsagePoint)
            enable_der_control: Enable DER control polling (FSA/DERProgram/DERControl)
            enable_subscription: Enable push-based subscription/notification for DER control.
                                 If None, uses config.subscription.enabled
            notification_host: Host for notification server (when subscription enabled).
                               If None, uses config.subscription.notification_host
            notification_port: Port for notification server (when subscription enabled).
                               If None, uses config.subscription.notification_port
        """
        self.config = config
        self.auto_register = auto_register
        self.enable_metering = enable_metering
        self.enable_der_control = enable_der_control
        
        # Use config values as defaults for subscription settings
        self._enable_subscription = (
            enable_subscription if enable_subscription is not None 
            else config.subscription.enabled
        )
        self._notification_host = (
            notification_host if notification_host is not None 
            else config.subscription.notification_host
        )
        self._notification_port = (
            notification_port if notification_port is not None 
            else config.subscription.notification_port
        )
        
        # Initialize components
        self.modbus_client = ModbusBMSClient.from_config(config)
        self.data_collector = BMSDataCollector(
            client=self.modbus_client,
            refresh_interval=config.modbus.refresh_interval,
        )
        self.ieee2030_5_client = IEEE2030_5Client.from_config(config)
        self.adapter = BMSAdapter()
        
        # State
        self._running = False
        self._edev_href: Optional[str] = None  # EndDevice href (e.g., /edev/97)
        self._der_path: Optional[str] = None
        self._mup_href: Optional[str] = None  # MirrorUsagePoint href
        self._mup_mrid: Optional[str] = None  # MirrorUsagePoint mRID (persisted)
        self._reading_mrids: Dict[str, str] = {}  # Cached reading mRIDs
        self._callbacks: List[Callable] = []
        
        # Alarm tracking for LogEvent
        self._previous_alarm_status: int = 0  # Previous alarm status (bitfield)
        self._log_event_id_counter: int = 0  # Unique LogEvent ID counter
        
        # Cycle tracking (charge >10% + discharge >10% = 1 cycle)
        # Uses persistent binary storage to survive restarts
        self._cycle_storage = CycleStorage("data/cycle_tracking.bin")
        self._init_cycle_tracking()
        
        # DER Control components (initialized after connection)
        self._der_client: Optional[DERClient] = None
        self._power_controller: Optional[SafePowerController] = None
        
        # Subscription/Notification components (initialized when enabled)
        self._notification_server: Optional[NotificationServer] = None
        self._subscription_manager: Optional[SubscriptionManager] = None
        self._notification_handler: Optional[NotificationHandler] = None
        self._time_sync_client: Optional[TimeSyncClient] = None
        
        # SQLite Database for IEEE 2030.5 resource persistence
        self._db: Optional[IEEE2030_5Database] = None
        self._db_path = getattr(config, 'database_path', 'data/ieee2030_5.db')
        self._init_database()

        # Persistent HTTP client for Supabase reporting (created on start, closed on stop)
        self._supabase_client: Optional[httpx.AsyncClient] = None

        # IEEE 2030.5 reconnection tracking (independent per-loop counters)
        self._reporting_consecutive_failures: int = 0
        self._metering_consecutive_failures: int = 0
        self._ieee2030_5_failure_threshold: int = 3  # trigger reconnect after N failures

        # mRID recovery tracking (Layer 2 cooldown + Layer 4 partial upload counter)
        self._last_mrid_recovery_attempt: float = 0.0  # monotonic timestamp
        self._mrid_recovery_cooldown: float = 1800.0  # 30 minutes
        self._partial_upload_count: int = 0  # consecutive partial uploads
        self._partial_upload_threshold: int = 10  # trigger full re-registration

        # Task supervisor for background task resilience
        self._supervisor = TaskSupervisor()
    
    def _init_cycle_tracking(self) -> None:
        """
        Initialize cycle tracking from persistent storage.
        
        Loads previously saved cycle count and SOC tracking data
        to continue from where we left off after restart.
        """
        saved_data = self._cycle_storage.load()
        if saved_data:
            self._cycle_count = saved_data.cycle_count
            self._last_soc = saved_data.last_soc
            self._charge_accumulated = saved_data.charge_accumulated
            self._discharge_accumulated = saved_data.discharge_accumulated
            logger.info(
                f"Restored cycle tracking: cycles={self._cycle_count}, "
                f"charge_acc={self._charge_accumulated:.2f}%, "
                f"discharge_acc={self._discharge_accumulated:.2f}%, "
                f"last_soc={self._last_soc}"
            )
        else:
            # Initialize with defaults
            self._cycle_count = 0
            self._last_soc = None
            self._charge_accumulated = 0.0
            self._discharge_accumulated = 0.0
            logger.info("Initialized new cycle tracking")
            # Save initial state to create the file
            self._save_cycle_tracking()
    
    def _save_cycle_tracking(self) -> None:
        """Save current cycle tracking state to persistent storage."""
        data = CycleTrackingData(
            cycle_count=self._cycle_count,
            charge_accumulated=self._charge_accumulated,
            discharge_accumulated=self._discharge_accumulated,
            last_soc=self._last_soc,
        )
        self._cycle_storage.save(data)

    @classmethod
    def from_config(cls, config_path: Union[str, Path]) -> "BMSClient":
        """
        Create BMSClient from configuration file.
        
        Args:
            config_path: Path to YAML configuration file
            
        Returns:
            BMSClient instance
        """
        config = Config.from_yaml(config_path)
        return cls(config)

    @property
    def is_running(self) -> bool:
        """Check if client is running."""
        return self._running

    @property
    def latest_snapshot(self) -> Optional[BMSSnapshot]:
        """Get latest BMS snapshot."""
        return self.data_collector.latest_snapshot
    
    @property
    def database(self) -> Optional[IEEE2030_5Database]:
        """Get the SQLite database instance."""
        return self._db
    
    @staticmethod
    def _description_to_reading_key(description: str) -> Optional[str]:
        """
        Map MirrorMeterReading description to reading key.
        
        Args:
            description: Reading description (e.g., "Battery Total Current")
            
        Returns:
            Key for _reading_mrids dict, or None if not recognized
        """
        name = description.lower().replace(" ", "_")
        if "soc" in name and "state" not in name:
            return "soc"
        elif "current" in name:
            return "current"
        elif "power" in name:
            return "power"
        elif "charge" in name and "discharge" not in name:
            return "charge_energy"
        elif "discharge" in name:
            return "discharge_energy"
        elif "max" in name and "temp" in name:
            return "max_temperature"
        elif "min" in name and "temp" in name:
            return "min_temperature"
        elif "avg" in name and "temp" in name:
            return "avg_temperature"
        elif "soh" in name:
            return "soh"
        elif "cycle" in name:
            return "cycle_count"
        elif "timestamp" in name:
            return "timestamp"
        return None
    
    def _cache_reading_mrids_from_server(self, readings: list) -> int:
        """
        Cache reading mRIDs from server response.
        
        Args:
            readings: List of MirrorMeterReading objects from server
            
        Returns:
            Number of mRIDs cached
        """
        cached_count = 0
        for reading in readings:
            logger.debug(f"Server reading: description={reading.description}, mRID={reading.mRID}, href={getattr(reading, 'href', None)}")
            if reading.description and reading.mRID:
                key = self._description_to_reading_key(reading.description)
                if key:
                    self._reading_mrids[key] = reading.mRID
                    cached_count += 1
                    logger.debug(f"Cached mRID: {key} -> {reading.mRID}")
                else:
                    logger.warning(f"Unknown reading description: {reading.description}")
            else:
                logger.warning(f"Reading missing mRID or description: desc={reading.description}, mRID={reading.mRID}")
        return cached_count
    
    def _init_database(self) -> None:
        """Initialize SQLite database for IEEE 2030.5 resource persistence."""
        try:
            self._db = init_database(self._db_path)
            logger.info(f"Initialized IEEE 2030.5 database: {self._db_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize database: {e}")
            self._db = None

    async def _reconnect_ieee2030_5(self) -> bool:
        """
        Reconnect to IEEE 2030.5 server with exponential backoff.

        Attempts up to 10 reconnections with delays: 2s, 4s, 8s, ... 120s max.

        Returns:
            True if reconnection successful
        """
        max_attempts = 10
        base_delay = 2.0
        max_delay = 120.0

        for attempt in range(1, max_attempts + 1):
            if not self._running:
                return False

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                f"IEEE 2030.5 reconnect attempt {attempt}/{max_attempts} "
                f"(next retry in {delay:.0f}s)"
            )
            try:
                await self.ieee2030_5_client.disconnect()
                success = await self.ieee2030_5_client.connect()
                if success:
                    logger.info(
                        f"IEEE 2030.5 reconnection successful after {attempt} attempt(s)"
                    )
                    self._ieee2030_5_consecutive_failures = 0
                    return True
            except Exception as e:
                logger.error(f"Reconnect attempt {attempt} failed: {e}")

            await asyncio.sleep(delay)

        logger.critical(
            "IEEE 2030.5 reconnection failed after max attempts — "
            "entering degraded state, will retry periodically"
        )
        return False
    
    def _load_cached_resources(self) -> bool:
        """
        Load cached resources from SQLite database.
        
        Implements IEEE 2030.5 快速恢復模式 (Fast Recovery):
        - 從資料庫載入已緩存的 EndDevice href
        - 從資料庫載入已緩存的 DER href
        - 從資料庫載入已緩存的 MirrorUsagePoint href
        - 從資料庫載入已緩存的 MirrorMeterReading mRIDs
        
        Returns:
            True if cached resources were found and loaded
        """
        if not self._db:
            return False
        
        # Try to load EndDevice by sFDI
        sfdi = self.ieee2030_5_client.sfdi
        if sfdi:
            cached_edev = self._db.get_end_device_by_sfdi(sfdi)
            if cached_edev:
                self._edev_href = cached_edev.href
                logger.info(f"[Fast Recovery] Loaded cached EndDevice: {self._edev_href}")
                
                # Load cached DER
                ders = self._db.get_ders_by_end_device(cached_edev.href)
                if ders:
                    self._der_path = ders[0].href
                    logger.info(f"[Fast Recovery] Loaded cached DER: {self._der_path}")
                
                # Load cached MirrorUsagePoint
                mups = self._db.get_mirror_usage_points_by_lfdi(self.ieee2030_5_client.lfdi or "")
                if mups:
                    self._mup_href = mups[0].href
                    self._mup_mrid = mups[0].mrid
                    logger.info(f"[Fast Recovery] Loaded cached MirrorUsagePoint: {self._mup_href} (mRID={self._mup_mrid})")
                    
                    # Load cached MirrorMeterReading mRIDs
                    readings = self._db.get_readings_by_mup(self._mup_href)
                    if readings:
                        for r in readings:
                            if r.description and r.mrid:
                                key = self._description_to_reading_key(r.description)
                                if key:
                                    self._reading_mrids[key] = r.mrid
                        logger.info(f"[Fast Recovery] Loaded {len(self._reading_mrids)} cached reading mRIDs: {list(self._reading_mrids.keys())}")
                    
                    # Layer 1: Fallback to meter_types table if mirror_meter_reading incomplete
                    expected_keys = {
                        "current", "power", "charge_energy", "discharge_energy",
                        "max_temperature", "min_temperature", "avg_temperature",
                        "soh", "cycle_count", "timestamp",
                    }
                    missing = expected_keys - set(self._reading_mrids.keys())
                    if missing and self._mup_href:
                        meter_types = self._db.get_meter_types(self._mup_href)
                        fallback_count = 0
                        for mt in meter_types:
                            if mt.mrid and mt.description:
                                key = self._description_to_reading_key(mt.description)
                                if key and key in missing:
                                    self._reading_mrids[key] = mt.mrid
                                    fallback_count += 1
                        if fallback_count:
                            logger.info(
                                f"[Fast Recovery] Filled {fallback_count} mRIDs from meter_types fallback: "
                                f"{list(self._reading_mrids.keys())}"
                            )
                
                return True
        
        return False
    
    def _save_end_device_to_db(self, edev) -> None:
        """Save EndDevice to SQLite database."""
        if not self._db:
            return
        
        try:
            record = EndDeviceRecord(
                href=edev.href or "",
                lfdi=edev.lFDI,
                sfdi=edev.sFDI,
                changed_time=edev.changedTime,
                enabled=edev.enabled,
                der_list_link=edev.DERListLink if isinstance(edev.DERListLink, str) else (edev.DERListLink.href if edev.DERListLink else None),
                device_information_link=edev.DeviceInformationLink if isinstance(edev.DeviceInformationLink, str) else (edev.DeviceInformationLink.href if edev.DeviceInformationLink else None),
                fsa_list_link=edev.FunctionSetAssignmentsListLink if isinstance(edev.FunctionSetAssignmentsListLink, str) else (edev.FunctionSetAssignmentsListLink.href if edev.FunctionSetAssignmentsListLink else None),
            )
            self._db.save_end_device(record)
            logger.debug(f"Saved EndDevice to database: {record.href}")
        except Exception as e:
            logger.warning(f"Failed to save EndDevice to database: {e}")
    
    def _save_der_to_db(self, der, end_device_href: str) -> None:
        """Save DER to SQLite database."""
        if not self._db:
            return
        
        try:
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
            self._db.save_der(record)
            logger.debug(f"Saved DER to database: {record.href}")
        except Exception as e:
            logger.warning(f"Failed to save DER to database: {e}")
    
    def _save_mup_to_db(self, mup) -> None:
        """Save MirrorUsagePoint to SQLite database."""
        if not self._db:
            return
        
        try:
            # Extract href from the MirrorUsagePoint object
            href = getattr(mup, 'href', None) or self._mup_href or ""
            
            record = MirrorUsagePointRecord(
                href=href,
                mrid=getattr(mup, 'mRID', None) or "",
                description=getattr(mup, 'description', None),
                version=getattr(mup, 'version', None),
                role_flags=getattr(mup, 'roleFlags', None),
                service_category_kind=getattr(mup, 'serviceCategoryKind', None),
                status=getattr(mup, 'status', None),
                device_lfdi=getattr(mup, 'deviceLFDI', None) or self.ieee2030_5_client.lfdi or "",
                post_rate=getattr(mup, 'postRate', None),
            )
            self._db.save_mirror_usage_point(record)
            logger.debug(f"Saved MirrorUsagePoint to database: {record.href}")
        except Exception as e:
            logger.warning(f"Failed to save MirrorUsagePoint to database: {e}")

    def _save_meter_readings_to_db(self, mup_href: str, readings: list) -> None:
        """
        Save MirrorMeterReadings to SQLite database.
        
        Args:
            mup_href: The href of the parent MirrorUsagePoint
            readings: List of MirrorMeterReading objects from server
        """
        if not self._db:
            return
        
        saved_count = 0
        for reading in readings:
            try:
                # Extract reading type info
                reading_type = getattr(reading, 'ReadingType', None)
                
                record = MirrorMeterReadingRecord(
                    mup_href=mup_href,
                    href=getattr(reading, 'href', None),
                    mrid=getattr(reading, 'mRID', None),
                    description=getattr(reading, 'description', None),
                    reading_type_href=getattr(reading_type, 'href', None) if reading_type else None,
                    accumulation_behaviour=getattr(reading_type, 'accumulationBehaviour', 0) if reading_type else 0,
                    commodity=getattr(reading_type, 'commodity', 1) if reading_type else 1,
                    data_qualifier=getattr(reading_type, 'dataQualifier', 0) if reading_type else 0,
                    flow_direction=getattr(reading_type, 'flowDirection', 0) if reading_type else 0,
                    kind=getattr(reading_type, 'kind', 0) if reading_type else 0,
                    phase=getattr(reading_type, 'phase', None) if reading_type else None,
                    power_of_ten_multiplier=getattr(reading_type, 'powerOfTenMultiplier', 0) if reading_type else 0,
                    uom=getattr(reading_type, 'uom', 0) if reading_type else 0,
                )
                self._db.save_mirror_meter_reading(record)
                saved_count += 1
            except Exception as e:
                logger.warning(f"Failed to save MirrorMeterReading to database: {e}")
        
        logger.info(f"Saved {saved_count} MirrorMeterReadings to database for MUP: {mup_href}")

    async def _recover_reading_mrids_from_server(self) -> bool:
        """
        Layer 2: Lightweight mRID recovery from server during upload.

        Unlike _recover_from_server() (used at startup), this only does:
        GET /upt → find matching UsagePoint → GET /upt/{id}/mr → sync mRIDs.
        Respects cooldown (_mrid_recovery_cooldown) to avoid hammering server.

        Returns:
            True if any mRIDs were recovered
        """
        now = time.monotonic()
        if now - self._last_mrid_recovery_attempt < self._mrid_recovery_cooldown:
            return False
        self._last_mrid_recovery_attempt = now

        if not self._mup_mrid:
            logger.warning("[mRID Recovery] No MUP mRID available, cannot recover")
            return False

        logger.info("[mRID Recovery] Attempting lightweight mRID sync from server...")

        # Step 1: GET /upt → find UsagePoint matching our MUP mRID
        upt_href = None
        try:
            upt_list = await self.ieee2030_5_client.get_usage_point_list()
            for upt in (upt_list.UsagePoint or []):
                if upt.mRID and upt.mRID.upper() == self._mup_mrid.upper():
                    upt_href = upt.href
                    break
            if not upt_href:
                logger.warning("[mRID Recovery] No matching UsagePoint found on server")
                return False
        except Exception as e:
            logger.warning(f"[mRID Recovery] Failed to GET /upt: {e}")
            return False

        # Step 2: GET /upt/{id}/mr → get MeterReadingList
        try:
            mr_list = await self.ieee2030_5_client.get_meter_reading_list(upt_href)
            mr_entries = mr_list.MeterReading or []
        except Exception as e:
            logger.warning(f"[mRID Recovery] Failed to GET {upt_href}/mr: {e}")
            return False

        # Step 3: Cache recovered mRIDs + write to DB
        recovered = 0
        for mr_entry in mr_entries:
            if not mr_entry.description or not mr_entry.mRID:
                continue
            key = self._description_to_reading_key(mr_entry.description)
            if key and key not in self._reading_mrids:
                self._reading_mrids[key] = mr_entry.mRID
                recovered += 1

        if recovered:
            logger.info(
                f"[mRID Recovery] Recovered {recovered} mRIDs from server: "
                f"{list(self._reading_mrids.keys())}"
            )
            self._sync_reading_mrids_to_db()
        else:
            logger.info("[mRID Recovery] No new mRIDs recovered from server")

        return recovered > 0

    def _sync_reading_mrids_to_db(self) -> None:
        """
        Defense C: Persist current _reading_mrids to mirror_meter_reading table.

        Called after successful upload or mRID recovery to ensure DB stays fresh.
        Uses (mup_href, description) as upsert key — same as save_mirror_meter_reading().
        """
        if not self._db or not self._mup_href:
            return

        # Reverse map: reading key → description (for DB storage)
        key_to_description = {
            "current": "Battery Total Current",
            "power": "Battery Total Power",
            "charge_energy": "Battery Charge Energy",
            "discharge_energy": "Battery Discharge Energy",
            "max_temperature": "Battery Max Temperature",
            "min_temperature": "Battery Min Temperature",
            "avg_temperature": "Battery Avg Temperature",
            "soh": "Battery SOH",
            "cycle_count": "Battery Cycle Count",
            "timestamp": "BMS Timestamp",
        }

        synced = 0
        for key, mrid in self._reading_mrids.items():
            desc = key_to_description.get(key)
            if not desc:
                continue
            try:
                record = MirrorMeterReadingRecord(
                    mup_href=self._mup_href,
                    mrid=mrid,
                    description=desc,
                )
                self._db.save_mirror_meter_reading(record)
                synced += 1
            except Exception as e:
                logger.warning(f"[DB Sync] Failed to sync mRID for {key}: {e}")

        if synced:
            logger.debug(f"[DB Sync] Synced {synced} reading mRIDs to database")

    def add_callback(self, callback: Callable[[BMSSnapshot], None]) -> None:
        """Add callback for new BMS data."""
        self._callbacks.append(callback)
        self.data_collector.add_callback(callback)

    async def start(self) -> None:
        """
        Start the BMS client.
        
        1. Connect to BMS via Modbus
        2. Connect to IEEE 2030.5 server
        3. Register end device (if auto_register)
        4. Start data collection
        5. Start periodic reporting
        """
        if self._running:
            logger.warning("Client already running")
            return

        logger.info("Starting BMS IEEE 2030.5 Client...")

        # Connect to BMS
        logger.info("Connecting to BMS...")
        if not await self.modbus_client.connect():
            raise RuntimeError("Failed to connect to BMS")

        # Connect to IEEE 2030.5 server
        logger.info("Connecting to IEEE 2030.5 server...")
        if not await self.ieee2030_5_client.connect():
            await self.modbus_client.disconnect()
            raise RuntimeError("Failed to connect to IEEE 2030.5 server")

        # Register with server (or find existing device)
        if self.auto_register:
            # =========================================================================
            # IEEE 2030.5 Device Registration Flow
            # =========================================================================
            # 1. Fast Recovery: Try to use cached resources from database
            # 2. Resource Validation: Verify cached resources exist on server
            # 3. Full Registration: If validation fails, perform full registration
            # =========================================================================
            
            # Step 1: Try Fast Recovery from SQLite cache
            if self._load_cached_resources():
                logger.info("=" * 60)
                logger.info("[IEEE 2030.5 Fast Recovery] Using cached resources from database")
                logger.info("=" * 60)
                
                # Step 2: Resource Validation - verify cached EndDevice exists on server
                try:
                    existing_edev = await self.ieee2030_5_client.find_end_device_by_sfdi()
                    if existing_edev and existing_edev.href == self._edev_href:
                        logger.info(f"[Fast Recovery] EndDevice verified on server - 200 OK: {self._edev_href}")
                        self.ieee2030_5_client._end_device = existing_edev
                    else:
                        logger.info("[Fast Recovery] EndDevice not found on server (404), switching to Full Registration...")
                        self._edev_href = None
                        self._der_path = None
                        self._mup_href = None
                        self._reading_mrids.clear()
                except Exception as e:
                    logger.warning(f"[Fast Recovery] Resource validation failed: {e}, switching to Full Registration...")
                    self._edev_href = None
                    self._der_path = None
                    self._mup_href = None
                    self._reading_mrids.clear()
            
            # Step 3: Full Registration if Fast Recovery failed or no cache
            if not self._edev_href:
                logger.info("=" * 60)
                logger.info("[IEEE 2030.5 Full Registration] Starting device registration...")
                logger.info("=" * 60)
                logger.info("[Full Registration] Checking for existing EndDevice by sFDI...")
                try:
                    # First check if device already exists
                    existing_edev = await self.ieee2030_5_client.find_end_device_by_sfdi()
                    
                    if existing_edev:
                        logger.info(f"Found existing EndDevice: {existing_edev.href}")
                        self._edev_href = existing_edev.href
                        self._save_end_device_to_db(existing_edev)
                    else:
                        # Register new device
                        logger.info("No existing device found, registering new EndDevice...")
                        end_device = await self.ieee2030_5_client.register_end_device(
                            pin=self.config.ieee2030_5.pin
                        )
                        logger.info(f"Registered end device: {end_device.href}")
                        self._edev_href = end_device.href
                        self._save_end_device_to_db(end_device)
                    
                    # Get or create DER resource and build complete path
                    if self._edev_href and not self._der_path:
                        logger.info("Getting or creating DER resource...")
                        der = await self.ieee2030_5_client.get_or_create_der(
                            description="CUBE Battery Management System"
                        )
                        if der and der.href:
                            self._der_path = der.href
                            logger.info(f"Using DER path: {self._der_path}")
                            self._save_der_to_db(der, self._edev_href)
                        else:
                            logger.warning("Could not get or create DER resource")
                        
                except Exception as e:
                    logger.warning(f"Registration/lookup failed: {e}", exc_info=True)

        # Register MirrorUsagePoint (meter) for metering data
        if self.enable_metering:
            await self._register_meter()

        # Update device information
        if self._edev_href:
            logger.info("Updating device information...")
            try:
                import time
                current_time = int(time.time())
                mfg_date = current_time - (365 * 24 * 60 * 60)  # 1 year ago
                
                await self.update_device_information(
                    mf_id=99400,  # Example manufacturer ID
                    mf_model="CUBE",
                    mf_serial_number="CUBE-001",
                    mf_ser_num="CUBE-001",  # Required: short form serial number
                    mf_date=mfg_date,  # Required: manufacture date
                    mf_hw_ver="1.0",  # Required: hardware version
                    secondary_power=2,  # Required: Battery backup
                    sw_act_time=current_time,  # Required: software activation time
                    gps_lat="25.0330",  # Required: Taipei latitude
                    gps_lon="121.5654",  # Required: Taipei longitude
                    mf_info="CUBE Battery Management System",
                    sw_ver="1.0.0",
                    primary_power=1,  # Mains power
                )
                logger.info("Device information updated successfully")
            except Exception as e:
                logger.warning(f"Failed to update device information: {e}", exc_info=True)

        # Start data collection
        await self.data_collector.start()

        # Start background tasks via supervisor
        self._running = True
        self._supervisor.register(
            "reporting", lambda: self._reporting_loop(),
            max_restarts=10, backoff_base=2.0, backoff_max=300.0,
        )

        if self.enable_metering:
            if self._mup_href:
                logger.info(f"Starting metering task with MUP: {self._mup_href}")
                self._supervisor.register(
                    "metering", lambda: self._metering_loop(),
                    max_restarts=10, backoff_base=2.0, backoff_max=300.0,
                )
            else:
                logger.warning("Metering enabled but no MirrorUsagePoint href available - metering task NOT started")

        await self._supervisor.start_all()

        # Start DER Control - either subscription-based or polling-based
        if self._enable_subscription:
            # Push-based: Use subscription/notification for near real-time control
            await self._start_subscription_control()
        elif self.enable_der_control:
            # Pull-based: Use polling for DER control
            await self._start_der_control()

        logger.info("BMS Client started successfully")

    async def stop(self) -> None:
        """Stop the BMS client."""
        logger.info("Stopping BMS Client...")
        
        self._running = False
        
        # Stop all supervised background tasks
        await self._supervisor.stop_all()

        # Stop DER Control
        if self._der_client:
            await self._der_client.stop()
            self._der_client = None
            logger.info("DER Control stopped")

        # Disconnect PCS Modbus client if separate from BMS
        pcs_client = getattr(self, '_pcs_modbus_client', None)
        if pcs_client:
            try:
                await pcs_client.disconnect()
                logger.info("PCS Modbus client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting PCS Modbus: {e}")
            self._pcs_modbus_client = None

        # Stop subscription components
        await self._stop_subscription_control()

        # Stop data collection
        await self.data_collector.stop()

        # Disconnect from servers
        await self.modbus_client.disconnect()
        await self.ieee2030_5_client.disconnect()

        logger.info("BMS Client stopped")

    async def _init_power_controller(self) -> SafePowerController:
        """
        Initialize SafePowerController from runtime config or env.
        
        If runtime config has power_control section, uses that.
        Otherwise falls back to environment variable based config.
        Also creates and wires ModbusPowerWriter for non-simulation modes.
        
        Returns:
            SafePowerController instance
        """
        # Try runtime config first
        runtime_config = getattr(self, '_runtime_config', None)
        if runtime_config and hasattr(runtime_config, 'power_control'):
            rt_pc = runtime_config.power_control
            controller = create_power_controller_from_runtime(rt_pc)
            
            # For non-dry_run modes, create and wire PCS Modbus writer
            if not rt_pc.is_dry_run:
                try:
                    from pymodbus.client import AsyncModbusTcpClient
                    
                    pcs_modbus = rt_pc.pcs_modbus
                    
                    # Create dedicated PCS Modbus client (separate from BMS)
                    pcs_client_wrapper = ModbusBMSClient(
                        host=pcs_modbus.host,
                        port=pcs_modbus.port,
                        unit_id=pcs_modbus.unit_id,
                        timeout=pcs_modbus.timeout,
                        rack_count=0,
                    )
                    
                    # Connect to PCS
                    connected = await pcs_client_wrapper.connect()
                    if not connected:
                        logger.error(
                            f"Failed to connect to PCS at "
                            f"{pcs_modbus.host}:{pcs_modbus.port}"
                        )
                    else:
                        logger.info(
                            f"Connected to PCS Modbus at "
                            f"{pcs_modbus.host}:{pcs_modbus.port}"
                        )
                    
                    # Configure PCS register addresses from runtime config
                    PCSRegisterAddress.POWER_SETPOINT = rt_pc.registers.power_setpoint
                    PCSRegisterAddress.POWER_SETPOINT_HIGH = rt_pc.registers.power_setpoint_high
                    PCSRegisterAddress.OPERATION_MODE = rt_pc.registers.operation_mode
                    PCSRegisterAddress.ENABLE_CONTROL = rt_pc.registers.enable_control
                    PCSRegisterAddress.ACTUAL_POWER = rt_pc.registers.actual_power
                    PCSRegisterAddress.OPERATION_STATUS = rt_pc.registers.operation_status
                    PCSRegisterAddress.ERROR_CODE = rt_pc.registers.error_code
                    
                    # Create ModbusPowerWriter config
                    writer_config = ModbusPowerWriterConfig(
                        power_setpoint_address=rt_pc.registers.power_setpoint,
                        use_32bit_power=rt_pc.use_32bit,
                        power_scale_factor=rt_pc.power_scale_factor,
                        verify_after_write=rt_pc.verify_after_write,
                    )
                    
                    # Create power writer (pure I/O layer, safety checks
                    # are handled by SafePowerController)
                    power_writer = ModbusPowerWriter(
                        modbus_client=pcs_client_wrapper,
                        config=writer_config,
                    )
                    
                    # Inject writer into controller
                    controller.set_pcs_writer(power_writer)
                    
                    # Store reference for cleanup
                    self._pcs_modbus_client = pcs_client_wrapper
                    
                    logger.info(
                        f"PCS ModbusPowerWriter configured: "
                        f"setpoint_reg={rt_pc.registers.power_setpoint}, "
                        f"scale={rt_pc.power_scale_factor}, "
                        f"32bit={rt_pc.use_32bit}"
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to initialize PCS writer: {e}", exc_info=True)
            
            return controller
        
        # Fallback: env-based config
        power_config = PowerControlConfig.from_env()
        return SafePowerController(power_config)

    async def _start_der_control(self) -> None:
        """
        Initialize and start DER Control polling.
        
        This enables:
        - FSA (FunctionSetAssignments) discovery and monitoring
        - DERProgram management with primacy handling
        - DERControl event execution
        - Response reporting
        
        ⚠️ Safety: Power control mode determined by runtime config
        """
        try:
            # Initialize power controller (runtime config aware)
            self._power_controller = await self._init_power_controller()
            
            logger.info(
                f"SafePowerController initialized "
                f"(mode={self._power_controller.control_mode.value})"
            )
            
            # Initialize DERClient config
            der_config = DERClientConfig(
                fsa_poll_interval_s=300.0,      # 5 minutes
                program_poll_interval_s=60.0,   # 1 minute
                control_poll_interval_s=30.0,   # 30 seconds
                max_programs=6,
                enable_randomization=True,
            )
            
            # Initialize DERClient
            self._der_client = DERClient(
                http_client=self.ieee2030_5_client,
                power_controller=self._power_controller,
                config=der_config,
            )
            
            # Start DERClient
            await self._der_client.start()
            logger.info(
                f"DER Control started - "
                f"FSA polling every {der_config.fsa_poll_interval_s}s, "
                f"Control polling every {der_config.control_poll_interval_s}s"
            )
            
        except Exception as e:
            logger.error(f"Failed to start DER Control: {e}", exc_info=True)
            # Don't fail the entire client if DER control fails
            self._der_client = None
            self._power_controller = None

    async def _start_subscription_control(self) -> None:
        """
        Initialize and start IEEE 2030.5 subscription-based control.
        
        This enables:
        - Push-based DERControl notifications via HTTPS server
        - Subscription chain: FSA → DERProgram → DERControl
        - Time synchronization (mandatory polling for /tm)
        - Automatic subscription renewal
        
        ⚠️ Safety: Power control mode determined by runtime config
        """
        try:
            # Initialize power controller (runtime config aware)
            self._power_controller = await self._init_power_controller()
            
            logger.info(
                f"SafePowerController initialized "
                f"(mode={self._power_controller.control_mode.value})"
            )
            
            # Get TLS certificate paths from config
            cert_file = self.config.ieee2030_5.cert_file
            key_file = self.config.ieee2030_5.key_file
            ca_file = self.config.ieee2030_5.ca_file
            
            # Check if using public_uri (e.g., Tailscale Funnel)
            # If so, disable TLS as the reverse proxy handles TLS termination
            use_tls = self.config.subscription.public_uri is None
            
            # Build notification server config
            notification_config = NotificationServerConfig(
                host=self._notification_host,
                port=self._notification_port,
                cert_file=cert_file,
                key_file=key_file,
                ca_file=ca_file,
                use_tls=use_tls,
            )
            
            # Initialize NotificationServer
            self._notification_server = NotificationServer(notification_config)
            
            # Start notification server
            await self._notification_server.start()
            
            # Build notification URI for server to send notifications to us
            # Use public_uri (e.g., Tailscale Funnel) if configured, otherwise fallback to local
            public_uri = self.config.subscription.public_uri
            if public_uri:
                # Use public URI (e.g., https://shulin1f25r.tailbd4dcc.ts.net)
                # Ensure it ends with the notification endpoint
                notification_uri = public_uri.rstrip('/') + "/notify"
                logger.info(f"Using public notification URI: {notification_uri}")
            else:
                notification_uri = f"https://{self._notification_host}:{self._notification_port}/notify"
                logger.info(f"Using local notification URI: {notification_uri}")
            
            # Initialize SubscriptionManager
            self._subscription_manager = SubscriptionManager(
                http_client=self.ieee2030_5_client,
                notification_uri=notification_uri,
            )
            
            # Initialize NotificationHandler
            self._notification_handler = NotificationHandler(
                http_client=self.ieee2030_5_client,
                subscription_manager=self._subscription_manager,
            )
            
            # Register notification handler with server
            self._notification_server.set_notification_handler(
                self._notification_handler.handle_notification
            )
            
            # Initialize TimeSyncClient (mandatory polling - /tm cannot be subscribed)
            time_sync_config = TimeSyncConfig(
                sync_interval_s=self.config.subscription.time_sync_interval,
            )
            self._time_sync_client = TimeSyncClient(
                http_client=self.ieee2030_5_client,
                config=time_sync_config,
            )
            
            # Start time sync loop
            await self._time_sync_client.start_sync_loop()
            
            # Setup subscription chain
            await self._subscription_manager.setup_subscriptions()
            
            logger.info(
                f"Subscription-based DER Control started - "
                f"Notification server on {self._notification_host}:{self._notification_port}"
            )
            
        except Exception as e:
            logger.error(f"Failed to start subscription control: {e}", exc_info=True)
            # Clean up partial initialization
            await self._stop_subscription_control()

    async def _stop_subscription_control(self) -> None:
        """Stop subscription-based control components."""
        # Stop time sync
        if self._time_sync_client:
            await self._time_sync_client.stop_sync_loop()
            self._time_sync_client = None
            logger.debug("Time sync client stopped")
        
        # Cleanup subscriptions
        if self._subscription_manager:
            await self._subscription_manager.cleanup()
            self._subscription_manager = None
            logger.debug("Subscription manager stopped")
        
        # Stop notification server
        if self._notification_server:
            await self._notification_server.stop()
            self._notification_server = None
            logger.debug("Notification server stopped")
        
        # Clear handler
        self._notification_handler = None
        
        logger.info("Subscription control components stopped")

    async def _reporting_loop(self) -> None:
        """
        Main reporting loop.
        
        Periodically sends DER status/availability to IEEE 2030.5 server.
        Triggers reconnection after consecutive failures exceed threshold.
        """
        poll_rate = self.config.ieee2030_5.poll_rate
        
        while self._running:
            try:
                await self._report_status()
                self._reporting_consecutive_failures = 0
            except Exception as e:
                self._reporting_consecutive_failures += 1
                logger.error(
                    f"Reporting error ({self._reporting_consecutive_failures}/"
                    f"{self._ieee2030_5_failure_threshold}): {e}"
                )
                if self._reporting_consecutive_failures >= self._ieee2030_5_failure_threshold:
                    logger.warning("Failure threshold reached — attempting IEEE 2030.5 reconnection")
                    reconnected = await self._reconnect_ieee2030_5()
                    if reconnected:
                        self._reporting_consecutive_failures = 0
                    else:
                        # Wait longer before next cycle in degraded state
                        await asyncio.sleep(300)
                        continue

            await asyncio.sleep(poll_rate)

    async def _report_status(self) -> None:
        """Report current BMS status to IEEE 2030.5 server."""
        snapshot = self.latest_snapshot
        if not snapshot:
            logger.debug("No BMS data available for reporting")
            return

        if not self._der_path:
            logger.debug("No DER path available for reporting")
            return

        # Convert to IEEE 2030.5 models
        der_status = self.adapter.snapshot_to_der_status(snapshot)
        der_availability = self.adapter.snapshot_to_der_availability(snapshot)
        
        # Get current alarm status from DERStatus (now a simple string)
        current_alarm = 0
        if der_status.alarmStatus:
            try:
                current_alarm = int(der_status.alarmStatus, 16)
            except (ValueError, TypeError):
                current_alarm = 0

        # Report to server
        soc_value = der_status.stateOfChargeStatus.value if der_status.stateOfChargeStatus else 0
        alarm_value = der_status.alarmStatus if der_status.alarmStatus else "00000000"
        logger.debug(
            f"Reporting DER status: system_soc={snapshot.system.total_soc:.1f}%, "
            f"avg_soc={snapshot.average_soc:.1f}%, "
            f"active_racks={len(snapshot.active_racks)}, "
            f"stateOfChargeStatus.value={soc_value}, "
            f"alarmStatus={alarm_value}"
        )
        
        try:
            await self.ieee2030_5_client.update_der_status(
                self._der_path,
                der_status,
            )
            await self.ieee2030_5_client.update_der_availability(
                self._der_path,
                der_availability,
            )
            
            # Check for alarm status changes and post LogEvents
            if self._edev_href:
                await self._check_and_post_alarm_events(current_alarm)
                
        except Exception as e:
            logger.error(f"Failed to report status: {e}")

    async def _check_and_post_alarm_events(self, current_alarm: int) -> None:
        """
        Check for alarm status changes and post LogEvents.
        
        Compares current alarm status with previous status and posts
        LogEvents for any bits that changed (set or cleared).
        
        Args:
            current_alarm: Current alarm status bitfield
        """
        import time
        
        previous = self._previous_alarm_status
        
        # Find changed bits
        changed_bits = previous ^ current_alarm
        
        if changed_bits == 0:
            # No changes
            return
        
        logger.info(f"Alarm status changed: {previous:08X} -> {current_alarm:08X}")
        
        # Check each bit (0-10 for standard IEEE 2030.5 alarms)
        for bit in range(11):
            bit_mask = 1 << bit
            
            if not (changed_bits & bit_mask):
                continue
            
            # This bit changed
            is_now_set = bool(current_alarm & bit_mask)
            
            # Create LogEvent
            self._log_event_id_counter += 1
            ts = int(time.time())
            
            if is_now_set:
                # Alarm triggered (normal -> abnormal)
                log_event_code = bit  # LogEventCode matches bit position
                details = LOG_EVENT_CODE_DESCRIPTIONS.get(
                    bit, f"DER fault bit {bit} triggered"
                )
            else:
                # Alarm cleared (abnormal -> normal)
                log_event_code = LogEventCode.DER_FAULT_CLEARED + bit  # 128 + bit
                alarm_name = LOG_EVENT_CODE_DESCRIPTIONS.get(bit, f"Bit {bit}")
                details = f"{alarm_name.replace(' detected', '')} cleared"
            
            log_event = LogEvent(
                createdDateTime=ts,
                functionSet=FunctionSetIdentifier.DER,  # 11
                logEventCode=log_event_code,
                logEventID=self._log_event_id_counter,
                logEventPEN=0,  # IEEE defined
                profileID=2,    # IEEE 2030.5
                details=details,
            )
            
            # Post the LogEvent
            try:
                await self.ieee2030_5_client.post_log_event(
                    self._edev_href,
                    log_event,
                )
                logger.info(
                    f"Posted LogEvent: id={log_event.logEventID}, "
                    f"code={log_event_code}, details={details}"
                )
            except Exception as e:
                logger.error(f"Failed to post LogEvent: {e}")
        
        # Update previous alarm status
        self._previous_alarm_status = current_alarm

    async def _recover_from_server(self) -> bool:
        """
        Recover MirrorUsagePoint data from server when local DB is empty.

        IEEE 2030.5 Section 10.11.3(b): Server creates UsagePoint for each MUP.
        Recovery path: GET /mup → GET /upt → GET /upt/{id}/mr → GET .../rt (×N)

        This method:
        1. GET /mup to find our MUP by deviceLFDI (latest by href)
        2. GET /upt to find matching UsagePoint by mRID
        3. GET /upt/{id}/mr to get MeterReadingList (descriptions + mRIDs)
        4. GET /upt/{id}/mr/{id}/rt for each reading to get ReadingType
        5. Populate DB tables: mirror_usage_point, mirror_meter_reading, meter_types
        6. Populate memory: _mup_href, _mup_mrid, _reading_mrids

        Returns:
            True if MUP was recovered (even partially), False if not found
        """
        our_lfdi = self.ieee2030_5_client.lfdi
        if not our_lfdi:
            logger.warning("[Server Recovery] No LFDI available, cannot recover")
            return False

        logger.info("=" * 60)
        logger.info("[Server Recovery] Attempting to recover MUP data from server...")
        logger.info("=" * 60)

        # Step 1: GET /mup → find our MUP by deviceLFDI
        try:
            mup_list = await self.ieee2030_5_client.get_mirror_usage_point_list()
        except Exception as e:
            logger.warning(f"[Server Recovery] Failed to GET /mup: {e}")
            return False

        our_mups = [
            m for m in (mup_list.MirrorUsagePoint or [])
            if m.deviceLFDI and m.deviceLFDI.upper() == our_lfdi.upper()
        ]
        if not our_mups:
            logger.info("[Server Recovery] No MirrorUsagePoint found for our LFDI on server")
            return False

        # Select MUP with highest href number (most recent, server ID auto-increment)
        def _href_sort_key(mup):
            try:
                return int(mup.href.split("/")[-1])
            except (ValueError, AttributeError, IndexError):
                return 0

        our_mups.sort(key=_href_sort_key, reverse=True)
        target_mup = our_mups[0]
        logger.info(
            f"[Server Recovery] Found {len(our_mups)} MUP(s) for our LFDI, "
            f"using latest: {target_mup.href} (mRID={target_mup.mRID})"
        )

        # Populate MUP in memory
        self._mup_href = target_mup.href
        self._mup_mrid = target_mup.mRID

        # Save MUP to DB
        self._save_mup_to_db(target_mup)

        # Step 2: GET /upt → find UsagePoint with matching mRID
        upt_href = None
        try:
            upt_list = await self.ieee2030_5_client.get_usage_point_list()
            for upt in (upt_list.UsagePoint or []):
                if upt.mRID and upt.mRID.upper() == target_mup.mRID.upper():
                    upt_href = upt.href
                    logger.info(f"[Server Recovery] Found matching UsagePoint: {upt_href}")
                    break

            if not upt_href:
                logger.warning(
                    "[Server Recovery] No matching UsagePoint found for mRID "
                    f"{target_mup.mRID} — readings cannot be recovered"
                )
                return True  # MUP recovered, readings will be re-registered
        except Exception as e:
            logger.warning(f"[Server Recovery] Failed to GET /upt: {e}")
            return True  # MUP recovered, readings will be re-registered

        # Step 3: GET /upt/{id}/mr → get MeterReadingList
        try:
            mr_list = await self.ieee2030_5_client.get_meter_reading_list(upt_href)
            mr_entries = mr_list.MeterReading or []
            logger.info(f"[Server Recovery] Found {len(mr_entries)} MeterReading(s) at {upt_href}/mr")
        except Exception as e:
            logger.warning(f"[Server Recovery] Failed to GET {upt_href}/mr: {e}")
            return True  # MUP recovered, readings will be re-registered

        # Step 4: For each MeterReading, cache mRID and GET ReadingType
        recovered_readings = 0
        for mr_entry in mr_entries:
            if not mr_entry.description or not mr_entry.mRID:
                continue

            # Cache reading mRID in memory
            key = self._description_to_reading_key(mr_entry.description)
            if key:
                self._reading_mrids[key] = mr_entry.mRID
                recovered_readings += 1

            # GET ReadingType for this MeterReading
            reading_type = None
            if mr_entry.ReadingTypeLink and mr_entry.ReadingTypeLink.href:
                try:
                    reading_type = await self.ieee2030_5_client.get_reading_type(
                        mr_entry.href
                    )
                except Exception as e:
                    logger.warning(
                        f"[Server Recovery] Failed to GET ReadingType for "
                        f"{mr_entry.description}: {e}"
                    )

            # Save MirrorMeterReading record to DB
            if self._db:
                mmr_record = MirrorMeterReadingRecord(
                    mup_href=self._mup_href,
                    href=mr_entry.href,
                    mrid=mr_entry.mRID,
                    description=mr_entry.description,
                    accumulation_behaviour=(
                        reading_type.accumulationBehaviour if reading_type else 0
                    ),
                    commodity=reading_type.commodity if reading_type else 1,
                    data_qualifier=(
                        reading_type.dataQualifier if reading_type else 0
                    ),
                    flow_direction=(
                        reading_type.flowDirection if reading_type else 0
                    ),
                    kind=reading_type.kind if reading_type else 0,
                    power_of_ten_multiplier=(
                        reading_type.powerOfTenMultiplier if reading_type else 0
                    ),
                    uom=reading_type.uom if reading_type else 0,
                )
                try:
                    self._db.save_mirror_meter_reading(mmr_record)
                except Exception as e:
                    logger.warning(
                        f"[Server Recovery] Failed to save MMR to DB: {e}"
                    )

            # Save meter_type record to DB
            if self._db and reading_type:
                try:
                    self._db.save_meter_type(MeterTypeRecord(
                        mup_href=self._mup_href,
                        description=mr_entry.description,
                        mrid=mr_entry.mRID,
                        uom_code=reading_type.uom,
                        kind=reading_type.kind,
                        commodity=reading_type.commodity,
                        flow_direction=reading_type.flowDirection,
                        accumulation_behaviour=reading_type.accumulationBehaviour,
                        power_of_ten_multiplier=reading_type.powerOfTenMultiplier,
                        is_active=True,
                    ))
                except Exception as e:
                    logger.warning(
                        f"[Server Recovery] Failed to save meter_type to DB: {e}"
                    )

        logger.info(
            f"[Server Recovery] Recovered {recovered_readings} reading mRIDs: "
            f"{list(self._reading_mrids.keys())}"
        )
        return True

    async def _register_meter(self) -> None:
        """
        Register MirrorUsagePoint (meter) with IEEE 2030.5 server.
        
        Uses multi-step process required by the server:
        1. Check if cached MUP exists in database
        2. POST MirrorUsagePoint without MirrorMeterReading
        3. POST each MirrorMeterReading individually to the MUP
        
        Creates meter readings for:
        - Total Current (A)
        - Total Power (kW)
        - Charge Energy (kWh)
        - Discharge Energy (kWh)
        - Max Temperature (°C)
        - Min Temperature (°C)
        - Avg Temperature (°C)
        """
        # First check if we have cached MUP from database
        if self._mup_href:
            logger.info(f"[Fast Recovery] Verifying cached MirrorUsagePoint: {self._mup_href}")
            try:
                # Verify it exists on server (IEEE 2030.5 資源有效性驗證)
                existing_mup = await self.ieee2030_5_client.get_mirror_usage_point(self._mup_href)
                if existing_mup:
                    logger.info(f"[Fast Recovery] MirrorUsagePoint verified on server - 200 OK")
                    # Fetch MirrorMeterReadingList from sub-resource /mmr
                    try:
                        mmr_list = await self.ieee2030_5_client.get_mirror_meter_reading_list(self._mup_href)
                        server_readings = mmr_list.MirrorMeterReading if mmr_list else []
                    except Exception as e:
                        logger.warning(f"[Fast Recovery] Could not fetch MirrorMeterReadingList: {e}")
                        server_readings = existing_mup.MirrorMeterReading or []
                    # Re-cache reading mRIDs and update database
                    if server_readings:
                        cached_count = self._cache_reading_mrids_from_server(server_readings)
                        # Update database with latest readings
                        self._save_meter_readings_to_db(self._mup_href, server_readings)
                        logger.info(f"[Fast Recovery] Synced {cached_count} reading mRIDs from server: {list(self._reading_mrids.keys())}")
                    return
                else:
                    logger.info("[Fast Recovery] MirrorUsagePoint not found on server (404), re-registering...")
                    # Clear href/cache but KEEP mRID for re-registration
                    # (IEEE 2030.5 Section 10.11.3(a)(4): server returns same URI for matching mRID)
                    if self._db:
                        self._db.delete_mirror_usage_point(self._mup_href)
                        logger.info(f"[Fast Recovery] Cleared stale MUP cache from database: {self._mup_href}")
                    self._mup_href = None
                    self._reading_mrids.clear()
                    # _mup_mrid is intentionally preserved
            except Exception as e:
                logger.info(f"[Fast Recovery] Could not verify cached MirrorUsagePoint: {e}, re-registering...")
                self._mup_href = None
                self._reading_mrids.clear()
                # _mup_mrid is intentionally preserved

        # Try server recovery when no cached MUP (DB empty or deleted)
        if not self._mup_href:
            recovered = await self._recover_from_server()
            if recovered and self._mup_href:
                logger.info(f"[Server Recovery] MUP recovered: {self._mup_href} (mRID={self._mup_mrid})")
                # Check which readings are still missing
                expected_keys = {
                    "current", "power", "charge_energy", "discharge_energy",
                    "max_temperature", "min_temperature", "avg_temperature",
                    "soh", "cycle_count",
                }
                missing_keys = expected_keys - set(self._reading_mrids.keys())
                if not missing_keys:
                    logger.info("[Server Recovery] All readings recovered — skip registration")
                    return

                # Re-register missing readings by POSTing all readings.
                # Server matches existing by mRID (→ 204) and creates missing (→ 201).
                logger.info(
                    f"[Server Recovery] {len(missing_keys)} readings missing: "
                    f"{missing_keys}, re-registering..."
                )
                try:
                    mup_with_readings = self.adapter.create_bms_mirror_usage_point(
                        device_lfdi=self.ieee2030_5_client.lfdi,
                        description="CUBE BMS Meter",
                        post_rate=self.config.ieee2030_5.poll_rate,
                        include_readings=True,
                        mup_mrid=self._mup_mrid,
                    )
                    readings = mup_with_readings.MirrorMeterReading
                    if readings:
                        await self.ieee2030_5_client.post_mirror_meter_reading_list(
                            self._mup_href, readings,
                        )
                    # Re-fetch from server to sync all reading mRIDs
                    try:
                        mmr_list = await self.ieee2030_5_client.get_mirror_meter_reading_list(self._mup_href)
                        if mmr_list and mmr_list.MirrorMeterReading:
                            self._cache_reading_mrids_from_server(mmr_list.MirrorMeterReading)
                            self._save_meter_readings_to_db(self._mup_href, mmr_list.MirrorMeterReading)
                    except Exception as e:
                        logger.warning(f"[Server Recovery] Could not re-fetch readings after re-register: {e}")
                    logger.info(
                        f"[Server Recovery] Re-registration complete, "
                        f"reading mRIDs: {list(self._reading_mrids.keys())}"
                    )
                except Exception as e:
                    logger.warning(f"[Server Recovery] Failed to re-register missing readings: {e}")
                return

        logger.info("[Full Registration] Creating new MirrorUsagePoint (meter)...")
        
        try:
            # Step 1: Create MirrorUsagePoint WITHOUT MirrorMeterReading
            # Reuse persisted mRID so server can match existing resource
            # (IEEE 2030.5 Section 10.11.3(a)(4): same mRID → 204 + same URI)
            mup = self.adapter.create_bms_mirror_usage_point(
                device_lfdi=self.ieee2030_5_client.lfdi,
                description="CUBE BMS Meter",
                post_rate=self.config.ieee2030_5.poll_rate,
                include_readings=False,  # Don't include readings for initial POST
                mup_mrid=self._mup_mrid,
            )
            
            # Register with server (POST)
            _, location = await self.ieee2030_5_client.create_mirror_usage_point(mup)
            self._mup_href = location
            self._mup_mrid = mup.mRID  # Persist the mRID used for this registration
            logger.info(f"Created MirrorUsagePoint at: {self._mup_href} (mRID={self._mup_mrid})")
            
            # Step 2: POST all MirrorMeterReading using MirrorMeterReadingList
            # Get the readings from adapter
            mup_with_readings = self.adapter.create_bms_mirror_usage_point(
                device_lfdi=self.ieee2030_5_client.lfdi,
                description="CUBE BMS Meter",
                post_rate=self.config.ieee2030_5.poll_rate,
                include_readings=True,
                mup_mrid=self._mup_mrid,
            )
            
            # POST all readings as a list
            readings = mup_with_readings.MirrorMeterReading
            if readings:
                success = await self.ieee2030_5_client.post_mirror_meter_reading_list(
                    self._mup_href,
                    readings,
                )
                if success:
                    logger.info(f"Registered {len(readings)} MirrorMeterReadings as list")
                else:
                    logger.warning("Failed to register MirrorMeterReadings as list")
            
            # Fetch the updated resource to cache reading mRIDs
            created_mup = await self.ieee2030_5_client.get_mirror_usage_point(self._mup_href)
            
            # Fetch MirrorMeterReadingList from sub-resource /mmr
            server_readings = []
            try:
                mmr_list = await self.ieee2030_5_client.get_mirror_meter_reading_list(self._mup_href)
                if mmr_list and mmr_list.MirrorMeterReading:
                    server_readings = mmr_list.MirrorMeterReading
            except Exception as e:
                logger.warning(f"Could not fetch MirrorMeterReadingList: {e}")
                # Fallback to inline readings if available
                if created_mup and created_mup.MirrorMeterReading:
                    server_readings = created_mup.MirrorMeterReading
            
            # Cache reading mRIDs for future updates
            if server_readings:
                cached_count = self._cache_reading_mrids_from_server(server_readings)
                logger.info(f"Registered MirrorUsagePoint with {cached_count} readings at: {self._mup_href}")
                logger.info(f"Cached reading mRIDs: {list(self._reading_mrids.keys())}")
            else:
                logger.info(f"Registered MirrorUsagePoint at: {self._mup_href} (no readings returned)")
            
            # Save MUP to database for caching
            if created_mup:
                self._save_mup_to_db(created_mup)
            
            # Save MirrorMeterReadings to database for caching
            if server_readings:
                self._save_meter_readings_to_db(self._mup_href, server_readings)
            
        except Exception as e:
            logger.warning(f"Failed to register MirrorUsagePoint: {e}")
            self._mup_href = None

    async def _metering_loop(self) -> None:
        """
        Metering data upload loop.
        
        Periodically uploads meter readings (SOC, Current, Power, Energy)
        to the IEEE 2030.5 server via MirrorUsagePoint.
        """
        # Use same poll rate as DER status, or default to 60 seconds
        poll_rate = getattr(self.config.ieee2030_5, 'meter_poll_rate', 
                          self.config.ieee2030_5.poll_rate)
        
        logger.info(f"Starting metering loop (interval: {poll_rate}s)")
        
        while self._running:
            try:
                await self._upload_meter_readings()
                self._metering_consecutive_failures = 0
            except Exception as e:
                self._metering_consecutive_failures += 1
                logger.error(
                    f"Metering error ({self._metering_consecutive_failures}/"
                    f"{self._ieee2030_5_failure_threshold}): {e}"
                )
                if self._metering_consecutive_failures >= self._ieee2030_5_failure_threshold:
                    logger.warning("Failure threshold reached — attempting IEEE 2030.5 reconnection")
                    reconnected = await self._reconnect_ieee2030_5()
                    if reconnected:
                        self._metering_consecutive_failures = 0
                    else:
                        await asyncio.sleep(300)
                        continue

            await asyncio.sleep(poll_rate)

    async def _upload_meter_readings(self) -> None:
        """
        Upload current BMS meter readings to IEEE 2030.5 server.

        Uses a 4-layer mRID recovery strategy to avoid generating random mRIDs:
          Layer 1: meter_types DB fallback (handled at startup in _load_cached_resources)
          Layer 2: Lightweight server recovery (GET /upt → GET /mr) with cooldown
          Layer 3: Partial upload — skip readings with missing mRIDs
          Layer 4: Full re-registration (last resort, after N consecutive partial uploads)
        """
        snapshot = self.latest_snapshot
        if not snapshot:
            logger.warning("No BMS data available for metering")
            return

        if not self._mup_href:
            logger.warning("No MirrorUsagePoint href available - skipping meter upload")
            return

        # Calculate SOH from active racks and update cycle tracking
        soh = None
        if snapshot.active_racks:
            soh = sum(r.soh for r in snapshot.active_racks) / len(snapshot.active_racks)
            
            # Update cycle tracking based on SOC changes
            current_soc = snapshot.average_soc
            if self._last_soc is not None:
                soc_delta = current_soc - self._last_soc
                
                if soc_delta > 0:
                    self._charge_accumulated += soc_delta
                elif soc_delta < 0:
                    self._discharge_accumulated += abs(soc_delta)
                
                if self._charge_accumulated >= 10.0 and self._discharge_accumulated >= 10.0:
                    self._cycle_count += 1
                    self._charge_accumulated -= 10.0
                    self._discharge_accumulated -= 10.0
                    logger.info(f"Cycle completed! Total cycles: {self._cycle_count}")
            
            self._last_soc = current_soc
            self._save_cycle_tracking()

        # --- mRID completeness check ---
        expected_keys = {
            "current", "power", "charge_energy", "discharge_energy",
            "max_temperature", "min_temperature", "avg_temperature",
            "soh", "cycle_count", "timestamp",
        }
        missing_keys = expected_keys - set(self._reading_mrids.keys())
        mrids_complete = len(missing_keys) == 0

        if self._reading_mrids:
            logger.debug(f"Using cached reading mRIDs: {list(self._reading_mrids.keys())}")
        if missing_keys:
            logger.info(f"[mRID Check] Missing keys: {missing_keys}")

        # --- Layer 2: Lightweight server recovery (if incomplete) ---
        if not mrids_complete:
            recovered = await self._recover_reading_mrids_from_server()
            if recovered:
                missing_keys = expected_keys - set(self._reading_mrids.keys())
                mrids_complete = len(missing_keys) == 0
                if mrids_complete:
                    logger.info("[Layer 2] Server recovery restored all mRIDs")
                else:
                    logger.info(f"[Layer 2] Server recovery partial, still missing: {missing_keys}")

        # --- Decide upload mode ---
        skip_missing = False
        needs_reading_type = False

        if mrids_complete:
            # Happy path: all mRIDs present, no ReadingType needed
            self._partial_upload_count = 0
        else:
            # --- Layer 4 check: too many consecutive partial uploads → full re-registration ---
            if self._partial_upload_count >= self._partial_upload_threshold:
                logger.warning(
                    f"[Layer 4] {self._partial_upload_count} consecutive partial uploads — "
                    f"triggering full re-registration (last resort)"
                )
                try:
                    # Clear state and re-register with ReadingType + new mRIDs
                    self._reading_mrids.clear()
                    self._mup_href = None
                    await self._register_meter()
                    self._partial_upload_count = 0
                    # After re-registration, mRIDs should be complete
                    missing_keys = expected_keys - set(self._reading_mrids.keys())
                    mrids_complete = len(missing_keys) == 0
                    if not mrids_complete:
                        logger.warning(f"[Layer 4] Re-registration done but still missing: {missing_keys}")
                        skip_missing = True
                        needs_reading_type = False
                    else:
                        logger.info("[Layer 4] Re-registration restored all mRIDs")
                except Exception as e:
                    logger.error(f"[Layer 4] Full re-registration failed: {e}")
                    skip_missing = True
                    needs_reading_type = False
            else:
                # --- Layer 3: partial upload — skip missing mRIDs ---
                self._partial_upload_count += 1
                skip_missing = True
                needs_reading_type = False
                logger.info(
                    f"[Layer 3] Partial upload ({self._partial_upload_count}/"
                    f"{self._partial_upload_threshold}), skipping: {missing_keys}"
                )

        # Convert BMS snapshot to meter readings
        readings = self.adapter.snapshot_to_meter_readings(
            snapshot,
            reading_mrids=self._reading_mrids,
            soh=soh,
            cycle_count=self._cycle_count,
            include_reading_type=needs_reading_type,
            skip_missing_mrids=skip_missing,
        )
        
        if readings and logger.isEnabledFor(logging.DEBUG):
            mrid_list = [(r.description, r.mRID) for r in readings]
            logger.debug(f"Meter readings mRIDs: {mrid_list}")

        # Upload
        soh_str = f"SOH={soh:.1f}%, " if soh else ""
        logger.info(
            f"Uploading meter readings to {self._mup_href}: "
            f"SOC={snapshot.system.total_soc:.1f}%, "
            f"Current={snapshot.system.total_current:.1f}A, "
            f"Power={snapshot.system.total_power:.1f}kW, "
            f"{soh_str}"
            f"Cycles={self._cycle_count}, "
            f"readings_count={len(readings)}"
        )
        
        if readings:
            success = await self.ieee2030_5_client.post_mirror_meter_reading_list(
                self._mup_href,
                readings,
            )
            
            self._record_meter_upload(readings, success)
            
            if success:
                logger.info(f"Successfully uploaded {len(readings)} meter readings")
                # Defense C: persist current mRIDs to DB after successful upload
                self._sync_reading_mrids_to_db()
            else:
                logger.warning("Failed to upload meter readings as list")
        else:
            logger.warning("No readings generated from snapshot")
    
    def _record_meter_upload(self, readings: list, success: bool) -> None:
        """Record meter types to SQLite and update in-memory counter."""
        reading_dicts = []
        
        # Map UOM code to type name
        uom_to_type = {
            5: "Current",           # A (安培)
            6: "Temperature",       # Kelvin
            23: "Temperature",      # °C
            29: "Voltage",          # V
            31: "Energy",           # J (焦耳)
            33: "Frequency",        # Hz
            38: "Power",            # W (實功)
            42: "Volume",           # m³
            61: "Power",            # VA (視在功率)
            63: "Power",            # var (虛功)
            65: "Power Factor",     # CosTheta
            67: "Voltage",          # V²
            69: "Current",          # A²
            71: "Energy",           # VAh (視在能量)
            72: "Energy",           # Wh (實功能量)
            73: "Energy",           # varh (虛功能量)
            106: "Capacity",        # Ah (安培小時)
            119: "Volume",          # ft³
            122: "Flow Rate",       # ft³/h
            125: "Flow Rate",       # m³/h
            128: "Volume",          # US gl
            129: "Flow Rate",       # US gl/h
            130: "Volume",          # IMP gl
            131: "Flow Rate",       # IMP gl/h
            132: "Energy",          # BTU
            133: "Power",           # BTU/h
            134: "Volume",          # Liter
            137: "Flow Rate",       # L/h
            140: "Pressure",        # PA(gauge)
            155: "Pressure",        # PA(absolute)
            169: "Energy",          # Therm
        }
        
        for r in readings:
            # Extract reading type info
            reading_uom = None
            reading_uom_name = None
            reading_kind = 0
            reading_type = None
            reading_mrid = None
            reading_flow_direction = 0
            reading_accumulation_behaviour = 0
            reading_power_of_ten_multiplier = 0
            reading_commodity = 1
            
            # Get mRID from MirrorMeterReading
            reading_mrid = getattr(r, "mRID", None)
            
            if hasattr(r, "ReadingType") and r.ReadingType:
                rt = r.ReadingType
                reading_uom = getattr(rt, "uom", None)
                reading_kind = getattr(rt, "kind", 0) or 0
                reading_flow_direction = getattr(rt, "flowDirection", 0) or 0
                reading_accumulation_behaviour = getattr(rt, "accumulationBehaviour", 0) or 0
                reading_power_of_ten_multiplier = getattr(rt, "powerOfTenMultiplier", 0) or 0
                reading_commodity = getattr(rt, "commodity", 1) or 1
                # Map UOM code to readable name (IEEE 2030.5 Table)
                if reading_uom is not None:
                    uom_names = {
                        0: "N/A",           # Not Applicable
                        5: "A",             # 安培 (RMS)
                        6: "K",             # Kelvin
                        23: "°C",           # 攝氏度
                        29: "V",            # 電壓
                        31: "J",            # 焦耳
                        33: "Hz",           # 頻率
                        38: "W",            # 實功功率
                        42: "m³",           # 體積
                        61: "VA",           # 視在功率
                        63: "var",          # 虛功功率
                        65: "cosθ",         # 功率因數
                        67: "V²",           # 伏特平方
                        69: "A²",           # 安培平方
                        71: "VAh",          # 視在能量
                        72: "Wh",           # 實功能量
                        73: "varh",         # 虛功能量
                        106: "Ah",          # 安培小時
                        119: "ft³",         # 立方英尺
                        122: "ft³/h",       # 立方英尺/小時
                        125: "m³/h",        # 立方公尺/小時
                        128: "US gal",      # 美制加侖
                        129: "US gal/h",    # 美制加侖/小時
                        130: "IMP gal",     # 英制加侖
                        131: "IMP gal/h",   # 英制加侖/小時
                        132: "BTU",         # 英熱單位
                        133: "BTU/h",       # 英熱單位/小時
                        134: "L",           # 公升
                        137: "L/h",         # 公升/小時
                        140: "Pa(g)",       # 表壓力
                        155: "Pa(a)",       # 絕對壓力
                        169: "thm",         # Therm
                    }
                    reading_uom_name = uom_names.get(reading_uom, f"UOM({reading_uom})")
                    reading_type = uom_to_type.get(reading_uom, "Measurement")
            
            # Get description from MirrorMeterReading
            description = getattr(r, "description", None) or ""
            
            # Get value and timestamp from Reading
            reading_value = None
            reading_timestamp = None
            
            if hasattr(r, "Reading") and r.Reading:
                reading_obj = r.Reading
                reading_value = getattr(reading_obj, "value", None)
                # Get timestamp from timePeriod if available
                if hasattr(reading_obj, "timePeriod") and reading_obj.timePeriod:
                    tp = reading_obj.timePeriod
                    start_time = getattr(tp, "start", None)
                    if start_time:
                        from datetime import datetime
                        try:
                            reading_timestamp = datetime.fromtimestamp(start_time).isoformat()
                        except:
                            reading_timestamp = str(start_time)
            
            # If no Reading, check lastUpdateTime
            if reading_timestamp is None:
                last_update = getattr(r, "lastUpdateTime", None)
                if last_update:
                    from datetime import datetime
                    try:
                        reading_timestamp = datetime.fromtimestamp(last_update).isoformat()
                    except:
                        reading_timestamp = str(last_update)
            
            if description:
                reading_dicts.append({
                    "type": reading_type or "Measurement",
                    "description": description,
                    "mrid": reading_mrid,
                    "value": reading_value,
                    "uom": reading_uom_name or "N/A",
                    "uom_code": reading_uom,
                    "kind": reading_kind,
                    "commodity": reading_commodity,
                    "flow_direction": reading_flow_direction,
                    "accumulation_behaviour": reading_accumulation_behaviour,
                    "power_of_ten_multiplier": reading_power_of_ten_multiplier,
                    "timestamp": reading_timestamp,
                })
        
        # Record meter types to SQLite database (persistent, no values)
        try:
            if self._db and self._mup_href and reading_dicts:
                types_count = self._db.update_meter_types_from_readings(
                    self._mup_href, reading_dicts
                )
                if types_count > 0:
                    logger.debug(f"Updated {types_count} meter types in SQLite")
        except Exception as e:
            logger.debug(f"Failed to save meter types to SQLite: {e}")

    async def get_battery_status(self) -> Optional[BMSSnapshot]:
        """
        Get current battery status.
        
        Returns:
            Current BMSSnapshot or None if not available
        """
        if not self.modbus_client.connected:
            return None
        return await self.modbus_client.read_snapshot()

    async def get_server_time(self):
        """Get time from IEEE 2030.5 server."""
        return await self.ieee2030_5_client.get_time()

    async def update_device_information(
        self,
        mf_id: int,
        mf_model: str,
        mf_serial_number: str,
        mf_ser_num: str,
        mf_date: int,
        mf_hw_ver: str,
        secondary_power: int,
        sw_act_time: int,
        gps_lat: str,
        gps_lon: str,
        mf_info: Optional[str] = None,
        sw_ver: Optional[str] = None,
        primary_power: int = PowerSourceType.MAINS,
    ) -> bool:
        """
        Update device information on IEEE 2030.5 server.
        
        Sends descriptive device information to the server including
        manufacturer details, serial number, and software version.
        
        Args:
            mf_id: Manufacturer ID (PEN - Private Enterprise Number)
            mf_model: Manufacturer model name/number
            mf_serial_number: Manufacturer serial number (long form)
            mf_ser_num: Manufacturer serial number (short form, required)
            mf_date: Manufacture date (Unix timestamp, required)
            mf_hw_ver: Hardware version (required)
            secondary_power: Secondary power source (PowerSourceType, required)
            sw_act_time: Software activation time (Unix timestamp, required)
            gps_lat: GPS latitude (required)
            gps_lon: GPS longitude (required)
            mf_info: Additional manufacturer info (e.g., device name)
            sw_ver: Software version string
            primary_power: Primary power source (PowerSourceType)
            
        Returns:
            True if successful
        """
        if not self.ieee2030_5_client._end_device:
            logger.warning("End device not registered, cannot update device information")
            return False
        
        edev_href = self.ieee2030_5_client._end_device.href
        if not edev_href:
            logger.warning("End device href not available")
            return False
        
        from bms_2030_5_client.models import GPSLocationType
        
        device_info = DeviceInformation(
            lFDI=self.ieee2030_5_client.lfdi,  # Already a hex string (40 chars)
            mfID=mf_id,
            mfModel=mf_model,
            mfSerNum=mf_ser_num,
            mfSerialNumber=mf_serial_number,
            mfDate=mf_date,
            mfHwVer=mf_hw_ver,
            mfInfo=mf_info,
            primaryPower=primary_power,
            secondaryPower=secondary_power,
            swVer=sw_ver,
            swActTime=sw_act_time,
            gpsLocation=GPSLocationType(lat=gps_lat, lon=gps_lon),
        )
        
        logger.info(f"Updating device information: {mf_model} ({mf_serial_number})")
        return await self.ieee2030_5_client.update_device_information(
            edev_href, device_info
        )

    async def get_device_information(self) -> Optional[DeviceInformation]:
        """
        Get device information from IEEE 2030.5 server.
        
        Returns:
            DeviceInformation or None if not available
        """
        if not self.ieee2030_5_client._end_device:
            logger.warning("End device not registered")
            return None
        
        edev_href = self.ieee2030_5_client._end_device.href
        if not edev_href:
            return None
        
        try:
            return await self.ieee2030_5_client.get_device_information(edev_href)
        except Exception as e:
            logger.warning(f"Failed to get device information: {e}")
            return None

    async def run_forever(self) -> None:
        """Run client until interrupted."""
        await self.start()
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
