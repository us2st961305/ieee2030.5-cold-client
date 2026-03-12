"""
Modbus TCP client for CUBE BMS communication.

Based on CUBE 電池組暫存器通訊表 V1.0.3
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, List, Optional

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from bms_2030_5_client.config import Config, ModbusConfig, RegisterConfig
from bms_2030_5_client.models import RackData, SystemData, BMSSnapshot

logger = logging.getLogger(__name__)


class ModbusClientError(Exception):
    """Modbus client error."""
    pass


class ModbusConnectionState(Enum):
    """Modbus connection health states."""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    UNSTABLE = "unstable"      # Reconnecting with backoff
    DEGRADED = "degraded"      # Max retries exceeded, low-frequency retry


@dataclass
class ModbusHealthStatus:
    """Modbus connection health status for external consumption."""
    state: ModbusConnectionState = ModbusConnectionState.DISCONNECTED
    consecutive_failures: int = 0
    last_success_time: datetime | None = None
    last_failure_time: datetime | None = None
    last_error: str | None = None
    total_reconnects: int = 0

    def is_data_fresh(self, max_age_s: float = 300.0) -> bool:
        """
        Check if latest data is still considered fresh.

        Args:
            max_age_s: Maximum acceptable age in seconds.

        Returns:
            True if last success was within max_age_s.
        """
        if self.last_success_time is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self.last_success_time).total_seconds()
        return elapsed <= max_age_s

    def to_dict(self) -> dict:
        """Serialize to dict for JSON."""
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "last_success_time": (
                self.last_success_time.isoformat() if self.last_success_time else None
            ),
            "last_failure_time": (
                self.last_failure_time.isoformat() if self.last_failure_time else None
            ),
            "last_error": self.last_error,
            "total_reconnects": self.total_reconnects,
            "data_fresh": self.is_data_fresh(),
        }


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
        read_max_retries: int = 3,
        read_retry_base_delay: float = 0.1,
    ):
        """
        Initialize Modbus BMS client.
        
        Args:
            host: BMS Modbus server IP address
            port: Modbus TCP port (default 502)
            unit_id: Modbus unit/slave ID
            timeout: Connection timeout in seconds
            rack_count: Number of battery racks to read
            read_max_retries: Max retries per read/write operation
            read_retry_base_delay: Base delay between retries in seconds
        """
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.rack_count = min(rack_count, self.MAX_RACKS)
        self._read_max_retries = read_max_retries
        self._read_retry_base_delay = read_retry_base_delay
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
            read_max_retries=getattr(config.modbus, "read_max_retries", 3),
            read_retry_base_delay=getattr(config.modbus, "read_retry_base_delay", 0.1),
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
        Read holding registers from BMS with retry and lock protection.
        
        Args:
            address: Starting register address
            count: Number of registers to read
            
        Returns:
            List of register values
            
        Raises:
            ModbusClientError: If read fails after all retries
        """
        if not self.connected:
            raise ModbusClientError("Not connected to BMS")

        async with self._lock:
            last_error: Exception | None = None
            for attempt in range(self._read_max_retries):
                try:
                    response = await self._client.read_holding_registers(
                        address=address,
                        count=count,
                        device_id=self.unit_id,
                    )
                    if response.isError():
                        raise ModbusClientError(
                            f"Modbus error reading address {address}: {response}"
                        )
                    return list(response.registers)
                except (ModbusException, ModbusClientError) as e:
                    last_error = e
                    if attempt < self._read_max_retries - 1:
                        delay = self._read_retry_base_delay * (2 ** attempt)
                        logger.warning(
                            f"Modbus read retry {attempt + 1}/{self._read_max_retries} "
                            f"for address {address} (delay {delay:.2f}s): {e}"
                        )
                        await asyncio.sleep(delay)
            raise ModbusClientError(
                f"Failed to read address {address} after {self._read_max_retries} attempts"
            ) from last_error

    async def write_register(
        self,
        address: int,
        value: int,
    ) -> bool:
        """
        Write single holding register with retry and lock protection.
        
        Args:
            address: Register address
            value: Value to write
            
        Returns:
            True if write successful
        """
        if not self.connected:
            raise ModbusClientError("Not connected to BMS")

        async with self._lock:
            for attempt in range(self._read_max_retries):
                try:
                    response = await self._client.write_register(
                        address=address,
                        value=value,
                        device_id=self.unit_id,
                    )
                    if response.isError():
                        logger.error(
                            f"Modbus error writing address {address}: {response}"
                        )
                        if attempt < self._read_max_retries - 1:
                            delay = self._read_retry_base_delay * (2 ** attempt)
                            await asyncio.sleep(delay)
                            continue
                        return False
                    return True
                except ModbusException as e:
                    logger.error(
                        f"Modbus write exception (attempt {attempt + 1}): {e}"
                    )
                    if attempt < self._read_max_retries - 1:
                        delay = self._read_retry_base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
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
    Manages connection health state: CONNECTED → UNSTABLE → DEGRADED.
    """

    # Transition to UNSTABLE after this many consecutive failures
    UNSTABLE_THRESHOLD = 2
    # Transition to DEGRADED after this many consecutive failures
    DEGRADED_THRESHOLD = 10

    def __init__(
        self,
        client: ModbusBMSClient,
        refresh_interval: float = 60.0,
        degraded_retry_interval: float = 300.0,
    ):
        """
        Initialize data collector.
        
        Args:
            client: ModbusBMSClient instance
            refresh_interval: Data refresh interval in seconds (default: 60s / 1 minute)
            degraded_retry_interval: Retry interval when in DEGRADED state (default: 300s)
        """
        self.client = client
        self.refresh_interval = refresh_interval
        self.degraded_retry_interval = degraded_retry_interval
        self._latest_snapshot: Optional[BMSSnapshot] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[callable] = []
        self._state_callbacks: List[Callable[[ModbusHealthStatus], None]] = []
        self._reconnect_delay: float = 1.0
        self._health = ModbusHealthStatus()

    @property
    def latest_snapshot(self) -> Optional[BMSSnapshot]:
        """Get latest BMS snapshot."""
        return self._latest_snapshot

    @property
    def health_status(self) -> ModbusHealthStatus:
        """Get current Modbus connection health status (read-only copy)."""
        return self._health

    def add_callback(self, callback: callable) -> None:
        """Add callback for new data notification."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: callable) -> None:
        """Remove callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def add_state_callback(self, callback: Callable[[ModbusHealthStatus], None]) -> None:
        """Add callback for health state changes."""
        self._state_callbacks.append(callback)

    def _transition_state(self, new_state: ModbusConnectionState) -> None:
        """
        Transition to a new connection state, log, and notify callbacks.
        """
        old_state = self._health.state
        if old_state == new_state:
            return
        self._health.state = new_state
        logger.warning(
            f"Modbus connection state: {old_state.value} → {new_state.value} "
            f"(failures={self._health.consecutive_failures})"
        )
        for cb in self._state_callbacks:
            try:
                cb(self._health)
            except Exception as e:
                logger.error(f"State callback error: {e}")

    async def start(self) -> None:
        """Start continuous data collection."""
        if self._running:
            return

        if not self.client.connected:
            connected = await self.client.connect()
            if connected:
                self._transition_state(ModbusConnectionState.CONNECTED)
            # Even if connect fails, start the loop — it will handle reconnect

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
        self._transition_state(ModbusConnectionState.DISCONNECTED)
        logger.info("BMS data collector stopped")

    async def _collection_loop(self) -> None:
        """Main collection loop with state-machine-based reconnect."""
        while self._running:
            # --- DEGRADED: low-frequency retry ---
            if self._health.state == ModbusConnectionState.DEGRADED:
                logger.info(
                    f"Modbus DEGRADED — retrying in {self.degraded_retry_interval:.0f}s"
                )
                await asyncio.sleep(self.degraded_retry_interval)
                try:
                    await self.client.disconnect()
                    if await self.client.connect():
                        self._health.total_reconnects += 1
                        # Try a read to confirm
                        snapshot = await self.client.read_snapshot()
                        self._latest_snapshot = snapshot
                        self._health.consecutive_failures = 0
                        self._health.last_success_time = datetime.now(timezone.utc)
                        self._reconnect_delay = 1.0
                        self._transition_state(ModbusConnectionState.CONNECTED)
                        self._notify_data_callbacks(snapshot)
                except Exception as e:
                    self._health.last_error = str(e)
                    self._health.last_failure_time = datetime.now(timezone.utc)
                    logger.error(f"Modbus DEGRADED retry failed: {e}")
                continue

            # --- CONNECTED / UNSTABLE: normal read ---
            try:
                snapshot = await self.client.read_snapshot()
                self._latest_snapshot = snapshot
                self._health.consecutive_failures = 0
                self._health.last_success_time = datetime.now(timezone.utc)
                self._reconnect_delay = 1.0

                if self._health.state != ModbusConnectionState.CONNECTED:
                    self._transition_state(ModbusConnectionState.CONNECTED)

                self._notify_data_callbacks(snapshot)

            except ModbusClientError as e:
                self._health.consecutive_failures += 1
                self._health.last_failure_time = datetime.now(timezone.utc)
                self._health.last_error = str(e)
                logger.error(
                    f"BMS read error (failure #{self._health.consecutive_failures}): {e}"
                )

                # Determine target state
                if self._health.consecutive_failures >= self.DEGRADED_THRESHOLD:
                    self._transition_state(ModbusConnectionState.DEGRADED)
                    continue  # Skip refresh_interval, go to DEGRADED branch
                elif self._health.consecutive_failures >= self.UNSTABLE_THRESHOLD:
                    self._transition_state(ModbusConnectionState.UNSTABLE)

                # Exponential backoff reconnect (no refresh_interval stacking)
                await self.client.disconnect()
                logger.info(f"Modbus reconnecting in {self._reconnect_delay:.1f}s")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60.0)
                try:
                    if await self.client.connect():
                        self._health.total_reconnects += 1
                except Exception as conn_err:
                    logger.error(f"Modbus reconnect failed: {conn_err}")
                continue  # Skip refresh_interval sleep after reconnect attempt

            except Exception as e:
                logger.error(f"Unexpected error in collection loop: {e}")

            await asyncio.sleep(self.refresh_interval)

    def _notify_data_callbacks(self, snapshot: BMSSnapshot) -> None:
        """Notify all data callbacks with new snapshot."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.ensure_future(callback(snapshot))
                else:
                    callback(snapshot)
            except Exception as e:
                logger.error(f"Callback error: {e}")
