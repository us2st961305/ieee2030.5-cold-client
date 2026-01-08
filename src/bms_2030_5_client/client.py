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
    """

    def __init__(
        self,
        config: Config,
        auto_register: bool = True,
        enable_metering: bool = True,
    ):
        """
        Initialize BMS Client.
        
        Args:
            config: Configuration object
            auto_register: Automatically register with 2030.5 server
            enable_metering: Enable meter data upload (MirrorUsagePoint)
        """
        self.config = config
        self.auto_register = auto_register
        self.enable_metering = enable_metering
        
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
        self._edev_href: Optional[str] = None  # EndDevice href (e.g., /edev/97)
        self._der_path: Optional[str] = None
        self._mup_href: Optional[str] = None  # MirrorUsagePoint href
        self._reading_mrids: Dict[str, str] = {}  # Cached reading mRIDs
        self._callbacks: List[Callable] = []

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

        # Stop data collection
        await self.data_collector.stop()

        # Disconnect from servers
        await self.modbus_client.disconnect()
        await self.ieee2030_5_client.disconnect()

        logger.info("BMS Client stopped")

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

        # Report to server
        logger.debug(f"Reporting DER status: SOC={snapshot.average_soc:.1f}%")
        
        try:
            await self.ieee2030_5_client.update_der_status(
                self._der_path,
                der_status,
            )
            await self.ieee2030_5_client.update_der_availability(
                self._der_path,
                der_availability,
            )
        except Exception as e:
            logger.error(f"Failed to report status: {e}")

    async def _register_meter(self) -> None:
        """
        Register MirrorUsagePoint (meter) with IEEE 2030.5 server.
        
        Uses two-step process required by the server:
        1. POST MirrorUsagePoint without MirrorMeterReading
        2. PUT MirrorUsagePoint with MirrorMeterReading
        
        Creates meter readings for:
        - Total SOC (%)
        - Total Current (A)
        - Total Power (kW)
        - Charge Energy (kWh)
        - Discharge Energy (kWh)
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
            
            # Step 2: Update MirrorUsagePoint WITH MirrorMeterReading (PUT)
            mup_with_readings = self.adapter.create_bms_mirror_usage_point(
                device_lfdi=self.ieee2030_5_client.lfdi,
                description="CUBE BMS Meter",
                post_rate=self.config.ieee2030_5.poll_rate,
                include_readings=True,  # Include readings for PUT update
            )
            # Use same mRID as created resource
            mup_with_readings.mRID = mup.mRID
            
            success = await self.ieee2030_5_client.update_mirror_usage_point(
                self._mup_href,
                mup_with_readings,
            )
            
            if success:
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
                
                logger.info(f"Registered MirrorUsagePoint with readings at: {self._mup_href}")
            else:
                logger.warning("Failed to update MirrorUsagePoint with readings")
            
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

        # Upload each reading
        logger.debug(
            f"Uploading meter readings: SOC={snapshot.system.total_soc:.1f}%, "
            f"Current={snapshot.system.total_current:.1f}A, "
            f"Power={snapshot.system.total_power:.1f}kW"
        )
        
        uploaded_count = 0
        for reading in readings:
            try:
                success = await self.ieee2030_5_client.update_mirror_meter_reading(
                    self._mup_href,
                    reading,
                )
                if success:
                    uploaded_count += 1
            except Exception as e:
                logger.error(f"Failed to upload {reading.description}: {e}")
        
        logger.debug(f"Uploaded {uploaded_count}/{len(readings)} meter readings")

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
