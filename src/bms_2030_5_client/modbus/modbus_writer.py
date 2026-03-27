"""
Modbus Writer - 最小化寫入模組.

提供簡單的 Modbus 寄存器寫入功能，支援多種資料類型。

支援的資料類型:
- U16: 無符號 16-bit 整數 (1 register)
- S16: 有符號 16-bit 整數 (1 register)
- U32: 無符號 32-bit 整數 (2 registers, big-endian)
- S32: 有符號 32-bit 整數 (2 registers, big-endian)
- FLOAT32: 32-bit 浮點數 (2 registers, big-endian)

用法:
    from bms_2030_5_client.modbus import ModbusWriter, DataType

    writer = ModbusWriter(host="192.168.1.100", port=502)
    
    # 寫入單一寄存器
    result = writer.write_register(
        address=4100,
        value=500,
        unit_id=1,
        datatype=DataType.U16,
        scale=0.1,  # 實際寫入值 = value / scale = 5000
    )
    
    if not result.success:
        print(f"Error: {result.error}")
    
    writer.close()
"""

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Union

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse

logger = logging.getLogger(__name__)


# ============================================
# Data Types
# ============================================

class DataType(str, Enum):
    """Supported Modbus data types."""
    U16 = "U16"       # Unsigned 16-bit integer (1 register)
    S16 = "S16"       # Signed 16-bit integer (1 register)
    U32 = "U32"       # Unsigned 32-bit integer (2 registers)
    S32 = "S32"       # Signed 32-bit integer (2 registers)
    FLOAT32 = "FLOAT32"  # 32-bit float (2 registers)
    
    @classmethod
    def from_string(cls, value: str) -> "DataType":
        """Convert string to DataType, case-insensitive."""
        upper = value.upper().replace("-", "").replace("_", "")
        mapping = {
            "U16": cls.U16,
            "UINT16": cls.U16,
            "S16": cls.S16,
            "INT16": cls.S16,
            "U32": cls.U32,
            "UINT32": cls.U32,
            "S32": cls.S32,
            "INT32": cls.S32,
            "FLOAT32": cls.FLOAT32,
            "FLOAT": cls.FLOAT32,
            "F32": cls.FLOAT32,
        }
        if upper in mapping:
            return mapping[upper]
        raise ValueError(f"Unknown datatype: {value}")


# ============================================
# Write Result
# ============================================

@dataclass
class WriteResult:
    """Result of a Modbus write operation."""
    success: bool
    address: int
    value: Union[int, float]
    raw_registers: List[int]
    unit_id: int
    datatype: DataType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float = 0.0
    error: Optional[str] = None
    
    def __str__(self) -> str:
        if self.success:
            return (
                f"WriteResult(OK, addr={self.address}, "
                f"value={self.value}, regs={self.raw_registers}, "
                f"{self.latency_ms:.1f}ms)"
            )
        return f"WriteResult(FAIL, addr={self.address}, error={self.error})"


# ============================================
# Modbus Writer
# ============================================

