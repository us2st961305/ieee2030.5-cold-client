"""
Main BMS IEEE 2030.5 Client.

Integrates Modbus BMS communication with IEEE 2030.5 server reporting.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable, List, Union, Dict
from pathlib import Path

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
)
from bms_2030_5_client.subscription import (
    NotificationServer,
    NotificationServerConfig,
    SubscriptionManager,
    SubscriptionManagerConfig,
    NotificationHandler,
    NotificationHandlerConfig,
    TimeSyncClient,
    TimeSyncConfig,
)

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
        self._reporting_task: Optional[asyncio.Task] = None
        self._metering_task: Optional[asyncio.Task] = None
        self._battery_status_task: Optional[asyncio.Task] = None
        self._edev_href: Optional[str] = None  # EndDevice href (e.g., /edev/97)
        self._der_path: Optional[str] = None
        self._mup_href: Optional[str] = None  # MirrorUsagePoint href
        self._reading_mrids: Dict[str, str] = {}  # Cached reading mRIDs
        self._callbacks: List[Callable] = []
        
        # Alarm tracking for LogEvent
        self._previous_alarm_status: int = 0  # Previous alarm status (bitfield)
        self._log_event_id_counter: int = 0  # Unique LogEvent ID counter
        
        # Cycle tracking (charge >10% + discharge >10% = 1 cycle)
        self._cycle_count: int = 0  # Total completed cycles
        self._last_soc: Optional[float] = None  # Last recorded SOC
        self._charge_accumulated: float = 0.0  # Accumulated charge % in current cycle
        self._discharge_accumulated: float = 0.0  # Accumulated discharge % in current cycle
        
        # DER Control components (initialized after connection)
        self._der_client: Optional[DERClient] = None
        self._power_controller: Optional[SafePowerController] = None
        
        # Subscription/Notification components (initialized when enabled)
        self._notification_server: Optional[NotificationServer] = None
        self._subscription_manager: Optional[SubscriptionManager] = None
        self._notification_handler: Optional[NotificationHandler] = None
        self._time_sync_client: Optional[TimeSyncClient] = None

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
            logger.info("Checking for existing EndDevice by sFDI...")
            try:
                # First check if device already exists
                existing_edev = await self.ieee2030_5_client.find_end_device_by_sfdi()
                
                if existing_edev:
                    logger.info(f"Found existing EndDevice: {existing_edev.href}")
                    self._edev_href = existing_edev.href
                else:
                    # Register new device
                    logger.info("No existing device found, registering new EndDevice...")
                    end_device = await self.ieee2030_5_client.register_end_device(
                        pin=self.config.ieee2030_5.pin
                    )
                    logger.info(f"Registered end device: {end_device.href}")
                    self._edev_href = end_device.href
                
                # Get or create DER resource and build complete path
                if self._edev_href:
                    logger.info("Getting or creating DER resource...")
                    der = await self.ieee2030_5_client.get_or_create_der(
                        description="CUBE Battery Management System"
                    )
                    if der and der.href:
                        self._der_path = der.href
                        logger.info(f"Using DER path: {self._der_path}")
                    else:
                        logger.warning("Could not get or create DER resource")
                    
            except Exception as e:
                logger.warning(f"Registration/lookup failed: {e}")
                import traceback
                traceback.print_exc()

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
                logger.warning(f"Failed to update device information: {e}")
                import traceback
                traceback.print_exc()

        # Start data collection
        await self.data_collector.start()

        # Start reporting task
        self._running = True
        self._reporting_task = asyncio.create_task(self._reporting_loop())

        # Start metering task if enabled
        if self.enable_metering and self._mup_href:
            self._metering_task = asyncio.create_task(self._metering_loop())

        # Start battery status reporting to Supabase
        self._battery_status_task = asyncio.create_task(self._battery_status_loop())

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
        
        # Stop reporting task
        if self._reporting_task:
            self._reporting_task.cancel()
            try:
                await self._reporting_task
            except asyncio.CancelledError:
                pass
            self._reporting_task = None

        # Stop metering task
        if self._metering_task:
            self._metering_task.cancel()
            try:
                await self._metering_task
            except asyncio.CancelledError:
                pass
            self._metering_task = None

        # Stop battery status task
        if self._battery_status_task:
            self._battery_status_task.cancel()
            try:
                await self._battery_status_task
            except asyncio.CancelledError:
                pass
            self._battery_status_task = None

        # Stop DER Control
        if self._der_client:
            await self._der_client.stop()
            self._der_client = None
            logger.info("DER Control stopped")

        # Stop subscription components
        await self._stop_subscription_control()

        # Stop data collection
        await self.data_collector.stop()

        # Disconnect from servers
        await self.modbus_client.disconnect()
        await self.ieee2030_5_client.disconnect()

        logger.info("BMS Client stopped")

    async def _start_der_control(self) -> None:
        """
        Initialize and start DER Control polling.
        
        This enables:
        - FSA (FunctionSetAssignments) discovery and monitoring
        - DERProgram management with primacy handling
        - DERControl event execution
        - Response reporting
        
        ⚠️ Safety: Power control runs in simulation mode by default
        """
        try:
            # Initialize SafePowerController (simulation mode by default)
            power_config = PowerControlConfig.from_env()
            self._power_controller = SafePowerController(power_config)
            
            logger.info(
                f"SafePowerController initialized "
                f"(simulation_mode={power_config.simulation_mode})"
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
            logger.error(f"Failed to start DER Control: {e}")
            import traceback
            traceback.print_exc()
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
        
        ⚠️ Safety: Power control runs in simulation mode by default
        """
        try:
            # Initialize SafePowerController (simulation mode by default)
            power_config = PowerControlConfig.from_env()
            self._power_controller = SafePowerController(power_config)
            
            logger.info(
                f"SafePowerController initialized "
                f"(simulation_mode={power_config.simulation_mode})"
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
            logger.error(f"Failed to start subscription control: {e}")
            import traceback
            traceback.print_exc()
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
        """
        poll_rate = self.config.ieee2030_5.poll_rate
        
        while self._running:
            try:
                await self._report_status()
            except Exception as e:
                logger.error(f"Reporting error: {e}")

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

    async def _register_meter(self) -> None:
        """
        Register MirrorUsagePoint (meter) with IEEE 2030.5 server.
        
        Uses multi-step process required by the server:
        1. POST MirrorUsagePoint without MirrorMeterReading
        2. POST each MirrorMeterReading individually to the MUP
        
        Creates meter readings for:
        - Total Current (A)
        - Total Power (kW)
        - Charge Energy (kWh)
        - Discharge Energy (kWh)
        - Max Temperature (°C)
        - Min Temperature (°C)
        - Avg Temperature (°C)
        """
        logger.info("Registering MirrorUsagePoint (meter)...")
        
        try:
            # Step 1: Create MirrorUsagePoint WITHOUT MirrorMeterReading
            mup = self.adapter.create_bms_mirror_usage_point(
                device_lfdi=self.ieee2030_5_client.lfdi,
                description="CUBE BMS Meter",
                post_rate=self.config.ieee2030_5.poll_rate,
                include_readings=False,  # Don't include readings for initial POST
            )
            
            # Register with server (POST)
            _, location = await self.ieee2030_5_client.create_mirror_usage_point(mup)
            self._mup_href = location
            logger.info(f"Created MirrorUsagePoint at: {self._mup_href}")
            
            # Step 2: POST all MirrorMeterReading using MirrorMeterReadingList
            # Get the readings from adapter
            mup_with_readings = self.adapter.create_bms_mirror_usage_point(
                device_lfdi=self.ieee2030_5_client.lfdi,
                description="CUBE BMS Meter",
                post_rate=self.config.ieee2030_5.poll_rate,
                include_readings=True,
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
            
            # Cache reading mRIDs for future updates
            if created_mup and created_mup.MirrorMeterReading:
                for reading in created_mup.MirrorMeterReading:
                    if reading.description and reading.mRID:
                        # Map description to mRID
                        name = reading.description.lower().replace(" ", "_")
                        if "soc" in name:
                            self._reading_mrids["soc"] = reading.mRID
                        elif "current" in name:
                            self._reading_mrids["current"] = reading.mRID
                        elif "power" in name:
                            self._reading_mrids["power"] = reading.mRID
                        elif "charge" in name and "discharge" not in name:
                            self._reading_mrids["charge_energy"] = reading.mRID
                        elif "discharge" in name:
                            self._reading_mrids["discharge_energy"] = reading.mRID
                        elif "max" in name and "temp" in name:
                            self._reading_mrids["max_temperature"] = reading.mRID
                        elif "min" in name and "temp" in name:
                            self._reading_mrids["min_temperature"] = reading.mRID
                        elif "avg" in name and "temp" in name:
                            self._reading_mrids["avg_temperature"] = reading.mRID
            
            logger.info(f"Registered MirrorUsagePoint with {len(self._reading_mrids)} readings at: {self._mup_href}")
            
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
            except Exception as e:
                logger.error(f"Metering error: {e}")

            await asyncio.sleep(poll_rate)

    async def _upload_meter_readings(self) -> None:
        """Upload current BMS meter readings to IEEE 2030.5 server."""
        snapshot = self.latest_snapshot
        if not snapshot:
            logger.debug("No BMS data available for metering")
            return

        if not self._mup_href:
            logger.debug("No MirrorUsagePoint href available")
            return

        # Convert BMS snapshot to meter readings
        readings = self.adapter.snapshot_to_meter_readings(
            snapshot,
            reading_mrids=self._reading_mrids,
        )

        # Upload all readings as a list
        logger.debug(
            f"Uploading meter readings: SOC={snapshot.system.total_soc:.1f}%, "
            f"Current={snapshot.system.total_current:.1f}A, "
            f"Power={snapshot.system.total_power:.1f}kW"
        )
        
        if readings:
            success = await self.ieee2030_5_client.post_mirror_meter_reading_list(
                self._mup_href,
                readings,
            )
            if success:
                logger.debug(f"Uploaded {len(readings)} meter readings as list")
            else:
                logger.warning("Failed to upload meter readings as list")

    async def _battery_status_loop(self) -> None:
        """
        Battery status reporting loop.
        
        Periodically sends battery health metrics (SOH, cycles) to Supabase.
        Sends every 5 minutes (300 seconds).
        """
        import httpx
        
        interval = 300  # 5 minutes
        supabase_url = "https://tspjubrehulrjhreptva.supabase.co/functions/v1/battery-status"
        
        logger.info(f"Starting battery status reporting loop (interval: {interval}s)")
        
        while self._running:
            try:
                await self._send_battery_status(supabase_url)
            except Exception as e:
                logger.error(f"Battery status reporting error: {e}")

            await asyncio.sleep(interval)

    async def _send_battery_status(self, url: str) -> None:
        """Send battery status to Supabase endpoint."""
        import httpx
        
        # Get device LFDI
        lfdi = self.ieee2030_5_client.lfdi
        if not lfdi:
            logger.warning("Cannot send battery status: LFDI not available")
            return
        
        # Get latest snapshot for real data
        snapshot = self.latest_snapshot
        
        # Calculate average SOH from all active racks
        soh = 80.0  # Default value
        if snapshot and snapshot.active_racks:
            soh = sum(r.soh for r in snapshot.active_racks) / len(snapshot.active_racks)
            
            # Update cycle tracking based on SOC changes
            current_soc = snapshot.average_soc
            if self._last_soc is not None:
                soc_delta = current_soc - self._last_soc
                
                if soc_delta > 0:
                    # Charging: accumulate charge %
                    self._charge_accumulated += soc_delta
                elif soc_delta < 0:
                    # Discharging: accumulate discharge %
                    self._discharge_accumulated += abs(soc_delta)
                
                # Check if a complete cycle is reached (charge >10% AND discharge >10%)
                if self._charge_accumulated >= 10.0 and self._discharge_accumulated >= 10.0:
                    self._cycle_count += 1
                    # Reset accumulators, keeping excess
                    self._charge_accumulated -= 10.0
                    self._discharge_accumulated -= 10.0
                    logger.info(f"Cycle completed! Total cycles: {self._cycle_count}")
            
            self._last_soc = current_soc
        
        payload = {
            "lfdi": lfdi,
            "cycles": self._cycle_count,
            "soh": round(soh, 2)
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code in (200, 201):
                    logger.info(
                        f"Battery status sent successfully: LFDI={lfdi}, "
                        f"SOH={payload['soh']:.2f}%, Cycles={self._cycle_count}"
                    )
                else:
                    logger.warning(
                        f"Battery status upload failed: {response.status_code} - {response.text}"
                    )
        except Exception as e:
            logger.error(f"Failed to send battery status: {e}")

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
