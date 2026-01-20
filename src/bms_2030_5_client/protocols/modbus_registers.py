"""
Modbus Register Definitions for BMS Communication.

Reference Documents:
- BMS to EMS communication protocol V1.7
- CUBE 電池組暫存器通訊表 V1.0.3

RS-485 Modbus RTU Configuration:
- Baud Rate: 9600
- Data Bits: 8
- Parity: None
- Stop Bits: 1
- Function Codes: Read(0x03), Write(0x06)
- Refresh Time: 500ms

CUBE Modbus TCP/IP Configuration:
- Port: 502 (default)
- Unit ID: 1
"""

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Final


# =============================================================================
# RS-485 Modbus RTU Register Definitions (BMS to EMS V1.7)
# =============================================================================

@dataclass(frozen=True)
class RS485RegisterDef:
    """RS-485 register definition with metadata."""
    address: int
    name: str
    name_zh: str
    rw: str  # "R", "W", or "R/W"
    unit: str
    scale: float = 1.0
    offset: float = 0.0
    description: str = ""


class RS485_REGISTERS:
    """
    RS-485 Modbus RTU Register Addresses.
    
    Reference: BMS to EMS communication protocol V1.7
    Rack: 1~24, ID: 1~n
    """
    
    # === Basic System Info (0x0000 - 0x0010) ===
    HEART_BEAT: Final[int] = 0x0000          # R, 0~65535, 0.5S循環加一
    TOTAL_VOLTAGE: Final[int] = 0x0001       # R, 0~60000, 0.1V
    TOTAL_CURRENT: Final[int] = 0x0002       # R, 0~32000, 0.1A, Shift: -1600A (充電為負)
    SOC: Final[int] = 0x0003                 # R, 0~1000, 0.1%
    CELL_MAX_VOLTAGE: Final[int] = 0x0004    # R, 0.001V/Bit
    CELL_MIN_VOLTAGE: Final[int] = 0x0005    # R, 0.001V/Bit
    CELL_MAX_TEMP: Final[int] = 0x0006       # R, 1℃, Shift: -40℃
    CELL_MIN_TEMP: Final[int] = 0x0007       # R, 1℃, Shift: -40℃
    ERROR_STATUS: Final[int] = 0x0008        # R, bitfield (see ErrorStatusBits)
    MAX_VOLTAGE_POS: Final[int] = 0x0009     # R, 0~511, 最高電壓位置
    MIN_VOLTAGE_POS: Final[int] = 0x000A     # R, 0~511, 最低電壓位置
    MAX_TEMP_POS: Final[int] = 0x000B        # R, 0~511, 最高溫度位置
    MIN_TEMP_POS: Final[int] = 0x000C        # R, 0~511, 最低溫度位置
    SOH: Final[int] = 0x000D                 # R, 0~100, 1%
    RELAY_SWITCH: Final[int] = 0x000E        # R/W, 0/1, 繼電器開關 (1=開, 0=關)
    PF_RELEASE: Final[int] = 0x000F          # R/W, 0/1, PF解除保護 (1=解除)
    FAN_SWITCH: Final[int] = 0x0010          # R/W, 0/1, 風扇開關 (1=開, 0=關)
    
    # === Capacity & Calibration (0x0011 - 0x0020) ===
    RM: Final[int] = 0x0011                  # R/W, 0~65535, 0.01AH, 殘留電量
    FCC: Final[int] = 0x0012                 # R/W, 0~65535, 0.01AH, 滿充電量
    BALANCE_STATUS: Final[int] = 0x0013      # R, 0/1, 平衡狀態 (1=開, 0=關)
    CELL_READ_POS: Final[int] = 0x0014       # R/W, 0~500, 指定電芯讀取位置
    CELL_DISPLAY_POS: Final[int] = 0x0015    # R, 0~500, 電芯顯示位址
    CELL_VOLTAGE: Final[int] = 0x0016        # R, 0.001V/Bit, 電芯電壓
    TEMP_READ_POS: Final[int] = 0x0017       # R/W, 0~500, 指定溫度讀取位置
    TEMP_DISPLAY_POS: Final[int] = 0x0018    # R, 0~500, 溫度顯示位址
    TEMPERATURE: Final[int] = 0x0019         # R, Shift: -40℃
    UPDATE_SOC: Final[int] = 0x001A          # R/W, 0/1, 更新SOC (無電流時寫1)
    DC: Final[int] = 0x001B                  # R/W, 0~65535, 0.01AH, 設計容量
    TAPER_CURRENT: Final[int] = 0x001C       # R/W, 0~65535, 1A
    TAPER_CUT_VOL: Final[int] = 0x001D       # R/W, 0~65535, 0.1mV, 滿電校正電壓
    TERMINATE_V: Final[int] = 0x001E         # R/W, 0~65535, 0.1mV, 沒電校正電壓
    DSC_COEF: Final[int] = 0x001F            # R/W, 900~1100, 0.1%, 放電電流係數
    CHG_COEF: Final[int] = 0x0020            # R/W, 900~1100, 0.1%, 充電電流係數
    
    # === Conversion Helpers ===
    @staticmethod
    def convert_voltage(raw: int) -> float:
        """Convert raw voltage value (0.1V scale) to volts."""
        return raw * 0.1
    
    @staticmethod
    def convert_current(raw: int) -> float:
        """Convert raw current value with -1600A offset to amps."""
        return (raw - 16000) * 0.1
    
    @staticmethod
    def convert_soc(raw: int) -> float:
        """Convert raw SOC value (0.1% scale) to percentage."""
        return raw * 0.1
    
    @staticmethod
    def convert_cell_voltage(raw: int) -> float:
        """Convert raw cell voltage (0.001V scale) to volts."""
        return raw * 0.001
    
    @staticmethod
    def convert_temperature(raw: int) -> float:
        """Convert raw temperature with -40°C offset to Celsius."""
        return raw - 40
    
    @staticmethod
    def convert_capacity(raw: int) -> float:
        """Convert raw capacity (0.01AH scale) to AH."""
        return raw * 0.01


