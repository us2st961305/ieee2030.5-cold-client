"""
Data models for BMS battery rack data.

Based on CUBE 電池組暫存器通訊表 V1.0.3
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import List, Optional


class RackStatus(IntEnum):
    """Rack operational status."""
    OFFLINE = 0
    STANDBY = 1
    CHARGING = 2
    DISCHARGING = 3
    FAULT = 4


class AlarmLevel(IntEnum):
    """Alarm severity level."""
    NONE = 0
    WARNING = 1
    ALARM = 2
    FAULT = 3


@dataclass
class CellInfo:
    """Individual cell information."""
    voltage: float  # V
    temperature: float  # °C
    cell_id: int


@dataclass
class RackData:
    """
    Single rack data from Modbus registers 7000-7029.
    
    Register mapping (offset 30 per rack):
    - 7000: rack_vol (U16, 0.1V)
    - 7001: rack_current (S16, 0.1A)
    - 7002: SOC (U16, 0.1%)
    - 7003: cell_max_v (U16, 0.001V)
    - 7004: cell_min_v (U16, 0.001V)
    - 7005: cell_max_t (S16, 1°C)
    - 7006: cell_min_t (S16, 1°C)
    - 7007: tag_max_v (U16, enum)
    - 7008: tag_min_v (U16, enum)
    - 7009: tag_max_t (U16, enum)
    - 7010: tag_min_t (U16, enum)
    - 7011: RM (U16, 0.01AH)
    - 7012: FCC (U16, 0.01AH)
    - 7013: rack_power (S32, 0.1W) [7013-7014]
    - 7015: cycle_count (U16)
    - 7016: rack_status (U16)
    - 7017: alarm_status (U16)
    - 7018: soh (U16, 0.1%)
    - 7019: max_charge_current (U16, 0.1A)
    - 7020: max_discharge_current (U16, 0.1A)
    - 7021: max_charge_voltage (U16, 0.1V)
    - 7022: min_discharge_voltage (U16, 0.1V)
    """
    rack_id: int
    voltage: float  # V
    current: float  # A (positive=charging, negative=discharging)
    soc: float  # %
    cell_max_voltage: float  # V
    cell_min_voltage: float  # V
    cell_max_temp: float  # °C
    cell_min_temp: float  # °C
    tag_max_v: int  # Cell ID with max voltage
    tag_min_v: int  # Cell ID with min voltage
    tag_max_t: int  # Cell ID with max temperature
    tag_min_t: int  # Cell ID with min temperature
    remaining_capacity: float  # AH
    full_charge_capacity: float  # AH
    power: float = 0.0  # W
    cycle_count: int = 0
    status: RackStatus = RackStatus.OFFLINE
    alarm_status: int = 0
    soh: float = 100.0  # %
    max_charge_current: float = 0.0  # A
    max_discharge_current: float = 0.0  # A
    max_charge_voltage: float = 0.0  # V
    min_discharge_voltage: float = 0.0  # V
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def cell_voltage_diff(self) -> float:
        """Calculate cell voltage difference (imbalance indicator)."""
        return self.cell_max_voltage - self.cell_min_voltage

    @property
    def cell_temp_diff(self) -> float:
        """Calculate cell temperature difference."""
        return self.cell_max_temp - self.cell_min_temp

    @property
    def is_charging(self) -> bool:
        """Check if rack is currently charging."""
        return self.current > 0

    @property
    def is_discharging(self) -> bool:
        """Check if rack is currently discharging."""
        return self.current < 0

    @classmethod
    def from_registers(cls, rack_id: int, registers: List[int]) -> "RackData":
        """
        Create RackData from raw Modbus registers.
        
        Args:
            rack_id: Rack identifier (0-23)
            registers: List of register values (at least 23 values)
        
        Returns:
            RackData instance with parsed values
        """
        if len(registers) < 23:
            raise ValueError(f"Expected at least 23 registers, got {len(registers)}")

        # Parse signed values (S16)
        def to_signed(val: int) -> int:
            return val - 65536 if val > 32767 else val

        # Parse 32-bit value from two registers
        def to_int32(high: int, low: int) -> int:
            val = (high << 16) | low
            return val - 4294967296 if val > 2147483647 else val

        return cls(
            rack_id=rack_id,
            voltage=registers[0] * 0.1,  # 7000: 0.1V
            current=to_signed(registers[1]) * 0.1,  # 7001: 0.1A
            soc=registers[2] * 0.1,  # 7002: 0.1%
            cell_max_voltage=registers[3] * 0.001,  # 7003: 0.001V
            cell_min_voltage=registers[4] * 0.001,  # 7004: 0.001V
            cell_max_temp=to_signed(registers[5]),  # 7005: 1°C
            cell_min_temp=to_signed(registers[6]),  # 7006: 1°C
            tag_max_v=registers[7],  # 7007
            tag_min_v=registers[8],  # 7008
            tag_max_t=registers[9],  # 7009
            tag_min_t=registers[10],  # 7010
            remaining_capacity=registers[11] * 0.01,  # 7011: 0.01AH
            full_charge_capacity=registers[12] * 0.01,  # 7012: 0.01AH
            power=to_int32(registers[13], registers[14]) * 0.1,  # 7013-7014: 0.1W
            cycle_count=registers[15],  # 7015
            status=RackStatus(registers[16]) if registers[16] in RackStatus._value2member_map_ else RackStatus.OFFLINE,
            alarm_status=registers[17],  # 7017
            soh=registers[18] * 0.1,  # 7018: 0.1%
            max_charge_current=registers[19] * 0.1,  # 7019: 0.1A
            max_discharge_current=registers[20] * 0.1,  # 7020: 0.1A
            max_charge_voltage=registers[21] * 0.1,  # 7021: 0.1V
            min_discharge_voltage=registers[22] * 0.1,  # 7022: 0.1V
            timestamp=datetime.now(),
        )


@dataclass
class SystemData:
    """
    System-level BMS data from registers 4000-4099.
    
    Register mapping:
    - 4000: system_status (U16)
    - 4001: total_voltage (U32, 0.1V) [4001-4002]
    - 4003: total_current (S32, 0.1A) [4003-4004]
    - 4005: total_soc (U16, 0.1%)
    - 4006: total_power (S32, 0.1kW) [4006-4007]
    - 4008: pcs_status (U16)
    - 4009: bms_mode (U16)
    - 4010: active_rack_count (U16)
    - 4011-4034: rack_enable_status (24 bits)
    """
    system_status: int = 0
    total_voltage: float = 0.0  # V
    total_current: float = 0.0  # A
    total_soc: float = 0.0  # %
    total_power: float = 0.0  # kW
    pcs_status: int = 0
    bms_mode: int = 0
    active_rack_count: int = 0
    rack_enable_status: List[bool] = field(default_factory=lambda: [False] * 24)
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_registers(cls, registers: List[int]) -> "SystemData":
        """Create SystemData from raw Modbus registers."""
        if len(registers) < 35:
            raise ValueError(f"Expected at least 35 registers, got {len(registers)}")

        def to_signed32(high: int, low: int) -> int:
            val = (high << 16) | low
            return val - 4294967296 if val > 2147483647 else val

        def to_unsigned32(high: int, low: int) -> int:
            return (high << 16) | low

        # Parse rack enable status from 24 bits
        rack_status = []
        for i in range(24):
            bit_index = i % 16
            reg_index = 11 + (i // 16)
            if reg_index < len(registers):
                rack_status.append(bool(registers[reg_index] & (1 << bit_index)))
            else:
                rack_status.append(False)

        return cls(
            system_status=registers[0],
            total_voltage=to_unsigned32(registers[1], registers[2]) * 0.1,
            total_current=to_signed32(registers[3], registers[4]) * 0.1,
            total_soc=registers[5] * 0.1,
            total_power=to_signed32(registers[6], registers[7]) * 0.1,
            pcs_status=registers[8],
            bms_mode=registers[9],
            active_rack_count=registers[10],
            rack_enable_status=rack_status,
            timestamp=datetime.now(),
        )


@dataclass
class BMSSnapshot:
    """Complete BMS system snapshot."""
    system: SystemData
    racks: List[RackData]
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def active_racks(self) -> List[RackData]:
        """Get list of active (online) racks."""
        return [r for r in self.racks if r.status != RackStatus.OFFLINE]

    @property
    def average_soc(self) -> float:
        """Calculate average SOC across all active racks."""
        active = self.active_racks
        if not active:
            return 0.0
        return sum(r.soc for r in active) / len(active)

    @property
    def total_power(self) -> float:
        """Calculate total power from all racks."""
        return sum(r.power for r in self.racks)

    @property
    def has_alarms(self) -> bool:
        """Check if any rack has alarms."""
        return any(r.alarm_status != 0 for r in self.racks)
