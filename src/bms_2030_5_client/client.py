"""
Main BMS IEEE 2030.5 Client.

Integrates Modbus BMS communication with IEEE 2030.5 server reporting.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable, List, Union
from pathlib import Path

from bms_2030_5_client.config import Config
from bms_2030_5_client.modbus import ModbusBMSClient, BMSDataCollector
from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client
from bms_2030_5_client.adapters import BMSAdapter
from bms_2030_5_client.models import BMSSnapshot, DERStatus, DERAvailability

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
    ):
        """
        Initialize BMS Client.
        
        Args:
            config: Configuration object
            auto_register: Automatically register with 2030.5 server
        """
        self.config = config
        self.auto_register = auto_register
        
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
        self._der_path: Optional[str] = None
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

        # Register with server
        if self.auto_register:
            logger.info("Registering end device...")
            try:
                end_device = await self.ieee2030_5_client.register_end_device(
                    pin=self.config.ieee2030_5.pin
                )
                logger.info(f"Registered end device: {end_device.href}")
                
                # Get DER path for status updates
                if end_device.DERListLink:
                    self._der_path = end_device.DERListLink
            except Exception as e:
                logger.warning(f"Registration failed: {e}")

        # Start data collection
        await self.data_collector.start()

        # Start reporting task
        self._running = True
        self._reporting_task = asyncio.create_task(self._reporting_loop())

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