class RS485_BALANCE_REGISTERS:
    """
    RS-485 Balance Function Registers (0x0101 - 0x012D).
    
    Reference: BMS to EMS communication protocol V1.7
    """
    
    # === Non-balance Cell List (0x0101 - 0x011E) ===
    # 30 cell positions that should not participate in balancing
    # Value 0xFFFF means empty/unused
    NON_BALANCE_CELL_START: Final[int] = 0x0101
    NON_BALANCE_CELL_END: Final[int] = 0x011E
    NON_BALANCE_CELL_COUNT: Final[int] = 30
    
    NON_BALANCE_TIME: Final[int] = 0x011F    # R/W, 0~65535, Min, EMS下指令
    BALANCE_FUNCTION: Final[int] = 0x0120    # R/W, 0~8, Bit, 執行平衡功能 (see BalanceFunctionBits)
    
    # === Charging Balance Thresholds ===
    CHG_BALANCE_SET_V: Final[int] = 0x0121   # R/W, 0~65535, 0.1mV, 充電平衡Set電壓
    CHG_BALANCE_SET_DV: Final[int] = 0x0122  # R/W, 0~65535, 0.1mV, 充電平衡Set壓差
    
    # === Discharging Balance Thresholds ===
    DSC_BALANCE_SET_V: Final[int] = 0x0123   # R/W, 0~65535, 0.1mV, 放電平衡Set電壓
    DSC_BALANCE_SET_DV: Final[int] = 0x0124  # R/W, 0~65535, 0.1mV, 放電平衡Set壓差
    
    # === Idle Balance Thresholds ===
    IDLE_BALANCE_SET_V: Final[int] = 0x0125  # R/W, 0~65535, 0.1mV, 靜止平衡Set電壓
    IDLE_BALANCE_SET_DV: Final[int] = 0x0126 # R/W, 0~65535, 0.1mV, 靜止平衡Set壓差
    
    EXECUTION_TIME: Final[int] = 0x0127      # R, 0~65535, Min, 執行時間
    
    # === Balance Release Thresholds ===
    CHG_BALANCE_REL_V: Final[int] = 0x0128   # R/W, 0~65535, 0.1mV, 充電平衡Rel電壓
    CHG_BALANCE_REL_DV: Final[int] = 0x0129  # R/W, 0~65535, 0.1mV, 充電平衡Rel壓差
    DSC_BALANCE_REL_V: Final[int] = 0x012A   # R/W, 0~65535, 0.1mV, 放電平衡Rel電壓
    DSC_BALANCE_REL_DV: Final[int] = 0x012B  # R/W, 0~65535, 0.1mV, 放電平衡Rel壓差
    IDLE_BALANCE_REL_V: Final[int] = 0x012C  # R/W, 0~65535, 0.1mV, 靜止平衡Rel電壓
    IDLE_BALANCE_REL_DV: Final[int] = 0x012D # R/W, 0~65535, 0.1mV, 靜止平衡Rel壓差


