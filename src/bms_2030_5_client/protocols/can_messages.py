"""
CAN 2.0B Message Definitions for BMS Communication.

Reference: BMS to EMS communication protocol V1.7

CAN Configuration:
- Standard: CAN 2.0B
- Baud Rate: 500K
- Data Length: 8 bytes
- ID Format: 0x 0 0 0 X X X X X
  - Example: 0x000F0101 = 主機讀取 Rack:01 Address:01
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Final, List, Tuple


# =============================================================================
# CAN Configuration
# =============================================================================

class CAN_CONFIG:
    """CAN bus communication configuration."""
    
    BAUD_RATE: Final[int] = 500000           # 500K bps
    DATA_LENGTH: Final[int] = 8              # 8 bytes per frame
    
    # ID Format masks
    ID_COMMAND_MASK: Final[int] = 0x00F00000 # Command type mask
    ID_RACK_MASK: Final[int] = 0x0000FF00    # Rack number mask
    ID_ADDR_MASK: Final[int] = 0x000000FF    # Address mask
    
    # Command type prefixes
    CMD_READ: Final[int] = 0x000F0000        # 主機讀取指令 (0xF)
    CMD_RESPONSE: Final[int] = 0x000A0000    # 從機回覆 (0xA)
    CMD_WRITE: Final[int] = 0x00010000       # 主機寫入指令 (0x1)
    CMD_WRITE_ACK: Final[int] = 0x00020000   # 從機寫入確認 (0x2)
    
    @staticmethod
    def build_can_id(command: int, rack: int, address: int) -> int:
        """
        Build CAN ID from components.
        
        Args:
            command: Command prefix (e.g., CMD_READ)
            rack: Rack number (1-24)
            address: Address within rack
            
        Returns:
            Complete CAN ID
        """
        return command | (rack << 8) | address
    
    @staticmethod
    def parse_can_id(can_id: int) -> Tuple[int, int, int]:
        """
        Parse CAN ID into components.
        
        Args:
            can_id: Complete CAN ID
            
        Returns:
            Tuple of (command, rack, address)
        """
        command = can_id & CAN_CONFIG.ID_COMMAND_MASK
        rack = (can_id & CAN_CONFIG.ID_RACK_MASK) >> 8
        address = can_id & CAN_CONFIG.ID_ADDR_MASK
        return (command, rack, address)


# =============================================================================
# CAN Read Commands (主機讀取指令)
# =============================================================================

class CAN_READ_COMMANDS:
    """
    CAN Read Commands sent by master to request data.
    
    Format: 0x0F0XXX where XX is rack number, X is command
    All commands send 8 bytes with first byte = 0x01
    """
    
    # System Information Commands
    SYSTEM_INFO: Final[int] = 0x0F0101       # 系統總資訊讀取 -> Returns 0xA0101, 0xA0102, 0xA0103
    
    # Cell Voltage Commands (each returns 36 frames)
    CELL_VOLTAGE_M1_9: Final[int] = 0x0F0102  # 電芯電壓 Module 1~9 (Cell 1-144)
    CELL_VOLTAGE_M10_18: Final[int] = 0x0F0103 # 電芯電壓 Module 10~18 (Cell 145-288)
    CELL_VOLTAGE_M19_26: Final[int] = 0x0F0104 # 電芯電壓 Module 19~26 (Cell 289-416)
    
    # Temperature Commands
    CELL_TEMP: Final[int] = 0x0F0105         # 電芯溫度讀取 (Module 1~26)
    
    # Balance Status Commands
    BALANCE_M1_18: Final[int] = 0x0F0180     # 平衡狀態 Module 1~18 (Cell 1-288)
    BALANCE_M19_26: Final[int] = 0x0F0181    # 平衡狀態 Module 19~26 (Cell 289-416)
    
    @staticmethod
    def get_request_payload() -> bytes:
        """Get standard request payload (8 bytes starting with 0x01)."""
        return bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    
    @staticmethod
    def for_rack(base_command: int, rack: int) -> int:
        """
        Get command ID for a specific rack.
        
        Args:
            base_command: Base command (e.g., SYSTEM_INFO)
            rack: Rack number (1-24)
            
        Returns:
            Command ID with rack number
        """
        rack_offset = (rack - 1) << 8
        return (base_command & 0x0F0000FF) | rack_offset | 0x0100


# =============================================================================
# CAN Response IDs (從機回覆)
# =============================================================================

class CAN_RESPONSE_IDS:
    """
    CAN Response IDs returned by slave devices.
    
    Format: 0x0A0XXX where XX is rack number, X is data type
    """
    
    # System Info Responses (for SYSTEM_INFO command)
    SYSTEM_INFO_1: Final[int] = 0x0A0101     # 總電壓, 總電流, SOC, 電芯最高電壓
    SYSTEM_INFO_2: Final[int] = 0x0A0102     # 電芯最低電壓, 最高/最低溫度, 異常狀態
    SYSTEM_INFO_3: Final[int] = 0x0A0103     # 最高/最低電壓位置, 最高/最低溫度位置
    SYSTEM_INFO_4: Final[int] = 0x0A0179     # 平衡統計時間, DC, FCC, RM
    
    # Cell Voltage Responses (0x0A0104 - 0x0A0177)
    # Module 1-9: 0x0A0104 - 0x0A0127 (Cell 1-144)
    CELL_VOLTAGE_START_M1: Final[int] = 0x0A0104
    CELL_VOLTAGE_END_M9: Final[int] = 0x0A0127
    
    # Module 10-18: 0x0A0128 - 0x0A0149 (Cell 145-288)
    CELL_VOLTAGE_START_M10: Final[int] = 0x0A0128
    CELL_VOLTAGE_END_M18: Final[int] = 0x0A0149
    
    # Module 19-26: 0x0A014A - 0x0A0161 (Cell 289-416)
    CELL_VOLTAGE_START_M19: Final[int] = 0x0A014A
    CELL_VOLTAGE_END_M26: Final[int] = 0x0A0161
    
    # Temperature Responses
    CELL_TEMP_START: Final[int] = 0x0A0162
    CELL_TEMP_END: Final[int] = 0x0A0178
    
    # Balance Status Responses
    BALANCE_START_M1: Final[int] = 0x0A0180
    BALANCE_END_M26: Final[int] = 0x0A019D

    @staticmethod
    def for_rack(base_response: int, rack: int) -> int:
        """
        Get response ID for a specific rack.
        
        Args:
            base_response: Base response ID
            rack: Rack number (1-24)
            
        Returns:
            Response ID with rack number
        """
        rack_offset = (rack - 1) << 8
        return (base_response & 0x0A0000FF) | rack_offset | 0x0100


# =============================================================================
# CAN Control/Write Commands (主機寫入指令)
# =============================================================================

class CAN_CONTROL_COMMANDS:
    """
    CAN Control Commands for writing/controlling BMS.
    
    Format: 0x010XXX where XX is rack number, X is control type
    """
    
    RELAY_CONTROL: Final[int] = 0x010101     # 繼電器控制 (Data: 0x00=關, 0x01=開)
    PF_RESET: Final[int] = 0x010102          # PF復歸 (Data: 0x01=復歸)
    FAN_CONTROL: Final[int] = 0x010103       # 風扇控制 (Data: 0x00=關, 0x01=開)
    
    @staticmethod
    def for_rack(base_command: int, rack: int) -> int:
        """Get control command ID for a specific rack."""
        rack_offset = (rack - 1) << 8
        return (base_command & 0x010000FF) | rack_offset | 0x0100


class CAN_WRITE_COMMANDS:
    """
    CAN Write Commands for setting BMS parameters.
    
    Format: 0x010XXX where XX is rack number, X is parameter type
    """
    
    # Capacity Settings
    SET_RM: Final[int] = 0x010104            # 設定殘留電量 (0.01AH)
    SET_FCC: Final[int] = 0x010105           # 設定滿充電量 (0.01AH)
    SET_DC: Final[int] = 0x010106            # 設定設計容量 (0.01AH)
    
    # Balance Settings
    SET_BALANCE_FUNCTION: Final[int] = 0x010120   # 設定平衡功能
    SET_CHG_BALANCE_V: Final[int] = 0x010121      # 設定充電平衡電壓
    SET_CHG_BALANCE_DV: Final[int] = 0x010122     # 設定充電平衡壓差
    SET_DSC_BALANCE_V: Final[int] = 0x010123      # 設定放電平衡電壓
    SET_DSC_BALANCE_DV: Final[int] = 0x010124     # 設定放電平衡壓差
    SET_IDLE_BALANCE_V: Final[int] = 0x010125     # 設定靜止平衡電壓
    SET_IDLE_BALANCE_DV: Final[int] = 0x010126    # 設定靜止平衡壓差


# =============================================================================
# Data Structures for CAN Messages
# =============================================================================

@dataclass
class CANSystemInfo:
    """
    Parsed system info from CAN responses.
    
    Combines data from SYSTEM_INFO_1, SYSTEM_INFO_2, SYSTEM_INFO_3, SYSTEM_INFO_4
    """
    # From SYSTEM_INFO_1 (0xA0101)
    total_voltage: float         # V (raw * 0.1)
    total_current: float         # A (raw * 0.1, with -1600A offset)
    soc: float                   # % (raw * 0.1)
    cell_max_voltage: float      # V (raw * 0.001)
    
    # From SYSTEM_INFO_2 (0xA0102)
    cell_min_voltage: float      # V (raw * 0.001)
    cell_max_temp: float         # °C (raw - 40)
    cell_min_temp: float         # °C (raw - 40)
    error_status: int            # Bitfield
    
    # From SYSTEM_INFO_3 (0xA0103)
    max_voltage_pos: int
    min_voltage_pos: int
    max_temp_pos: int
    min_temp_pos: int
    
    # From SYSTEM_INFO_4 (0xA0179)
    balance_time: int            # Minutes
    dc: float                    # AH (raw * 0.01)
    fcc: float                   # AH (raw * 0.01)
    rm: float                    # AH (raw * 0.01)


@dataclass
class CANCellVoltageFrame:
    """Single CAN frame containing 4 cell voltages."""
    can_id: int
    cell_1_voltage: float        # V
    cell_2_voltage: float        # V
    cell_3_voltage: float        # V
    cell_4_voltage: float        # V
    
    @classmethod
    def from_raw(cls, can_id: int, data: bytes) -> "CANCellVoltageFrame":
        """Parse raw CAN data into cell voltages."""
        if len(data) != 8:
            raise ValueError(f"Expected 8 bytes, got {len(data)}")
        
        # Each cell voltage is 2 bytes, little-endian, 0.001V scale
        v1 = int.from_bytes(data[0:2], 'little') * 0.001
        v2 = int.from_bytes(data[2:4], 'little') * 0.001
        v3 = int.from_bytes(data[4:6], 'little') * 0.001
        v4 = int.from_bytes(data[6:8], 'little') * 0.001
        
        return cls(can_id=can_id, cell_1_voltage=v1, cell_2_voltage=v2,
                   cell_3_voltage=v3, cell_4_voltage=v4)


# =============================================================================
# Helper Functions
# =============================================================================

def parse_system_info_1(data: bytes) -> dict:
    """
    Parse SYSTEM_INFO_1 (0xA0101) response.
    
    Format:
    - Bytes 0-1: 總電壓 (U16, 0.1V)
    - Bytes 2-3: 總電流 (S16, 0.1A, offset -1600A)
    - Bytes 4-5: SOC (U16, 0.1%)
    - Bytes 6-7: 電芯最高電壓 (U16, 0.001V)
    """
    if len(data) != 8:
        raise ValueError(f"Expected 8 bytes, got {len(data)}")
    
    total_voltage = int.from_bytes(data[0:2], 'little') * 0.1
    raw_current = int.from_bytes(data[2:4], 'little', signed=True)
    total_current = (raw_current - 16000) * 0.1
    soc = int.from_bytes(data[4:6], 'little') * 0.1
    cell_max_v = int.from_bytes(data[6:8], 'little') * 0.001
    
    return {
        'total_voltage': total_voltage,
        'total_current': total_current,
        'soc': soc,
        'cell_max_voltage': cell_max_v
    }


def parse_system_info_2(data: bytes) -> dict:
    """
    Parse SYSTEM_INFO_2 (0xA0102) response.
    
    Format:
    - Bytes 0-1: 電芯最低電壓 (U16, 0.001V)
    - Bytes 2-3: 電芯最高溫度 (S16, 1°C, offset -40°C)
    - Bytes 4-5: 電芯最低溫度 (S16, 1°C, offset -40°C)
    - Bytes 6-7: 異常訊息及狀態 (U16, bitfield)
    """
    if len(data) != 8:
        raise ValueError(f"Expected 8 bytes, got {len(data)}")
    
    cell_min_v = int.from_bytes(data[0:2], 'little') * 0.001
    cell_max_t = int.from_bytes(data[2:4], 'little', signed=True) - 40
    cell_min_t = int.from_bytes(data[4:6], 'little', signed=True) - 40
    error_status = int.from_bytes(data[6:8], 'little')
    
    return {
        'cell_min_voltage': cell_min_v,
        'cell_max_temp': cell_max_t,
        'cell_min_temp': cell_min_t,
        'error_status': error_status
    }


def parse_system_info_3(data: bytes) -> dict:
    """
    Parse SYSTEM_INFO_3 (0xA0103) response.
    
    Format:
    - Bytes 0-1: 最高電壓位置 (U16)
    - Bytes 2-3: 最低電壓位置 (U16)
    - Bytes 4-5: 最高溫度位置 (U16)
    - Bytes 6-7: 最低溫度位置 (U16)
    """
    if len(data) != 8:
        raise ValueError(f"Expected 8 bytes, got {len(data)}")
    
    return {
        'max_voltage_pos': int.from_bytes(data[0:2], 'little'),
        'min_voltage_pos': int.from_bytes(data[2:4], 'little'),
        'max_temp_pos': int.from_bytes(data[4:6], 'little'),
        'min_temp_pos': int.from_bytes(data[6:8], 'little')
    }


def parse_system_info_4(data: bytes) -> dict:
    """
    Parse SYSTEM_INFO_4 (0xA0179) response.
    
    Format:
    - Bytes 0-1: 平衡統計時間 (U16, Min)
    - Bytes 2-3: DC 設計容量 (U16, 0.01AH)
    - Bytes 4-5: FCC 滿充電量 (U16, 0.01AH)
    - Bytes 6-7: RM 殘留電量 (U16, 0.01AH)
    """
    if len(data) != 8:
        raise ValueError(f"Expected 8 bytes, got {len(data)}")
    
    return {
        'balance_time': int.from_bytes(data[0:2], 'little'),
        'dc': int.from_bytes(data[2:4], 'little') * 0.01,
        'fcc': int.from_bytes(data[4:6], 'little') * 0.01,
        'rm': int.from_bytes(data[6:8], 'little') * 0.01
    }


def build_control_payload(value: int) -> bytes:
    """
    Build control command payload.
    
    Args:
        value: Control value (e.g., 0x00 for off, 0x01 for on)
        
    Returns:
        8-byte payload
    """
    payload = bytearray(8)
    payload[0] = value & 0xFF
    return bytes(payload)


def build_write_payload(value: int) -> bytes:
    """
    Build write command payload for 16-bit value.
    
    Args:
        value: 16-bit value to write
        
    Returns:
        8-byte payload with value in bytes 0-1 (little-endian)
    """
    payload = bytearray(8)
    payload[0:2] = value.to_bytes(2, 'little')
    return bytes(payload)
