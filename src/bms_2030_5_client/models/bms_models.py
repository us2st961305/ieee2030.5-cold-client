"""
Data models for BMS battery rack data.

Based on CUBE 電池組暫存器通訊表 V1.0.3
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    Single rack data from Modbus registers.
    
    IMPORTANT: Actual Modbus addresses are doc addresses - 1.
    Doc 7000 series -> Actual 6999 series
    
    Register mapping (offset 30 per rack):
    Doc -> Actual (index in registers list)
    - 7000 -> 6999 [0]: rack_vol (U16, 0.1V)
    - 7001 -> 7000 [1]: rack_current (S16, 0.1A)
    - 7002 -> 7001 [2]: SOC (U16, 0.1%)
    - 7003 -> 7002 [3]: cell_max_v (U16, 0.001V)
    - 7004 -> 7003 [4]: cell_min_v (U16, 0.001V)
    - 7005 -> 7004 [5]: cell_max_t (S16, 1°C)
    - 7006 -> 7005 [6]: cell_min_t (S16, 1°C)
    - 7007 -> 7006 [7]: tag_max_v (U16, enum)
    - 7008 -> 7007 [8]: tag_min_v (U16, enum)
    - 7009 -> 7008 [9]: tag_max_t (U16, enum)
    - 7010 -> 7009 [10]: tag_min_t (U16, enum)
    - 7011 -> 7010 [11]: RM (U16, 0.01AH)
    - 7012 -> 7011 [12]: FCC (U16, 0.01AH)
    - 7019 -> 7018 [19]: lecu_flag (U16, bitfield)
    - 7020 -> 7019 [20]: rack_flag (U16, bitfield)
    - 7022 -> 7021 [22]: SOH (U16, 1%)
    - 7025 -> 7024 [25]: relay_sw (U16, 0/1)
    - 7026 -> 7025 [26]: PF_release (U16, 0/1)
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
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
            soh=registers[22],  # 7022 -> 7021 [22]: SOH (U16, 1%)
            max_charge_current=registers[19] * 0.1,  # 7019: 0.1A
            max_discharge_current=registers[20] * 0.1,  # 7020: 0.1A
            max_charge_voltage=registers[21] * 0.1,  # 7021: 0.1V
            min_discharge_voltage=registers[23] * 0.1,  # 7023: 0.1V
            timestamp=datetime.now(timezone.utc),
        )


@dataclass
class SystemData:
    """
    System-level BMS data from registers.
    
    IMPORTANT: Actual Modbus addresses are doc addresses - 1.
    Doc 4000 series -> Actual 3999 series
    
    Register mapping (CUBE 電池組暫存器通訊表 V1.0.3):
    Doc -> Actual (index in registers list)
    - 4000 -> 3999 [0]: Vol_avg (U16, 0.1V) - Average voltage
    - 4001 -> 4000 [1]: total_curr (S16, 0.1A) - Total current
    - 4002 -> 4001 [2]: total_power (S16, 0.1kW) - Total power
    - 4003 -> 4002 [3]: deliy_CHG (U16, 0.1kWh) - Daily charge energy
    - 4004 -> 4003 [4]: deliy_DSC (U16, 0.1kWh) - Daily discharge energy
    - 4005 -> 4004 [5]: SOC_avg (U16, 0.1%) - Average SOC
    - 4006 -> 4005 [6]: RM_total (U16, AH) - Total remaining capacity
    - 4007 -> 4006 [7]: FCC_total (U16, AH) - Total full charge capacity
    - 4008 -> 4007 [8]: online_NO (U16) - Online rack count
    - 4009 -> 4008 [9]: allow_power (U16, 0.1kW) - Allowed power
    - 4010 -> 4009 [10]: Right_State (U16, bitfield) - Rack 1-12 state
    - 4011 -> 4010 [11]: Left_State (U16, bitfield) - Rack 13-24 state
    - 4012 -> 4011 [12]: SYS_state (U16, 0/1) - System state
    - 4016 -> 4015 [16]: all_max_t (S16, 1°C) - Maximum temperature
    - 4017 -> 4016 [17]: all_min_t (S16, 1°C) - Minimum temperature
    - 4042 -> 4041 [42]: allow_power_DSC (U16, 0.1kW) - Allowed discharge power
    - 4043 -> 4042 [43]: allow_power_CHG (U16, 0.1kW) - Allowed charge power
    """
    system_status: int = 0
    total_voltage: float = 0.0  # V (from 4000: Vol_avg)
    total_current: float = 0.0  # A (from 4001: total_curr)
    total_soc: float = 0.0  # % (from 4005: SOC_avg)
    total_power: float = 0.0  # kW (from 4002: total_power)
    charge_energy: float = 0.0  # kWh (from 4003: deliy_CHG)
    discharge_energy: float = 0.0  # kWh (from 4004: deliy_DSC)
    remaining_capacity: float = 0.0  # AH (from 4006: RM_total)
    full_charge_capacity: float = 0.0  # AH (from 4007: FCC_total)
    pcs_status: int = 0
    bms_mode: int = 0
    active_rack_count: int = 0  # (from 4008: online_NO)
    allowed_power: float = 0.0  # kW (from 4009: allow_power)
    allowed_charge_power: float = 0.0  # kW (from 4043: allow_power_CHG)
    allowed_discharge_power: float = 0.0  # kW (from 4042: allow_power_DSC)
    max_temperature: float = 0.0  # °C (from 4016: all_max_t)
    min_temperature: float = 0.0  # °C (from 4017: all_min_t)
    rack_enable_status: List[bool] = field(default_factory=lambda: [False] * 24)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_registers(cls, registers: List[int]) -> "SystemData":
        """
        Create SystemData from raw Modbus registers starting at 4000.
        
        Args:
            registers: List of register values starting from address 4000
            
        Returns:
            SystemData instance with parsed values
        """
        if len(registers) < 44:
            raise ValueError(f"Expected at least 44 registers, got {len(registers)}")

        def to_signed16(val: int) -> int:
            return val - 65536 if val > 32767 else val

        # Parse rack enable status from Right_State (4010) and Left_State (4011)
        rack_status = []
        # Right_State: Rack 1-12 (register 4010)
        right_state = registers[10] if len(registers) > 10 else 0
        for i in range(12):
            rack_status.append(bool(right_state & (1 << i)))
        # Left_State: Rack 13-24 (register 4011)
        left_state = registers[11] if len(registers) > 11 else 0
        for i in range(12):
            rack_status.append(bool(left_state & (1 << i)))

        return cls(
            system_status=registers[12] if len(registers) > 12 else 0,  # 4012: SYS_state
            total_voltage=registers[0] * 0.1,  # 4000: Vol_avg (0.1V)
            total_current=to_signed16(registers[1]) * 0.1,  # 4001: total_curr (0.1A)
            total_power=to_signed16(registers[2]) * 0.1,  # 4002: total_power (0.1kW)
            charge_energy=registers[3] * 0.1,  # 4003: deliy_CHG (0.1kWh)
            discharge_energy=registers[4] * 0.1,  # 4004: deliy_DSC (0.1kWh)
            total_soc=registers[5] * 0.1,  # 4005: SOC_avg (0.1%)
            remaining_capacity=registers[6],  # 4006: RM_total (AH)
            full_charge_capacity=registers[7],  # 4007: FCC_total (AH)
            active_rack_count=registers[8],  # 4008: online_NO
            allowed_power=registers[9] * 0.1,  # 4009: allow_power (0.1kW)
            max_temperature=to_signed16(registers[16]) if len(registers) > 16 else 0,  # 4016
            min_temperature=to_signed16(registers[17]) if len(registers) > 17 else 0,  # 4017
            allowed_discharge_power=registers[42] * 0.1 if len(registers) > 42 else 0,  # 4042
            allowed_charge_power=registers[43] * 0.1 if len(registers) > 43 else 0,  # 4043
            rack_enable_status=rack_status,
            timestamp=datetime.now(timezone.utc),
        )


@dataclass
class BMSSnapshot:
    """Complete BMS system snapshot."""
    system: SystemData
    racks: List[RackData]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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

    def to_dict(self) -> dict:
        """Serialize snapshot to dict for JSON API."""
        return {
            "voltage": self.system.total_voltage,
            "current": self.system.total_current,
            "soc": self.system.total_soc,
            "power": self.system.total_power,
            "timestamp": self.timestamp.isoformat(),
        }