# =============================================================================
# CUBE Modbus TCP/IP Register Definitions (V1.0.3)
# =============================================================================

# NOTE: CUBE documentation uses 1-based register numbering.
# Actual Modbus protocol addresses are offset by -1.
# Document address 7000 -> Actual address 6999
# Document address 4000 -> Actual address 3999
CUBE_ADDRESS_OFFSET: Final[int] = -1


class CUBE_RACK_REGISTERS:
    """
    CUBE Modbus TCP Rack-Level Registers (7000 series in documentation).
    
    Reference: CUBE 電池組暫存器通訊表 V1.0.3
    
    IMPORTANT: Addresses here are the ACTUAL Modbus addresses to use.
    Documentation addresses need -1 offset for actual communication.
    (Doc 7000 -> Actual 6999)
    
    Each rack has 30 registers, offset by RACK_OFFSET * (rack_number - 1)
    """
    
    # Base addresses (Rack 1) - Actual Modbus addresses (doc address - 1)
    RACK_VOLTAGE: Final[int] = 6999          # RO, U16, 0.1V (Doc: 7000)
    RACK_CURRENT: Final[int] = 7000          # RO, S16, 0.1A (Doc: 7001)
    SOC: Final[int] = 7001                   # RO, U16, 0.1% (Doc: 7002)
    CELL_MAX_V: Final[int] = 7002            # RO, U16, 0.001V (Doc: 7003)
    CELL_MIN_V: Final[int] = 7003            # RO, U16, 0.001V (Doc: 7004)
    CELL_MAX_T: Final[int] = 7004            # RO, S16, 1°C (Doc: 7005)
    CELL_MIN_T: Final[int] = 7005            # RO, S16, 1°C (Doc: 7006)
    TAG_MAX_V: Final[int] = 7006             # RO, U16, enum (Doc: 7007)
    TAG_MIN_V: Final[int] = 7007             # RO, U16, enum (Doc: 7008)
    TAG_MAX_T: Final[int] = 7008             # RO, U16, enum (Doc: 7009)
    TAG_MIN_T: Final[int] = 7009             # RO, U16, enum (Doc: 7010)
    RM: Final[int] = 7010                    # RO, U16, 0.01AH, 殘留電量 (Doc: 7011)
    FCC: Final[int] = 7011                   # RO, U16, 0.01AH, 滿充電量 (Doc: 7012)
    # 7012-7017: Reserved (Doc: 7013-7018)
    LECU_FLAG: Final[int] = 7018             # RO, U16, LECU告警旗標 (Doc: 7019)
    RACK_FLAG: Final[int] = 7019             # RO, U16, Rack告警旗標 (Doc: 7020)
    # 7020: Reserved (Doc: 7021)
    SOH: Final[int] = 7021                   # RO, U16, 1% (Doc: 7022)
    # 7022-7023: Reserved (Doc: 7023-7024)
    RELAY_SW: Final[int] = 7024              # R/W, U16, 繼電器開關 (Doc: 7025)
    PF_RELEASE: Final[int] = 7025            # R/W, U16, 解除永久保護 (Doc: 7026)
    # 7026-7028: Reserved (Doc: 7027-7029)
    
    # Rack offset
    RACK_OFFSET: Final[int] = 30             # 每個 Rack 偏移量
    
    # Base address for first rack (actual Modbus address)
    BASE_ADDRESS: Final[int] = 6999          # Doc: 7000
    
    @classmethod
    def get_rack_address(cls, base_address: int, rack_number: int) -> int:
        """
        Calculate register address for a specific rack.
        
        Args:
            base_address: Base register address (actual Modbus address)
            rack_number: Rack number (1-based)
            
        Returns:
            Actual register address for the specified rack
        """
        return base_address + cls.RACK_OFFSET * (rack_number - 1)
    
    @classmethod
    def doc_to_actual(cls, doc_address: int) -> int:
        """Convert documentation address to actual Modbus address."""
        return doc_address + CUBE_ADDRESS_OFFSET