class ModbusWriter:
    """
    Modbus 寫入器.
    
    提供簡單的同步介面來寫入 Modbus 寄存器。
    支援 U16/S16/U32/S32/FLOAT32 資料類型。
    
    Attributes:
        host: Modbus 伺服器 IP
        port: Modbus 埠號 (預設 502)
        timeout: 連線逾時秒數
        simulation_mode: 模擬模式 (不實際寫入)
    """
    
    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 5.0,
        simulation_mode: bool = True,
    ):
        """
        初始化 Modbus Writer.
        
        Args:
            host: Modbus 伺服器 IP 位址
            port: Modbus TCP 埠號
            timeout: 連線/操作逾時秒數
            simulation_mode: 若為 True，只記錄但不實際寫入
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.simulation_mode = simulation_mode
        
        self._client: Optional[ModbusTcpClient] = None
        self._connected: bool = False
    
    # ----------------------------------------
    # Connection Management
    # ----------------------------------------
    
    def connect(self) -> bool:
        """
        連接到 Modbus 伺服器.
        
        Returns:
            True if connected successfully
        """
        if self.simulation_mode:
            logger.info(f"[SIMULATION] ModbusWriter: 模擬連接到 {self.host}:{self.port}")
            self._connected = True
            return True
        
        try:
            self._client = ModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=self.timeout,
            )
            self._connected = self._client.connect()
            
            if self._connected:
                logger.info(f"ModbusWriter: 已連接到 {self.host}:{self.port}")
            else:
                logger.error(f"ModbusWriter: 無法連接到 {self.host}:{self.port}")
            
            return self._connected
            
        except Exception as e:
            logger.error(f"ModbusWriter: 連接失敗 - {e}")
            self._connected = False
            return False
    
    def close(self) -> None:
        """關閉 Modbus 連接."""
        if self._client:
            try:
                self._client.close()
                logger.info("ModbusWriter: 連接已關閉")
            except Exception as e:
                logger.warning(f"ModbusWriter: 關閉連接時發生錯誤 - {e}")
            finally:
                self._client = None
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """檢查是否已連接."""
        return self._connected
    
    # ----------------------------------------
    # Write Operations
    # ----------------------------------------
    
    def write_register(
        self,
        address: int,
        value: Union[int, float],
        unit_id: int = 1,
        datatype: Union[DataType, str] = DataType.U16,
        scale: float = 1.0,
        offset: float = 0.0,
    ) -> WriteResult:
        """
        寫入值到 Modbus 寄存器.
        
        Args:
            address: 寄存器起始位址
            value: 要寫入的值 (原始工程值)
            unit_id: Modbus Unit ID (slave address)
            datatype: 資料類型 (U16/S16/U32/S32/FLOAT32)
            scale: 縮放係數 (寫入值 = (value - offset) / scale)
            offset: 偏移量
            
        Returns:
            WriteResult 包含寫入結果
            
        Example:
            # 寫入 50.0 到 U16 寄存器，scale=0.1 -> 實際寫入 500
            writer.write_register(4100, 50.0, datatype=DataType.U16, scale=0.1)
        """
        start_time = time.time()
        
        # 解析 datatype
        if isinstance(datatype, str):
            try:
                datatype = DataType.from_string(datatype)
            except ValueError as e:
                return WriteResult(
                    success=False,
                    address=address,
                    value=value,
                    raw_registers=[],
                    unit_id=unit_id,
                    datatype=DataType.U16,
                    error=str(e),
                )
        
        # 應用 scale 和 offset
        scaled_value = (value - offset) / scale if scale != 0 else value
        
        # 轉換為寄存器值
        try:
            raw_registers = self._convert_to_registers(scaled_value, datatype)
        except Exception as e:
            error_msg = f"值轉換失敗: {e}"
            logger.error(f"ModbusWriter: {error_msg}")
            return WriteResult(
                success=False,
                address=address,
                value=value,
                raw_registers=[],
                unit_id=unit_id,
                datatype=datatype,
                error=error_msg,
            )
        
        # 模擬模式
        if self.simulation_mode:
            latency = (time.time() - start_time) * 1000
            logger.info(
                f"[SIMULATION] ModbusWriter: write_register("
                f"addr={address}, value={value}, scaled={scaled_value}, "
                f"regs={raw_registers}, unit={unit_id}, type={datatype.value})"
            )
            return WriteResult(
                success=True,
                address=address,
                value=value,
                raw_registers=raw_registers,
                unit_id=unit_id,
                datatype=datatype,
                latency_ms=latency,
            )
        
        # 實際寫入
        return self._do_write(
            address=address,
            value=value,
            raw_registers=raw_registers,
            unit_id=unit_id,
            datatype=datatype,
            start_time=start_time,
        )
    
    def _do_write(
        self,
        address: int,
        value: Union[int, float],
        raw_registers: List[int],
        unit_id: int,
        datatype: DataType,
        start_time: float,
    ) -> WriteResult:
        """執行實際的 Modbus 寫入."""
        # 檢查連接
        if not self._connected or self._client is None:
            error_msg = "Modbus 未連接"
            logger.error(f"ModbusWriter: {error_msg}")
            return WriteResult(
                success=False,
                address=address,
                value=value,
                raw_registers=raw_registers,
                unit_id=unit_id,
                datatype=datatype,
                error=error_msg,
            )
        
        try:
            # 根據寄存器數量選擇寫入方法
            if len(raw_registers) == 1:
                # 單一寄存器 - 使用 write_register (FC 0x06)
                response = self._client.write_register(
                    address=address,
                    value=raw_registers[0],
                    device_id=unit_id,
                )
            else:
                # 多個寄存器 - 使用 write_registers (FC 0x10)
                response = self._client.write_registers(
                    address=address,
                    values=raw_registers,
                    device_id=unit_id,
                )
            
            latency = (time.time() - start_time) * 1000
            
            # 檢查回應
            if response is None:
                error_msg = "Modbus 無回應"
                logger.error(f"ModbusWriter: {error_msg} (addr={address})")
                return WriteResult(
                    success=False,
                    address=address,
                    value=value,
                    raw_registers=raw_registers,
                    unit_id=unit_id,
                    datatype=datatype,
                    latency_ms=latency,
                    error=error_msg,
                )
            
            if isinstance(response, ExceptionResponse):
                error_msg = f"Modbus 異常: {response}"
                logger.error(f"ModbusWriter: {error_msg} (addr={address})")
                return WriteResult(
                    success=False,
                    address=address,
                    value=value,
                    raw_registers=raw_registers,
                    unit_id=unit_id,
                    datatype=datatype,
                    latency_ms=latency,
                    error=error_msg,
                )
            
            if response.isError():
                error_msg = f"Modbus 錯誤: {response}"
                logger.error(f"ModbusWriter: {error_msg} (addr={address})")
                return WriteResult(
                    success=False,
                    address=address,
                    value=value,
                    raw_registers=raw_registers,
                    unit_id=unit_id,
                    datatype=datatype,
                    latency_ms=latency,
                    error=error_msg,
                )
            
            # 成功
            logger.info(
                f"ModbusWriter: 寫入成功 addr={address}, "
                f"regs={raw_registers}, unit={unit_id}, {latency:.1f}ms"
            )
            return WriteResult(
                success=True,
                address=address,
                value=value,
                raw_registers=raw_registers,
                unit_id=unit_id,
                datatype=datatype,
                latency_ms=latency,
            )
            
        except ModbusException as e:
            latency = (time.time() - start_time) * 1000
            error_msg = f"Modbus 通訊錯誤: {e}"
            logger.error(f"ModbusWriter: {error_msg} (addr={address})")
            return WriteResult(
                success=False,
                address=address,
                value=value,
                raw_registers=raw_registers,
                unit_id=unit_id,
                datatype=datatype,
                latency_ms=latency,
                error=error_msg,
            )
            
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            error_msg = f"未預期錯誤: {e}"
            logger.error(f"ModbusWriter: {error_msg} (addr={address})")
            return WriteResult(
                success=False,
                address=address,
                value=value,
                raw_registers=raw_registers,
                unit_id=unit_id,
                datatype=datatype,
                latency_ms=latency,
                error=error_msg,
            )
    
    # ----------------------------------------
    # Data Conversion
    # ----------------------------------------
    
    def _convert_to_registers(
        self,
        value: Union[int, float],
        datatype: DataType,
    ) -> List[int]:
        """
        將值轉換為 Modbus 寄存器.
        
        Args:
            value: 已縮放的值
            datatype: 資料類型
            
        Returns:
            寄存器值列表 (1 或 2 個 16-bit 值)
        """
        if datatype == DataType.U16:
            # Unsigned 16-bit: 0 ~ 65535
            int_val = int(round(value))
            int_val = max(0, min(65535, int_val))
            return [int_val]
        
        elif datatype == DataType.S16:
            # Signed 16-bit: -32768 ~ 32767
            int_val = int(round(value))
            int_val = max(-32768, min(32767, int_val))
            # 轉換為無符號表示
            if int_val < 0:
                int_val = int_val + 65536
            return [int_val]
        
        elif datatype == DataType.U32:
            # Unsigned 32-bit: 0 ~ 4294967295 (Big-endian: high word first)
            int_val = int(round(value))
            int_val = max(0, min(0xFFFFFFFF, int_val))
            high = (int_val >> 16) & 0xFFFF
            low = int_val & 0xFFFF
            return [high, low]
        
        elif datatype == DataType.S32:
            # Signed 32-bit: -2147483648 ~ 2147483647 (Big-endian)
            int_val = int(round(value))
            int_val = max(-2147483648, min(2147483647, int_val))
            # 轉換為無符號表示
            if int_val < 0:
                int_val = int_val + 0x100000000
            high = (int_val >> 16) & 0xFFFF
            low = int_val & 0xFFFF
            return [high, low]
        
        elif datatype == DataType.FLOAT32:
            # IEEE 754 單精度浮點數 (Big-endian)
            packed = struct.pack('>f', float(value))
            high = struct.unpack('>H', packed[0:2])[0]
            low = struct.unpack('>H', packed[2:4])[0]
            return [high, low]
        
        else:
            raise ValueError(f"不支援的資料類型: {datatype}")
    
    # ----------------------------------------
    # Context Manager
    # ----------------------------------------
    
    def __enter__(self) -> "ModbusWriter":
        """Context manager 進入."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager 離開."""
        self.close()


# ============================================
# Helper Functions
# ============================================

def create_writer(
    host: str,
    port: int = 502,
    timeout: float = 5.0,
    simulation_mode: bool = True,
) -> ModbusWriter:
    """
    建立並連接 ModbusWriter.
    
    Args:
        host: Modbus 伺服器 IP
        port: Modbus 埠號
        timeout: 連線逾時
        simulation_mode: 模擬模式
        
    Returns:
        已連接的 ModbusWriter 實例
    """
    writer = ModbusWriter(
        host=host,
        port=port,
        timeout=timeout,
        simulation_mode=simulation_mode,
    )
    writer.connect()
    return writer
