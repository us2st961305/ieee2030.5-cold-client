"""
Modbus to IEEE 2030.5 Mapping Definitions.

Defines the mapping between:
- CUBE/RS-485 Modbus registers
- IEEE 2030.5 resources and attributes

This enables:
- Reading Modbus values and uploading to IEEE 2030.5
- Receiving IEEE 2030.5 DER controls and writing to Modbus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any

from bms_2030_5_client.protocols.modbus_registers import (
    RS485_REGISTERS,
    CUBE_RACK_REGISTERS,
    CUBE_SYSTEM_REGISTERS,
)


class Direction(Enum):
    """Mapping direction."""
    READ = "read"           # Modbus → IEEE 2030.5 (upload)
    WRITE = "write"         # IEEE 2030.5 → Modbus (control)
    BIDIRECTIONAL = "bidirectional"


class ModbusSource(Enum):
    """Modbus register source."""
    RS485 = "rs485"         # RS-485 RTU (BMS V1.7)
    CUBE_RACK = "cube_rack"  # CUBE TCP Rack registers (7000 series)
    CUBE_SYSTEM = "cube_sys" # CUBE TCP System registers (4000 series)


class Sep2Resource(Enum):
    """IEEE 2030.5 resource type."""
    DER_STATUS = "ders"
    DER_CAPABILITY = "dercap"
    DER_SETTINGS = "derg"
    DER_AVAILABILITY = "dera"
    DER_CONTROL = "derc"
    MUP_READING = "mup"


@dataclass
class ModbusRegisterInfo:
    """Modbus register information."""
    address: int
    name: str
    name_zh: str
    unit: str
    scale: float = 1.0
    offset: float = 0.0
    signed: bool = False
    rw: str = "R"  # "R", "W", "R/W"
    source: ModbusSource = ModbusSource.CUBE_SYSTEM
    doc_address: Optional[int] = None  # Documentation address (before -1 offset)
    
    @property
    def readable(self) -> bool:
        return "R" in self.rw
    
    @property
    def writable(self) -> bool:
        return "W" in self.rw


@dataclass
class Sep2AttributeInfo:
    """IEEE 2030.5 attribute information."""
    resource: Sep2Resource
    attribute: str
    xpath: str
    description: str
    unit: str = ""
    sep_scale: float = 1.0  # Scale factor for IEEE 2030.5 value


@dataclass
class RegisterMapping:
    """
    Mapping between a Modbus register and IEEE 2030.5 attribute.
    """
    id: str
    modbus: ModbusRegisterInfo
    sep2: Sep2AttributeInfo
    direction: Direction = Direction.READ
    
    # Value conversion
    modbus_to_sep2: Optional[Callable[[int], Any]] = None
    sep2_to_modbus: Optional[Callable[[Any], int]] = None
    
    # Additional metadata
    description: str = ""
    enabled: bool = True


# ============================================
# Modbus Register Definitions
# ============================================

# CUBE System Registers (4000 series)
CUBE_SYSTEM_REGISTER_DEFS: Dict[str, ModbusRegisterInfo] = {
    "vol_avg": ModbusRegisterInfo(
        address=3999,
        doc_address=4000,
        name="vol_avg",
        name_zh="平均電壓",
        unit="0.1V",
        scale=0.1,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "total_curr": ModbusRegisterInfo(
        address=4000,
        doc_address=4001,
        name="total_curr",
        name_zh="總電流",
        unit="0.1A",
        scale=0.1,
        signed=True,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "total_power": ModbusRegisterInfo(
        address=4001,
        doc_address=4002,
        name="total_power",
        name_zh="總功率",
        unit="0.1kW",
        scale=0.1,
        signed=True,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "deliy_chg": ModbusRegisterInfo(
        address=4002,
        doc_address=4003,
        name="deliy_CHG",
        name_zh="日充電量",
        unit="0.1kWh",
        scale=0.1,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "deliy_dsc": ModbusRegisterInfo(
        address=4003,
        doc_address=4004,
        name="deliy_DSC",
        name_zh="日放電量",
        unit="0.1kWh",
        scale=0.1,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "soc_avg": ModbusRegisterInfo(
        address=4004,
        doc_address=4005,
        name="SOC_avg",
        name_zh="平均SOC",
        unit="0.1%",
        scale=0.1,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "rm_total": ModbusRegisterInfo(
        address=4005,
        doc_address=4006,
        name="RM_total",
        name_zh="總殘留電量",
        unit="AH",
        scale=1.0,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "fcc_total": ModbusRegisterInfo(
        address=4006,
        doc_address=4007,
        name="FCC_total",
        name_zh="總滿充電量",
        unit="AH",
        scale=1.0,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "online_no": ModbusRegisterInfo(
        address=4007,
        doc_address=4008,
        name="online_NO",
        name_zh="在線數量",
        unit="N.A.",
        scale=1.0,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "allow_power": ModbusRegisterInfo(
        address=4008,
        doc_address=4009,
        name="allow_power",
        name_zh="允許功率",
        unit="0.1kW",
        scale=0.1,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "all_max_t": ModbusRegisterInfo(
        address=4015,
        doc_address=4016,
        name="all_max_t",
        name_zh="最高溫度",
        unit="°C",
        scale=1.0,
        signed=True,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "all_min_t": ModbusRegisterInfo(
        address=4016,
        doc_address=4017,
        name="all_min_t",
        name_zh="最低溫度",
        unit="°C",
        scale=1.0,
        signed=True,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "on_all_relay": ModbusRegisterInfo(
        address=4017,
        doc_address=4018,
        name="ON_all_relay",
        name_zh="全開繼電器",
        unit="0/1",
        scale=1.0,
        rw="R/W",
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "off_all_relay": ModbusRegisterInfo(
        address=4018,
        doc_address=4019,
        name="OFF_all_relay",
        name_zh="全關繼電器",
        unit="0/1",
        scale=1.0,
        rw="R/W",
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "allow_power_dsc": ModbusRegisterInfo(
        address=4041,
        doc_address=4042,
        name="allow_power_DSC",
        name_zh="允許放電功率",
        unit="0.1kW",
        scale=0.1,
        source=ModbusSource.CUBE_SYSTEM,
    ),
    "allow_power_chg": ModbusRegisterInfo(
        address=4042,
        doc_address=4043,
        name="allow_power_CHG",
        name_zh="允許充電功率",
        unit="0.1kW",
        scale=0.1,
        source=ModbusSource.CUBE_SYSTEM,
    ),
}

# CUBE Rack Registers (7000 series)
CUBE_RACK_REGISTER_DEFS: Dict[str, ModbusRegisterInfo] = {
    "rack_vol": ModbusRegisterInfo(
        address=6999,
        doc_address=7000,
        name="rack_vol",
        name_zh="Rack電壓",
        unit="0.1V",
        scale=0.1,
        source=ModbusSource.CUBE_RACK,
    ),
    "rack_current": ModbusRegisterInfo(
        address=7000,
        doc_address=7001,
        name="rack_current",
        name_zh="Rack電流",
        unit="0.1A",
        scale=0.1,
        signed=True,
        source=ModbusSource.CUBE_RACK,
    ),
    "rack_soc": ModbusRegisterInfo(
        address=7001,
        doc_address=7002,
        name="SOC",
        name_zh="Rack SOC",
        unit="0.1%",
        scale=0.1,
        source=ModbusSource.CUBE_RACK,
    ),
    "cell_max_v": ModbusRegisterInfo(
        address=7002,
        doc_address=7003,
        name="cell_max_v",
        name_zh="最高電芯電壓",
        unit="0.001V",
        scale=0.001,
        source=ModbusSource.CUBE_RACK,
    ),
    "cell_min_v": ModbusRegisterInfo(
        address=7003,
        doc_address=7004,
        name="cell_min_v",
        name_zh="最低電芯電壓",
        unit="0.001V",
        scale=0.001,
        source=ModbusSource.CUBE_RACK,
    ),
    "cell_max_t": ModbusRegisterInfo(
        address=7004,
        doc_address=7005,
        name="cell_max_t",
        name_zh="最高電芯溫度",
        unit="°C",
        scale=1.0,
        signed=True,
        source=ModbusSource.CUBE_RACK,
    ),
    "cell_min_t": ModbusRegisterInfo(
        address=7005,
        doc_address=7006,
        name="cell_min_t",
        name_zh="最低電芯溫度",
        unit="°C",
        scale=1.0,
        signed=True,
        source=ModbusSource.CUBE_RACK,
    ),
    "rack_soh": ModbusRegisterInfo(
        address=7021,
        doc_address=7022,
        name="SOH",
        name_zh="Rack SOH",
        unit="1%",
        scale=1.0,
        source=ModbusSource.CUBE_RACK,
    ),
    "relay_sw": ModbusRegisterInfo(
        address=7024,
        doc_address=7025,
        name="relay_sw",
        name_zh="繼電器開關",
        unit="0/1",
        scale=1.0,
        rw="R/W",
        source=ModbusSource.CUBE_RACK,
    ),
    "pf_release": ModbusRegisterInfo(
        address=7025,
        doc_address=7026,
        name="PF_release",
        name_zh="解除永久保護",
        unit="0/1",
        scale=1.0,
        rw="R/W",
        source=ModbusSource.CUBE_RACK,
    ),
}

# RS-485 Registers
RS485_REGISTER_DEFS: Dict[str, ModbusRegisterInfo] = {
    "total_voltage": ModbusRegisterInfo(
        address=0x0001,
        name="TOTAL_VOLTAGE",
        name_zh="總電壓",
        unit="0.1V",
        scale=0.1,
        source=ModbusSource.RS485,
    ),
    "total_current": ModbusRegisterInfo(
        address=0x0002,
        name="TOTAL_CURRENT",
        name_zh="總電流",
        unit="0.1A",
        scale=0.1,
        offset=-1600.0,  # -1600A offset
        source=ModbusSource.RS485,
    ),
    "soc": ModbusRegisterInfo(
        address=0x0003,
        name="SOC",
        name_zh="SOC",
        unit="0.1%",
        scale=0.1,
        source=ModbusSource.RS485,
    ),
    "cell_max_voltage": ModbusRegisterInfo(
        address=0x0004,
        name="CELL_MAX_VOLTAGE",
        name_zh="最高電芯電壓",
        unit="0.001V",
        scale=0.001,
        source=ModbusSource.RS485,
    ),
    "cell_min_voltage": ModbusRegisterInfo(
        address=0x0005,
        name="CELL_MIN_VOLTAGE",
        name_zh="最低電芯電壓",
        unit="0.001V",
        scale=0.001,
        source=ModbusSource.RS485,
    ),
    "cell_max_temp": ModbusRegisterInfo(
        address=0x0006,
        name="CELL_MAX_TEMP",
        name_zh="最高電芯溫度",
        unit="°C",
        scale=1.0,
        offset=-40.0,
        source=ModbusSource.RS485,
    ),
    "cell_min_temp": ModbusRegisterInfo(
        address=0x0007,
        name="CELL_MIN_TEMP",
        name_zh="最低電芯溫度",
        unit="°C",
        scale=1.0,
        offset=-40.0,
        source=ModbusSource.RS485,
    ),
    "soh": ModbusRegisterInfo(
        address=0x000D,
        name="SOH",
        name_zh="SOH",
        unit="1%",
        scale=1.0,
        source=ModbusSource.RS485,
    ),
    "relay_switch": ModbusRegisterInfo(
        address=0x000E,
        name="RELAY_SWITCH",
        name_zh="繼電器開關",
        unit="0/1",
        scale=1.0,
        rw="R/W",
        source=ModbusSource.RS485,
    ),
}


# ============================================
# IEEE 2030.5 Attribute Definitions
# ============================================

SEP2_ATTRIBUTE_DEFS: Dict[str, Sep2AttributeInfo] = {
    # DER Status (ders)
    "ders_soc": Sep2AttributeInfo(
        resource=Sep2Resource.DER_STATUS,
        attribute="stateOfChargeStatus.value",
        xpath="//DERStatus/stateOfChargeStatus/value",
        description="State of Charge",
        unit="%",
        sep_scale=100.0,  # 0-10000 = 0-100%
    ),
    "ders_operational_state": Sep2AttributeInfo(
        resource=Sep2Resource.DER_STATUS,
        attribute="operationalModeStatus.value",
        xpath="//DERStatus/operationalModeStatus/value",
        description="Operational Mode",
    ),
    
    # DER Capability (dercap)
    "dercap_max_charge": Sep2AttributeInfo(
        resource=Sep2Resource.DER_CAPABILITY,
        attribute="rtgMaxChargeRate.value",
        xpath="//DERCapability/rtgMaxChargeRate/value",
        description="Max Charge Rate",
        unit="W",
    ),
    "dercap_max_discharge": Sep2AttributeInfo(
        resource=Sep2Resource.DER_CAPABILITY,
        attribute="rtgMaxDischargeRate.value",
        xpath="//DERCapability/rtgMaxDischargeRate/value",
        description="Max Discharge Rate",
        unit="W",
    ),
    "dercap_max_w": Sep2AttributeInfo(
        resource=Sep2Resource.DER_CAPABILITY,
        attribute="rtgMaxW.value",
        xpath="//DERCapability/rtgMaxW/value",
        description="Max Active Power",
        unit="W",
    ),
    "dercap_max_wh": Sep2AttributeInfo(
        resource=Sep2Resource.DER_CAPABILITY,
        attribute="rtgMaxWh.value",
        xpath="//DERCapability/rtgMaxWh/value",
        description="Max Storage Capacity",
        unit="Wh",
    ),
    
    # DER Settings (derg)
    "derg_set_max_w": Sep2AttributeInfo(
        resource=Sep2Resource.DER_SETTINGS,
        attribute="setMaxW.value",
        xpath="//DERSettings/setMaxW/value",
        description="Set Max Active Power",
        unit="W",
    ),
    
    # DER Availability (dera)
    "dera_avail_discharge": Sep2AttributeInfo(
        resource=Sep2Resource.DER_AVAILABILITY,
        attribute="availabilityDuration",
        xpath="//DERAvailability/availabilityDuration",
        description="Discharge Availability Duration",
        unit="s",
    ),
    
    # DER Control (derc) - WRITE direction
    "derc_op_mod_fixed_w": Sep2AttributeInfo(
        resource=Sep2Resource.DER_CONTROL,
        attribute="opModFixedW.value",
        xpath="//DERControl/DERControlBase/opModFixedW/value",
        description="Fixed Active Power Setpoint",
        unit="W",
    ),
    
    # MirrorUsagePoint Readings
    "mup_soc": Sep2AttributeInfo(
        resource=Sep2Resource.MUP_READING,
        attribute="Reading.value",
        xpath="//MirrorMeterReading/Reading/value",
        description="SOC Reading",
        unit="%",
        sep_scale=100.0,
    ),
    "mup_power": Sep2AttributeInfo(
        resource=Sep2Resource.MUP_READING,
        attribute="Reading.value",
        xpath="//MirrorMeterReading/Reading/value",
        description="Power Reading",
        unit="W",
    ),
}


# ============================================
# Default Mappings
# ============================================

DEFAULT_MAPPINGS: List[RegisterMapping] = [
    # SOC: Modbus → IEEE 2030.5 DER Status / MUP
    RegisterMapping(
        id="soc_to_ders",
        modbus=CUBE_SYSTEM_REGISTER_DEFS["soc_avg"],
        sep2=SEP2_ATTRIBUTE_DEFS["ders_soc"],
        direction=Direction.READ,
        modbus_to_sep2=lambda v: int(v * 10),  # 0.1% to 0.01%
        description="SOC → DER Status",
    ),
    RegisterMapping(
        id="soc_to_mup",
        modbus=CUBE_SYSTEM_REGISTER_DEFS["soc_avg"],
        sep2=SEP2_ATTRIBUTE_DEFS["mup_soc"],
        direction=Direction.READ,
        modbus_to_sep2=lambda v: int(v * 10),
        description="SOC → MUP Reading",
    ),
    
    # Power: Modbus → MUP
    RegisterMapping(
        id="power_to_mup",
        modbus=CUBE_SYSTEM_REGISTER_DEFS["total_power"],
        sep2=SEP2_ATTRIBUTE_DEFS["mup_power"],
        direction=Direction.READ,
        modbus_to_sep2=lambda v: int(v * 100),  # 0.1kW to W
        description="Total Power → MUP Reading",
    ),
    
    # Max Charge/Discharge → DER Capability
    RegisterMapping(
        id="allow_chg_to_dercap",
        modbus=CUBE_SYSTEM_REGISTER_DEFS["allow_power_chg"],
        sep2=SEP2_ATTRIBUTE_DEFS["dercap_max_charge"],
        direction=Direction.READ,
        modbus_to_sep2=lambda v: int(v * 100),  # 0.1kW to W
        description="Allow Charge → DER Capability",
    ),
    RegisterMapping(
        id="allow_dsc_to_dercap",
        modbus=CUBE_SYSTEM_REGISTER_DEFS["allow_power_dsc"],
        sep2=SEP2_ATTRIBUTE_DEFS["dercap_max_discharge"],
        direction=Direction.READ,
        modbus_to_sep2=lambda v: int(v * 100),
        description="Allow Discharge → DER Capability",
    ),
    
    # DER Control → Modbus (WRITE direction)
    # Note: This requires specific Modbus write register for PCS control
    # Using simulation mode by default (see power-control-safety.md)
]


# ============================================
# Mapping Manager
# ============================================

class MappingManager:
    """
    Manages Modbus ↔ IEEE 2030.5 mappings.
    """
    
    def __init__(self):
        self._mappings: Dict[str, RegisterMapping] = {}
        self._load_defaults()
    
    def _load_defaults(self) -> None:
        """Load default mappings."""
        for mapping in DEFAULT_MAPPINGS:
            self._mappings[mapping.id] = mapping
    
    @property
    def mappings(self) -> Dict[str, RegisterMapping]:
        """Get all mappings."""
        return dict(self._mappings)
    
    def get_readable_mappings(self) -> List[RegisterMapping]:
        """Get mappings for Modbus → IEEE 2030.5 direction."""
        return [
            m for m in self._mappings.values()
            if m.direction in (Direction.READ, Direction.BIDIRECTIONAL)
            and m.enabled
        ]
    
    def get_writable_mappings(self) -> List[RegisterMapping]:
        """Get mappings for IEEE 2030.5 → Modbus direction."""
        return [
            m for m in self._mappings.values()
            if m.direction in (Direction.WRITE, Direction.BIDIRECTIONAL)
            and m.enabled
        ]
    
    def get_all_registers(self) -> Dict[str, Dict[str, ModbusRegisterInfo]]:
        """Get all available Modbus registers grouped by source."""
        return {
            "cube_system": CUBE_SYSTEM_REGISTER_DEFS,
            "cube_rack": CUBE_RACK_REGISTER_DEFS,
            "rs485": RS485_REGISTER_DEFS,
        }
    
    def get_all_sep2_attributes(self) -> Dict[str, Sep2AttributeInfo]:
        """Get all IEEE 2030.5 attributes."""
        return SEP2_ATTRIBUTE_DEFS
    
    def add_mapping(self, mapping: RegisterMapping) -> None:
        """Add or update a mapping."""
        self._mappings[mapping.id] = mapping
    
    def remove_mapping(self, mapping_id: str) -> bool:
        """Remove a mapping by ID."""
        if mapping_id in self._mappings:
            del self._mappings[mapping_id]
            return True
        return False
    
    def enable_mapping(self, mapping_id: str) -> bool:
        """Enable a mapping."""
        if mapping_id in self._mappings:
            self._mappings[mapping_id].enabled = True
            return True
        return False
    
    def disable_mapping(self, mapping_id: str) -> bool:
        """Disable a mapping."""
        if mapping_id in self._mappings:
            self._mappings[mapping_id].enabled = False
            return True
        return False


# Global instance
mapping_manager = MappingManager()