class CUBE_SYSTEM_REGISTERS:
    """
    CUBE Modbus TCP System-Level Registers (4000 series in documentation).
    
    Reference: CUBE 電池組暫存器通訊表 V1.0.3
    整櫃 / Container 等級系統資訊
    
    IMPORTANT: Addresses here are the ACTUAL Modbus addresses to use.
    Documentation addresses need -1 offset for actual communication.
    (Doc 4000 -> Actual 3999)
    """
    
    # Base address (actual Modbus address)
    BASE_ADDRESS: Final[int] = 3999          # Doc: 4000
    
    # System registers - Actual Modbus addresses (doc address - 1)
    VOL_AVG: Final[int] = 3999               # RO, U16, 0.1V, 平均電壓 (Doc: 4000)
    TOTAL_CURR: Final[int] = 4000            # RO, S16, 0.1A, 總電流 (Doc: 4001)
    TOTAL_POWER: Final[int] = 4001           # RO, S16, 0.1kW, 總功率 (Doc: 4002)
    DELIY_CHG: Final[int] = 4002             # RO, U16, 0.1kWh, 充電累計 (Doc: 4003)
    DELIY_DSC: Final[int] = 4003             # RO, U16, 0.1kWh, 放電累計 (Doc: 4004)
    SOC_AVG: Final[int] = 4004               # RO, U16, 0.1%, 平均SOC (Doc: 4005)
    RM_TOTAL: Final[int] = 4005              # RO, U16, AH, 總殘留電量 (Doc: 4006)
    FCC_TOTAL: Final[int] = 4006             # RO, U16, AH, 總滿充電量 (Doc: 4007)
    ONLINE_NO: Final[int] = 4007             # RO, U16, 在線數量 (Doc: 4008)
    ALLOW_POWER: Final[int] = 4008           # RO, U16, 0.1kW, 允許功率 (Doc: 4009)
    RIGHT_STATE: Final[int] = 4009           # RO, U16, bitfield Rack1~12 (Doc: 4010)
    LEFT_STATE: Final[int] = 4010            # RO, U16, bitfield Rack13~24 (Doc: 4011)
    SYS_STATE: Final[int] = 4011             # RO, U16, 0/1 系統狀態 (Doc: 4012)
    ALL_MAX_V: Final[int] = 4012             # RO, U16, 0.1V, 最高電壓Rack (Doc: 4013)
    ALL_MIN_V: Final[int] = 4013             # RO, U16, 0.1V, 最低電壓Rack (Doc: 4014)
    VOL_DIFF: Final[int] = 4014              # RO, U16, 0.1V, 電壓差 (Doc: 4015)
    ALL_MAX_T: Final[int] = 4015             # RO, S16, 1°C, 最高溫度 (Doc: 4016)
    ALL_MIN_T: Final[int] = 4016             # RO, S16, 1°C, 最低溫度 (Doc: 4017)
    ON_ALL_RELAY: Final[int] = 4017          # R/W, U16, 0/1, 全開繼電器 (Doc: 4018)
    OFF_ALL_RELAY: Final[int] = 4018         # R/W, U16, 0/1, 全關繼電器 (Doc: 4019)
    # 4019-4025: Reserved (Doc: 4020-4026)
    FIRE_ALARM_1: Final[int] = 4026          # RO, U16, 0/1, 火警1 (Doc: 4027)
    FIRE_ALARM_2: Final[int] = 4027          # RO, U16, 0/1, 火警2 (Doc: 4028)
    # 4028-4040: Reserved (Doc: 4029-4041)
    ALLOW_POWER_DSC: Final[int] = 4041       # RO, U16, 0.1kW, 允許放電功率 (Doc: 4042)
    ALLOW_POWER_CHG: Final[int] = 4042       # RO, U16, 0.1kW, 允許充電功率 (Doc: 4043)
    
    # Legacy aliases for backward compatibility
    SYSTEM_VOLTAGE: Final[int] = VOL_AVG
    SYSTEM_CURRENT: Final[int] = TOTAL_CURR
    SYSTEM_SOC: Final[int] = SOC_AVG
    
    @classmethod
    def doc_to_actual(cls, doc_address: int) -> int:
        """Convert documentation address to actual Modbus address."""
        return doc_address + CUBE_ADDRESS_OFFSET


# =============================================================================
# Bit Field Definitions
# =============================================================================

class ErrorStatusBits(IntFlag):
    """
    Error Status Bitfield for RS-485 register 0x0008.
    
    Reference: BMS to EMS communication protocol V1.7
    """
    # Low Byte
    LEVEL2_ALARM = 0x0001       # Bit 0: Level 2 警報
    LEVEL3_ALARM = 0x0002       # Bit 1: Level 3 警報
    PF_PROTECTION = 0x0004     # Bit 2: PF 永久保護
    RELAY_STUCK = 0x0008       # Bit 3: 繼電器沾粘
    VOLTAGE_ALARM = 0x0010     # Bit 4: 電壓警報
    TEMP_ALARM = 0x0020        # Bit 5: 溫度警報
    CURRENT_ALARM = 0x0040     # Bit 6: 電流警報
    COMM_ERROR = 0x0080        # Bit 7: 通訊及量測異常
    
    # High Byte
    RELAY_STATUS = 0x0100      # Bit 8: 繼電器狀態 (1=開, 0=關)
    FAN_STATUS = 0x0200        # Bit 9: 風扇狀態 (1=開, 0=關)
    BALANCE_ERROR = 0x0400     # Bit 10: 平衡異常
    # Bits 11-15: Reserved


