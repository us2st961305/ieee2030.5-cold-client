"""
IEEE 2030.5 data models for DER (Distributed Energy Resource).

Based on IEEE 2030.5 / Smart Energy Profile 2.0 specification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, IntFlag
from typing import List, Optional
from dataclasses_json import dataclass_json


class DERType(IntEnum):
    """DER device type."""
    NOT_APPLICABLE = 0
    VIRTUAL_MIXED = 1
    RECIPROCATING_ENGINE = 2
    FUEL_CELL = 3
    PHOTOVOLTAIC = 4
    COMBINED_HEAT_POWER = 5
    OTHER_GENERATION = 6
    BATTERY_STORAGE = 7
    EV = 8
    HVAC = 9
    IRRIGATION_PUMP = 10
    WATER_HEATER = 11
    POOL_PUMP = 12
    OTHER_LOAD = 13


class ConnectStatusType(IntFlag):
    """DER connection status flags."""
    CONNECTED = 0x01
    AVAILABLE = 0x02
    OPERATING = 0x04
    TEST = 0x08
    FAULT = 0x10


class OperationalModeStatusType(IntFlag):
    """DER operational mode status."""
    OFF = 0x00
    OPERATING = 0x01
    CHARGING = 0x02
    DISCHARGING = 0x04


@dataclass_json
@dataclass
class Link:
    """IEEE 2030.5 Link element with href and all attributes."""
    href: Optional[str] = None
    all: Optional[int] = None  # Total count of items


@dataclass_json
@dataclass
class ActivePower:
    """Real power in Watts."""
    multiplier: int = 0  # 10^multiplier
    value: int = 0  # Integer value


@dataclass_json
@dataclass
class ReactivePower:
    """Reactive power in VAR."""
    multiplier: int = 0
    value: int = 0


@dataclass_json
@dataclass
class Voltage:
    """Voltage in Volts."""
    multiplier: int = 0
    value: int = 0


@dataclass_json
@dataclass
class Current:
    """Current in Amps."""
    multiplier: int = 0
    value: int = 0


@dataclass_json
@dataclass
class ConnectStatusValue:
    """Connection status with timestamp. Value is hex binary string."""
    dateTime: int = 0
    value: str = "00"


@dataclass_json
@dataclass
class OperationalModeStatusValue:
    """Operational mode status with timestamp. Value is hex binary string."""
    dateTime: int = 0
    value: str = "00"


@dataclass_json
@dataclass
class InverterStatusValue:
    """Inverter status with timestamp. Value is hex binary string."""
    dateTime: int = 0
    value: str = "00"


@dataclass_json
@dataclass
class StorageModeStatusValue:
    """Storage mode status with timestamp. Value is hex binary string."""
    dateTime: int = 0
    value: str = "00"


@dataclass_json
@dataclass
class StateOfCharge:
    """State of charge percentage with timestamp."""
    dateTime: int = 0  # Unix timestamp
    value: int = 0  # 0-10000 (0.00% - 100.00%)


@dataclass_json
@dataclass
class Temperature:
    """Temperature in degrees Celsius."""
    multiplier: int = 0
    value: int = 0


@dataclass_json
@dataclass
class DERCapability:
    """
    DER device capabilities.
    
    Defines the maximum/minimum values for various DER parameters.
    """
    href: Optional[str] = None
    modesSupported: int = 0  # Bitmask of supported modes
    rtgMaxW: Optional[ActivePower] = None  # Maximum active power rating
    rtgMaxVA: Optional[ActivePower] = None  # Maximum apparent power rating
    rtgMaxVar: Optional[ReactivePower] = None  # Maximum reactive power rating
    rtgMaxChargeRateW: Optional[ActivePower] = None  # Max charge rate
    rtgMaxDischargeRateW: Optional[ActivePower] = None  # Max discharge rate
    rtgMaxChargeRateVA: Optional[ActivePower] = None
    rtgMaxDischargeRateVA: Optional[ActivePower] = None
    rtgMinPFOverExcited: Optional[int] = None  # Min power factor
    rtgMinPFUnderExcited: Optional[int] = None
    rtgVNom: Optional[Voltage] = None  # Nominal voltage
    rtgAMax: Optional[Current] = None  # Maximum current
    type_: DERType = DERType.BATTERY_STORAGE


@dataclass_json
@dataclass
class DERSettings:
    """
    DER device settings.
    
    Current operational settings of the DER.
    """
    href: Optional[str] = None
    setGradW: Optional[int] = None  # Ramp rate for active power
    setMaxW: Optional[ActivePower] = None  # Maximum active power
    setMaxVar: Optional[ReactivePower] = None
    setMaxChargeRateW: Optional[ActivePower] = None
    setMaxDischargeRateW: Optional[ActivePower] = None
    setMinPFOverExcited: Optional[int] = None
    setMinPFUnderExcited: Optional[int] = None
    setVRef: Optional[Voltage] = None
    setVRefOfs: Optional[Voltage] = None
    updatedTime: Optional[int] = None  # Timestamp


@dataclass_json
@dataclass
class DERStatus:
    """
    DER device status.
    
    Current operational status of the DER.
    """
    href: Optional[str] = None
    readingTime: int = 0  # Timestamp of the reading
    genConnectStatus: Optional[ConnectStatusValue] = None
    inverterStatus: Optional[InverterStatusValue] = None
    operationalModeStatus: Optional[OperationalModeStatusValue] = None
    stateOfChargeStatus: Optional[StateOfCharge] = None
    storModeStatus: Optional[StorageModeStatusValue] = None
    storConnectStatus: Optional[ConnectStatusValue] = None


@dataclass_json
@dataclass
class DERAvailability:
    """
    DER availability information.
    
    Indicates when and how much the DER is available.
    """
    href: Optional[str] = None
    availabilityDuration: Optional[int] = None  # Seconds
    maxChargeDuration: Optional[int] = None
    readingTime: int = 0
    reserveChargePercent: Optional[int] = None  # 0-10000
    reservePercent: Optional[int] = None
    statWAvail: Optional[ActivePower] = None  # Available W
    statVarAvail: Optional[ReactivePower] = None


@dataclass_json
@dataclass
class DER:
    """
    DER resource representation.
    
    Main DER object containing links to capability, settings, status, etc.
    """
    href: Optional[str] = None
    mRID: Optional[bytes] = None
    description: Optional[str] = None
    version: Optional[int] = None
    AssociatedDERProgramListLink: Optional[str] = None
    CurrentDERProgramLink: Optional[str] = None
    DERAvailabilityLink: Optional[str] = None
    DERCapabilityLink: Optional[str] = None
    DERSettingsLink: Optional[str] = None
    DERStatusLink: Optional[str] = None


@dataclass_json
@dataclass
class Reading:
    """
    Meter reading value.
    """
    href: Optional[str] = None
    localID: Optional[int] = None
    value: int = 0
    timePeriod: Optional[int] = None
    touTier: Optional[int] = None


@dataclass_json
@dataclass
class MirrorMeterReading:
    """
    Mirror meter reading for uploading to server.
    """
    href: Optional[str] = None
    mRID: Optional[bytes] = None
    description: Optional[str] = None
    readings: List["Reading"] = field(default_factory=list)


@dataclass_json
@dataclass
class EndDevice:
    """
    IEEE 2030.5 End Device.
    
    Represents the client device in the IEEE 2030.5 hierarchy.
    """
    href: Optional[str] = None
    lFDI: Optional[bytes] = None  # Long-form device identifier
    sFDI: Optional[int] = None  # Short-form device identifier
    changedTime: int = 0
    enabled: bool = True
    DERListLink: Optional[str] = None
    FunctionSetAssignmentsListLink: Optional[str] = None
    RegistrationLink: Optional[str] = None
    PowerStatusLink: Optional[str] = None
    DeviceStatusLink: Optional[str] = None


@dataclass_json
@dataclass
class DeviceCapability:
    """
    Device capability resource.
    
    Entry point for IEEE 2030.5 resource discovery.
    """
    href: Optional[str] = None
    pollRate: int = 900  # Default poll rate in seconds
    EndDeviceListLink: Optional['Link'] = None
    MirrorUsagePointListLink: Optional['Link'] = None
    SelfDeviceLink: Optional['Link'] = None
    TimeLink: Optional['Link'] = None
    DERProgramListLink: Optional['Link'] = None
    CustomerAccountListLink: Optional['Link'] = None
    DemandResponseProgramListLink: Optional['Link'] = None
    FileListLink: Optional['Link'] = None
    MessagingProgramListLink: Optional['Link'] = None
    PrepaymentListLink: Optional['Link'] = None
    ResponseSetListLink: Optional['Link'] = None
    TariffProfileListLink: Optional['Link'] = None
    UsagePointListLink: Optional['Link'] = None


@dataclass_json
@dataclass
class Time:
    """
    Time resource from server.
    """
    href: Optional[str] = None
    currentTime: int = 0  # UTC timestamp
    dstEndTime: int = 0
    dstOffset: int = 0
    dstStartTime: int = 0
    localTime: Optional[int] = None
    quality: int = 0
    tzOffset: int = 0
