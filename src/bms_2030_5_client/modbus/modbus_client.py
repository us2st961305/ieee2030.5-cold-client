"""
Modbus TCP client for CUBE BMS communication.

Based on CUBE 電池組暫存器通訊表 V1.0.3
"""

import asyncio
import logging
from typing import List, Optional

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from bms_2030_5_client.config import Config, ModbusConfig, RegisterConfig
from bms_2030_5_client.models import RackData, SystemData, BMSSnapshot

logger = logging.getLogger(__name__)


class ModbusClientError(Exception):
    """Modbus client error."""
    pass


class ModbusBMSClient:
    """
    Modbus TCP client for CUBE BMS.
    
    Handles communication with battery racks via Modbus TCP/IP protocol.
    - Refresh time: 500ms
    - Function codes: Read (0x03), Write (0x06)
    - Data length: 2 bytes
    - Rack register offset: 30
    - Maximum 24 racks (0-23)
    """

    # Register addresses (actual Modbus addresses, doc addresses - 1)
    # Documentation uses 1-based numbering, actual Modbus is 0-based offset
    SYSTEM_BASE_ADDR = 3999      # Doc: 4000, Actual: 3999
    RACK_BASE_ADDR = 6999        # Doc: 7000, Actual: 6999
    RACK_REGISTER_OFFSET = 30
    MAX_RACKS = 24

    # Number of registers to read
    SYSTEM_REGISTER_COUNT = 44   # Read 3999-4042 (Doc: 4000-4043) for allowed_power_DSC/CHG
    RACK_REGISTER_COUNT = 30

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 5.0,
        rack_count: int = 4,
    ):
        """
        Initialize Modbus BMS client.
        
        Args:
            host: BMS Modbus server IP address
            port: Modbus TCP port (default 502)
            unit_id: Modbus unit/slave ID
            timeout: Connection timeout in seconds
            rack_count: Number of battery racks to read
        """
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.rack_count = min(rack_count, self.MAX_RACKS)
        self._client: Optional[AsyncModbusTcpClient] = None
        self._connected = False
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(cls, config: Config) -> "ModbusBMSClient":
        """Create client from configuration."""
        return cls(
            host=config.modbus.host,
            port=config.modbus.port,
            unit_id=config.modbus.unit_id,
            timeout=config.modbus.timeout,
            rack_count=config.modbus.rack_count,
        )

    @property
    def connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self._client is not None

    async def connect(self) -> bool:
        """
        Connect to BMS Modbus server.
        
        Returns:
            True if connection successful
        """
        async with self._lock:
            if self._connected:
                return True

            try:
                self._client = AsyncModbusTcpClient(
                    host=self.host,
                    port=self.port,
                    timeout=self.timeout,
                )
                
                connected = await self._client.connect()
                if connected:
                    self._connected = True
                    logger.info(f"Connected to BMS at {self.host}:{self.port}")
                    return True
                else:
                    logger.error(f"Failed to connect to BMS at {self.host}:{self.port}")
                    return False
                    
            except Exception as e:
                logger.error(f"Connection error: {e}")
                self._connected = False
                return False

    async def disconnect(self) -> None:
        """Disconnect from BMS."""
        async with self._lock:
            if self._client:
                self._client.close()
                self._client = None
            self._connected = False
            logger.info("Disconnected from BMS")

    async def read_registers(
        self,
        address: int,
        count: int,
    ) -> List[int]:
        """
        Read holding registers from BMS.
        
        Args:
            address: Starting register address
            count: Number of registers to read
            
        Returns:
            List of register values
            
        Raises:
            ModbusClientError: If read fails
        """
        if not self.connected:
            raise ModbusClientError("Not connected to BMS")

        try:
            response = await self._client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.unit_id,
            )
            
            if response.isError():
                raise ModbusClientError(f"Modbus error reading address {address}: {response}")
            
            return list(response.registers)
            
        except ModbusException as e:
            raise ModbusClientError(f"Modbus exception: {e}") from e

    async def write_register(
        self,
        address: int,
        value: int,
    ) -> bool:
        """
        Write single holding register.
        
        Args:
            address: Register address
            value: Value to write
            
        Returns:
            True if write successful
        """
        if not self.connected:
            raise ModbusClientError("Not connected to BMS")

        try:
            response = await self._client.write_register(
                address=address,
                value=value,
                device_id=self.unit_id,
            )
            
            if response.isError():
                logger.error(f"Modbus error writing address {address}: {response}")
                return False
            
            return True
            
        except ModbusException as e:
            logger.error(f"Modbus exception: {e}")
            return False

    async def read_system_data(self) -> SystemData:
        """
        Read system-level data from registers 4000-4034.
        
        Returns:
            SystemData with current system status
        """
        registers = await self.read_registers(
            self.SYSTEM_BASE_ADDR,
            self.SYSTEM_REGISTER_COUNT,
        )
        return SystemData.from_registers(registers)

    async def read_rack_data(self, rack_id: int) -> RackData:
        """
        Read data for a single rack.
        
        Args:
            rack_id: Rack index (0-23)
            
        Returns:
            RackData for the specified rack
        """
        if rack_id < 0 or rack_id >= self.MAX_RACKS:
            raise ValueError(f"Invalid rack_id: {rack_id} (must be 0-{self.MAX_RACKS-1})")

        address = self.RACK_BASE_ADDR + (rack_id * self.RACK_REGISTER_OFFSET)
        registers = await self.read_registers(address, self.RACK_REGISTER_COUNT)
        return RackData.from_registers(rack_id, registers)

    async def read_all_racks(self) -> List[RackData]:
        """
        Read data from all configured racks.
        
        Returns:
            List of RackData for all racks
        """
        racks = []
        for rack_id in range(self.rack_count):
            try:
                rack_data = await self.read_rack_data(rack_id)
                racks.append(rack_data)
            except ModbusClientError as e:
                logger.warning(f"Failed to read rack {rack_id}: {e}")
        return racks

    async def read_snapshot(self) -> BMSSnapshot:
        """
        Read complete BMS snapshot including system and all racks.
        
        Returns:
            BMSSnapshot with current BMS state
        """
        system_data = await self.read_system_data()
        racks_data = await self.read_all_racks()
        return BMSSnapshot(system=system_data, racks=racks_data)

    async def set_rack_mode(self, rack_id: int, mode: int) -> bool:
        """
        Set operational mode for a rack.
        
        Args:
            rack_id: Rack index
            mode: Operational mode value
            
        Returns:
            True if successful
        """
        # Control register is typically at offset 25 from rack base
        address = self.RACK_BASE_ADDR + (rack_id * self.RACK_REGISTER_OFFSET) + 25
        return await self.write_register(address, mode)