class RackFlagBits(IntFlag):
    """
    Rack Flag Bitfield for CUBE register 7020.
    
    Reference: CUBE 電池組暫存器通訊表 V1.0.3
    """
    # Low Byte - 告警狀態
    CELL_OV_ALARM = 0x0001     # Bit 0: 電芯過壓告警
    CELL_UV_ALARM = 0x0002     # Bit 1: 電芯欠壓告警
    CELL_OT_ALARM = 0x0004     # Bit 2: 電芯過溫告警
    CELL_UT_ALARM = 0x0008     # Bit 3: 電芯低溫告警
    CHG_OC_ALARM = 0x0010      # Bit 4: 充電過流告警
    DSC_OC_ALARM = 0x0020      # Bit 5: 放電過流告警
    RACK_OV_ALARM = 0x0040     # Bit 6: Rack過壓告警
    RACK_UV_ALARM = 0x0080     # Bit 7: Rack欠壓告警
    
    # High Byte - 保護狀態
    CELL_OV_PROT = 0x0100      # Bit 8: 電芯過壓保護
    CELL_UV_PROT = 0x0200      # Bit 9: 電芯欠壓保護
    CELL_OT_PROT = 0x0400      # Bit 10: 電芯過溫保護
    CELL_UT_PROT = 0x0800      # Bit 11: 電芯低溫保護
    CHG_OC_PROT = 0x1000       # Bit 12: 充電過流保護
    DSC_OC_PROT = 0x2000       # Bit 13: 放電過流保護
    RELAY_STATUS = 0x4000      # Bit 14: 繼電器狀態
    BALANCE_STATUS = 0x8000    # Bit 15: 平衡狀態


class LECUFlagBits(IntFlag):
    """
    LECU Flag Bitfield for CUBE register 7019.
    
    Reference: CUBE 電池組暫存器通訊表 V1.0.3
    """
    # Low Byte
    COMM_ERROR = 0x0001        # Bit 0: 通訊異常
    HARDWARE_ERROR = 0x0002    # Bit 1: 硬體異常
    AFE_ERROR = 0x0004         # Bit 2: AFE異常
    MEASURE_ERROR = 0x0008     # Bit 3: 量測異常
    BALANCE_ERROR = 0x0010     # Bit 4: 平衡異常
    EEPROM_ERROR = 0x0020      # Bit 5: EEPROM異常
    # Bits 6-15: Reserved


class BalanceFunctionBits(IntFlag):
    """
    Balance Function Bitfield for RS-485 register 0x0120.
    
    Reference: BMS to EMS communication protocol V1.7
    """
    # Low Byte
    CHG_BALANCE = 0x01         # Bit 0: 充電平衡 (0=OFF, 1=ON)
    DSC_BALANCE = 0x02         # Bit 1: 放電平衡 (0=OFF, 1=ON)
    IDLE_BALANCE = 0x04        # Bit 2: 靜止平衡 (0=OFF, 1=ON)
    NON_BALANCE_CMD = 0x08     # Bit 3: 30個指定不平指令 (0=無效, 1=有效)
    # Bits 4-7: Reserved
    # High Byte: Reserved


# =============================================================================
# Modbus Configuration Constants
# =============================================================================

class ModbusConfig:
    """Modbus communication configuration."""
    
    # RS-485 RTU Settings
    RS485_BAUD_RATE: Final[int] = 9600
    RS485_DATA_BITS: Final[int] = 8
    RS485_PARITY: Final[str] = "N"
    RS485_STOP_BITS: Final[int] = 1
    RS485_REFRESH_MS: Final[int] = 500
    
    # Function Codes
    FC_READ_HOLDING: Final[int] = 0x03
    FC_WRITE_SINGLE: Final[int] = 0x06
    FC_WRITE_MULTIPLE: Final[int] = 0x10
    
    # CUBE TCP Settings
    CUBE_TCP_PORT: Final[int] = 502
    CUBE_UNIT_ID: Final[int] = 1
