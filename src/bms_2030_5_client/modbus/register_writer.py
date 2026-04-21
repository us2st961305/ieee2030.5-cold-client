"""
Modbus Register Writer for Polling Worker.

Provides a simple interface to write values to Modbus registers
from polling results. Supports different data types and scaling.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from bms_2030_5_client.runtime_config import ModbusWriteConfig, ModbusDataType

logger = logging.getLogger(__name__)


class ModbusWriterError(Exception):
    """Modbus writer error."""
    pass


@dataclass
class WriteResult:
    """Result of a Modbus write operation."""
    success: bool
    address: int
    value: Union[int, float]
    raw_values: list[int]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None
    latency_ms: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "address": self.address,
            "value": self.value,
            "raw_values": self.raw_values,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "latency_ms": self.latency_ms,
        }


class ModbusRegisterWriter:
    """
    Modbus register writer for polling results.
    
    Handles writing polled values to Modbus registers with
    proper data type conversion and scaling.
    
    Usage:
        writer = ModbusRegisterWriter(host="192.168.1.100", port=502)
        await writer.connect()
        
        result = await writer.write(
            address=4100,
            value=50.5,
            datatype="int16",
            scale=0.1,
        )
        
        await writer.close()
    """
    
    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 5.0,
        simulation_mode: bool = True,
    ):
        """
        Initialize Modbus writer.
        
        Args:
            host: Modbus server host
            port: Modbus server port
            unit_id: Modbus unit/slave ID
            timeout: Connection timeout
            simulation_mode: If True, don't actually write to Modbus
        """
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.simulation_mode = simulation_mode
        
        self._client: Optional[AsyncModbusTcpClient] = None
        self._connected = False
        self._lock = asyncio.Lock()
    
    @property
    def connected(self) -> bool:
        """Check if connected."""
        return self._connected and self._client is not None
    
    async def connect(self) -> bool:
        """
        Connect to Modbus server.
        
        Returns:
            True if connected successfully
        """
        if self.simulation_mode:
            logger.info(f"[SIMULATION] Modbus writer ready (would connect to {self.host}:{self.port})")
            self._connected = True
            return True
        
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
                    logger.info(f"Connected to Modbus server at {self.host}:{self.port}")
                    return True
                else:
                    logger.error(f"Failed to connect to Modbus server at {self.host}:{self.port}")
                    return False
                    
            except Exception as e:
                logger.error(f"Modbus connection error: {e}")
                self._connected = False
                return False
    
    async def close(self) -> None:
        """Close connection."""
        async with self._lock:
            if self._client:
                self._client.close()
                self._client = None
            self._connected = False
            logger.info("Modbus writer disconnected")
    
    def _convert_value(
        self,
        value: float,
        datatype: str,
        scale: float = 1.0,
        offset: float = 0.0,
    ) -> list[int]:
        """
        Convert value to Modbus register values.
        
        Args:
            value: Value to convert
            datatype: Data type (int16, uint16, int32, uint32, float32)
            scale: Scale factor (value * scale)
            offset: Offset (value + offset before scaling)
            
        Returns:
            List of 16-bit register values
        """
        # Apply offset and scale
        scaled_value = (value + offset) * scale
        
        if datatype == ModbusDataType.INT16.value:
            int_val = int(scaled_value)
            # Clamp to int16 range
            int_val = max(-32768, min(32767, int_val))
            # Convert to unsigned for register
            if int_val < 0:
                int_val = int_val + 65536
            return [int_val]
        
        elif datatype == ModbusDataType.UINT16.value:
            int_val = int(scaled_value)
            int_val = max(0, min(65535, int_val))
            return [int_val]
        
        elif datatype == ModbusDataType.INT32.value:
            int_val = int(scaled_value)
            int_val = max(-2147483648, min(2147483647, int_val))
            # Convert to unsigned
            if int_val < 0:
                int_val = int_val + 4294967296
            # Split into high/low words (big-endian)
            high = (int_val >> 16) & 0xFFFF
            low = int_val & 0xFFFF
            return [high, low]
        
        elif datatype == ModbusDataType.UINT32.value:
            int_val = int(scaled_value)
            int_val = max(0, min(4294967295, int_val))
            high = (int_val >> 16) & 0xFFFF
            low = int_val & 0xFFFF
            return [high, low]
        
        elif datatype == ModbusDataType.FLOAT32.value:
            # Pack as IEEE 754 float
            packed = struct.pack('>f', float(scaled_value))
            high = struct.unpack('>H', packed[0:2])[0]
            low = struct.unpack('>H', packed[2:4])[0]
            return [high, low]
        
        else:
            # Default to int16
            int_val = int(scaled_value)
            int_val = max(-32768, min(32767, int_val))
            if int_val < 0:
                int_val = int_val + 65536
            return [int_val]
    
    async def write(
        self,
        address: int,
        value: float,
        datatype: str = "int16",
        scale: float = 1.0,
        offset: float = 0.0,
    ) -> WriteResult:
        """
        Write value to Modbus register.
        
        Args:
            address: Register address
            value: Value to write
            datatype: Data type for conversion
            scale: Scale factor
            offset: Offset value
            
        Returns:
            WriteResult with operation status
        """
        import time
        start_time = time.perf_counter()
        
        # Convert value to register values
        raw_values = self._convert_value(value, datatype, scale, offset)
        
        # Simulation mode
        if self.simulation_mode:
            latency = (time.perf_counter() - start_time) * 1000
            logger.debug(
                f"[SIMULATION] Write to {address}: value={value}, "
                f"raw={raw_values}, type={datatype}"
            )
            return WriteResult(
                success=True,
                address=address-1,
                value=value,
                raw_values=raw_values,
                latency_ms=latency,
            )
        
        # Ensure connected
        if not self._connected:
            await self.connect()
        
        if not self._connected or self._client is None:
            return WriteResult(
                success=False,
                address=address-1,
                value=value,
                raw_values=raw_values,
                error="Not connected to Modbus server",
            )
        
        try:
            async with self._lock:
                if len(raw_values) == 1:
                    # Single register write
                    result = await self._client.write_register(
                        address=address-1,
                        value=raw_values[0],
                        device_id=self.unit_id,
                    )
                else:
                    # Multiple register write
                    result = await self._client.write_registers(
                        address=address-1,
                        values=raw_values,
                        device_id=self.unit_id,
                    )
                
                latency = (time.perf_counter() - start_time) * 1000
                
                if result.isError():
                    return WriteResult(
                        success=False,
                        address=address-1,
                        value=value,
                        raw_values=raw_values,
                        error=str(result),
                        latency_ms=latency,
                    )
                
                logger.debug(
                    f"Modbus write to {address}: value={value}, "
                    f"raw={raw_values} ({latency:.1f}ms)"
                )
                
                return WriteResult(
                    success=True,
                    address=address-1,
                    value=value,
                    raw_values=raw_values,
                    latency_ms=latency,
                )
                
        except ModbusException as e:
            latency = (time.perf_counter() - start_time) * 1000
            logger.error(f"Modbus write error at {address}: {e}")
            return WriteResult(
                success=False,
                address=address-1,
                value=value,
                raw_values=raw_values,
                error=str(e),
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000
            logger.error(f"Unexpected error writing to {address}: {e}")
            return WriteResult(
                success=False,
                address=address-1,
                value=value,
                raw_values=raw_values,
                error=str(e),
                latency_ms=latency,
            )
    
    async def write_from_config(
        self,
        config: ModbusWriteConfig,
        value: float,
    ) -> WriteResult:
        """
        Write value using ModbusWriteConfig from poll target.
        
        Args:
            config: Modbus write configuration
            value: Value to write
            
        Returns:
            WriteResult
        """
        return await self.write(
            address=config.address,
            value=value,
            datatype=config.datatype,
            scale=config.scale,
            offset=config.offset,
        )