class BMSDataCollector:
    """
    Continuous data collector for BMS.
    
    Periodically reads BMS data and provides latest snapshot.
    """

    def __init__(
        self,
        client: ModbusBMSClient,
        refresh_interval: float = 60.0,
    ):
        """
        Initialize data collector.
        
        Args:
            client: ModbusBMSClient instance
            refresh_interval: Data refresh interval in seconds (default: 60s / 1 minute)
        """
        self.client = client
        self.refresh_interval = refresh_interval
        self._latest_snapshot: Optional[BMSSnapshot] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[callable] = []

    @property
    def latest_snapshot(self) -> Optional[BMSSnapshot]:
        """Get latest BMS snapshot."""
        return self._latest_snapshot

    def add_callback(self, callback: callable) -> None:
        """Add callback for new data notification."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: callable) -> None:
        """Remove callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start(self) -> None:
        """Start continuous data collection."""
        if self._running:
            return

        if not self.client.connected:
            await self.client.connect()

        self._running = True
        self._task = asyncio.create_task(self._collection_loop())
        logger.info(f"BMS data collector started (interval: {self.refresh_interval}s)")

    async def stop(self) -> None:
        """Stop data collection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("BMS data collector stopped")

    async def _collection_loop(self) -> None:
        """Main collection loop."""
        while self._running:
            try:
                snapshot = await self.client.read_snapshot()
                self._latest_snapshot = snapshot
                
                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(snapshot)
                        else:
                            callback(snapshot)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

            except ModbusClientError as e:
                logger.error(f"BMS read error: {e}")
                # Try to reconnect
                await self.client.disconnect()
                await asyncio.sleep(1.0)
                await self.client.connect()

            except Exception as e:
                logger.error(f"Unexpected error in collection loop: {e}")

            await asyncio.sleep(self.refresh_interval)
