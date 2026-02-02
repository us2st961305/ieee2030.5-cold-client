"""
IEEE 2030.5 data models for DER (Distributed Energy Resource).

Based on IEEE 2030.5 / Smart Energy Profile 2.0 specification.
"""

from __future__ import annotations

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
class AlarmStatusValue:
    """Alarm status with timestamp. Value is 4-character hex binary string (16-bit flags / HexBinary16)."""
    dateTime: int = 0
    value: str = "0000"


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
    
    Reference: IEEE Std 2030.5-2023, DERStatus resource.
    
    alarmStatus: Indicates current alarms/fault conditions as xs:hexBinary.
                 8-character hex string (e.g., "00000000").
                 Maps from BMS error status registers to IEEE 2030.5 format.
    """
    href: Optional[str] = None
    readingTime: int = 0  # Timestamp of the reading
    alarmStatus: Optional[str] = None  # Alarm status as hex binary string
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


@dataclass
class DERList:
    """
    List of DER resources.
    """
    href: Optional[str] = None
    all_: int = 0  # Total count
    results: int = 0  # Number of results in this response
    DER: List["DER"] = field(default_factory=list)


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
    lFDI: Optional[str] = None  # Long-form device identifier (40 hex chars)
    sFDI: Optional[int] = None  # Short-form device identifier
    changedTime: int = 0
    enabled: bool = True
    DERListLink: Optional[str] = None
    DeviceInformationLink: Optional[str] = None
    FunctionSetAssignmentsListLink: Optional[str] = None
    RegistrationLink: Optional[str] = None
    PowerStatusLink: Optional[str] = None
    DeviceStatusLink: Optional[str] = None


@dataclass_json
@dataclass
class EndDeviceList:
    """
    List of EndDevice resources.
    
    IEEE 2030.5 resource that contains multiple EndDevice instances.
    """
    href: Optional[str] = None
    all: int = 0  # Total count
    results: int = 0  # Number of results in this response
    EndDevice: List["EndDevice"] = field(default_factory=list)


class PowerSourceType(IntEnum):
    """Power source type for DeviceInformation."""
    NOT_APPLICABLE = 0
    MAINS = 1           # Mains power (AC grid)
    BATTERY = 2         # Battery power
    LOCAL_GENERATION = 3  # Local generation (e.g., solar)
    EMERGENCY = 4       # Emergency power
    UNKNOWN = 5         # Unknown power source


@dataclass_json
@dataclass
class GPSLocationType:
    """GPS location coordinates."""
    lat: Optional[str] = None  # Latitude in degrees
    lon: Optional[str] = None  # Longitude in degrees


@dataclass_json
@dataclass
class DeviceInformation:
    """
    IEEE 2030.5 Device Information.
    
    Descriptive information about a device, including manufacturer details,
    serial number, and software version. This is a sub-resource of EndDevice.
    
    URI: /edev/{id}/di
    
    Example XML:
        <DeviceInformation xmlns="urn:ieee:std:2030.5:ns" href="/edev/1/di">
            <lFDI>0123456789ABCDEF0123456789ABCDEF01234567</lFDI>
            <mfID>12345</mfID>
            <mfModel>BMS-2000</mfModel>
            <mfSerNum>SN-001</mfSerNum>
            <mfSerialNumber>SN-001</mfSerialNumber>
            <mfDate>1704585600</mfDate>
            <mfHwVer>1.0</mfHwVer>
            <mfInfo>Battery Storage Unit A</mfInfo>
            <primaryPower>1</primaryPower>
            <secondaryPower>2</secondaryPower>
            <swVer>1.0.0</swVer>
            <swActTime>1704585600</swActTime>
            <gpsLocation><lat>25.0330</lat><lon>121.5654</lon></gpsLocation>
        </DeviceInformation>
    """
    href: Optional[str] = None
    # Long-form device identifier (40 hex characters - required)
    lFDI: Optional[str] = None
    # Manufacturer ID (PEN - Private Enterprise Number)
    mfID: Optional[int] = None
    # Manufacturer model name/number
    mfModel: Optional[str] = None
    # Manufacturer serial number (short form - required)
    mfSerNum: Optional[str] = None
    # Manufacturer serial number (long form)
    mfSerialNumber: Optional[str] = None
    # Manufacture date (Unix timestamp - required)
    mfDate: Optional[int] = None
    # Primary power source
    primaryPower: Optional[int] = None  # PowerSourceType
    # Secondary power source (required)
    secondaryPower: Optional[int] = None  # PowerSourceType
    # Hardware version (required)
    mfHwVer: Optional[str] = None
    # Additional manufacturer info (free text - device name)
    mfInfo: Optional[str] = None
    # Software activation time (Unix timestamp - required)
    swActTime: Optional[int] = None
    # Software version
    swVer: Optional[str] = None
    # GPS location (required)
    gpsLocation: Optional[GPSLocationType] = None


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


# =============================================================================
# Metering Function Set Models (IEEE 2030.5 MirrorUsagePoint)
# =============================================================================


class AccumulationBehaviourType(IntEnum):
    """How reading values are accumulated over time."""
    NOT_APPLICABLE = 0
    CUMULATIVE = 3        # Running total
    DELTA_DATA = 4        # Change since last reading
    INDICATING = 6        # Instantaneous value
    SUMMATION = 9         # Sum over interval
    INSTANTANEOUS = 12    # Current value at moment


class CommodityType(IntEnum):
    """Type of commodity being measured."""
    NOT_APPLICABLE = 0
    ELECTRICITY_PRIMARY = 1
    ELECTRICITY_SECONDARY = 2
    AIR = 4
    NATURAL_GAS = 7
    WATER = 11
    ELECTRICITY_STORAGE = 15  # Battery storage


class FlowDirectionType(IntEnum):
    """Direction of energy flow."""
    NOT_APPLICABLE = 0
    FORWARD = 1           # From source to load
    REVERSE = 19          # From load to source (generation)
    NET = 4               # Net flow (forward - reverse)
    Q1_PLUS_Q2 = 5        # Quadrants 1+2
    Q1_PLUS_Q3 = 7        # Quadrants 1+3
    Q1_PLUS_Q4 = 8        # Quadrants 1+4


class DataQualifierType(IntEnum):
    """Data qualifier describing measurement type."""
    NOT_APPLICABLE = 0
    AVERAGE = 2
    MAXIMUM = 8
    MINIMUM = 9
    NORMAL = 12


class KindType(IntEnum):
    """Kind of reading."""
    NOT_APPLICABLE = 0
    CURRENCY = 3
    CURRENT = 4
    CURRENT_ANGLE = 5
    DATE = 7
    DEMAND = 8
    ENERGY = 12
    FREQUENCY = 15
    POWER = 37
    POWER_FACTOR = 38
    TEMPERATURE = 40
    VOLTAGE = 29
    VOLTAGE_ANGLE = 30


class UomType(IntEnum):
    """Unit of measure."""
    NOT_APPLICABLE = 0
    AMPERE = 5          # A
    KELVIN = 6          # K
    CELSIUS = 23        # °C
    VOLT = 29           # V
    WATT = 38           # W
    WATT_HOUR = 72      # Wh
    VAR = 63            # VAR
    PERCENT = 33        # %
    AMP_HOUR = 106      # Ah


class ServiceKind(IntEnum):
    """Type of service."""
    ELECTRICITY = 0
    GAS = 1
    WATER = 2
    TIME = 3
    HEAT = 4
    COOLING = 5
    PRESSURE = 6
    AIR = 9


class RoleFlagsType(IntEnum):
    """Role flags for usage point."""
    IS_MIRROR = 0x0001
    IS_PREMISE_AGGREGATION_POINT = 0x0002
    IS_PEV = 0x0004
    IS_DER = 0x0008
    IS_REVENUE_QUALITY = 0x0010
    IS_DC = 0x0020
    IS_SUBMETER = 0x0040


@dataclass_json
@dataclass
class DateTimeInterval:
    """Time period with duration and start time."""
    duration: int = 0     # Duration in seconds
    start: int = 0        # Start timestamp (Unix time)


@dataclass_json
@dataclass
class UnitValueType:
    """Unit value with multiplier."""
    multiplier: int = 0   # Power of ten multiplier
    unit: int = 0         # UomType
    value: int = 0        # Value


@dataclass_json
@dataclass
class ReadingType:
    """
    Type of data conveyed by a Reading.
    
    Based on IEEE 2030.5 ReadingType for describing measurement characteristics.
    """
    href: Optional[str] = None
    accumulationBehaviour: int = AccumulationBehaviourType.NOT_APPLICABLE
    commodity: int = CommodityType.ELECTRICITY_SECONDARY
    dataQualifier: int = DataQualifierType.NOT_APPLICABLE
    flowDirection: int = FlowDirectionType.NOT_APPLICABLE
    intervalLength: int = 0  # Default interval in seconds
    kind: int = KindType.NOT_APPLICABLE
    phase: Optional[int] = None  # PhaseCode
    powerOfTenMultiplier: int = 0  # 10^multiplier for value
    uom: int = UomType.NOT_APPLICABLE
    maxNumberOfIntervals: int = 0
    numberOfConsumptionBlocks: int = 0
    numberOfTouTiers: int = 0


@dataclass_json
@dataclass
class MeterReading:
    """
    A single meter reading value.
    
    IEEE 2030.5 Reading element for MirrorMeterReading.
    """
    href: Optional[str] = None
    localID: Optional[str] = None  # HexBinary16
    consumptionBlock: Optional[int] = None
    qualityFlags: Optional[str] = None  # HexBinary16
    timePeriod: Optional[DateTimeInterval] = None
    touTier: Optional[int] = None
    value: int = 0  # Int48 - actual reading value


@dataclass_json
@dataclass
class MirrorReadingSet:
    """
    A set of readings for a time period.
    
    IEEE 2030.5 MirrorReadingSet contains multiple readings.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    timePeriod: Optional[DateTimeInterval] = None
    Reading: List[MeterReading] = field(default_factory=list)


@dataclass_json
@dataclass
class MirrorMeterReading:
    """
    Meter reading with type and value(s).
    
    IEEE 2030.5 MirrorMeterReading for uploading readings to server.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    lastUpdateTime: Optional[int] = None
    nextUpdateTime: Optional[int] = None
    MirrorReadingSet: List[MirrorReadingSet] = field(default_factory=list)
    Reading: Optional[MeterReading] = None  # Current/latest reading
    ReadingType: Optional[ReadingType] = None


@dataclass_json
@dataclass
class MirrorMeterReadingList:
    """
    List of MirrorMeterReading resources.
    
    Used to POST multiple meter readings at once to MirrorUsagePoint.
    IEEE 2030.5 allows posting a list of readings for efficiency.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    MirrorMeterReading: List[MirrorMeterReading] = field(default_factory=list)


# Default IANA PEN - replace with your organization's registered PEN
# See https://www.iana.org/assignments/enterprise-numbers/
DEFAULT_IANA_PEN = 0x00000000  # Placeholder - should be replaced with actual PEN

# Reserved prefix for objects being created (accumulating)
MRID_RESERVED_PREFIX = "FFFFFFFFFFFFFFFFFFFFFFFF"  # 96 bits all 1s


def _generate_mrid(pen: Optional[int] = None, reserved: bool = False) -> str:
    """
    Generate a valid mRID (HexBinary128 - 32 hex chars).
    
    According to IEEE 2030.5 mRIDType specification:
    - Bits 0-31 (least significant 8 hex chars): IANA PEN provider ID
    - Bits 32-127 (most significant 24 hex chars): Unique ID assigned by provider
    
    Format: [96-bit unique ID][32-bit PEN] = 32 hex characters
    
    Special reserved: 0xFFFFFFFFFFFFFFFFFFFFFFFF[PEN] is reserved for
    objects being created (e.g., a ReadingSet still accumulating).
    
    Args:
        pen: IANA Private Enterprise Number (32-bit). Uses DEFAULT_IANA_PEN if None.
        reserved: If True, generates reserved mRID for objects being created.
        
    Returns:
        32-character uppercase hex string representing 128-bit mRID.
    """
    import uuid
    
    if pen is None:
        pen = DEFAULT_IANA_PEN
    
    # Ensure PEN is within 32-bit range
    pen = pen & 0xFFFFFFFF
    pen_hex = f"{pen:08X}"
    
    if reserved:
        # Reserved format for objects being created
        return MRID_RESERVED_PREFIX + pen_hex
    
    # Generate 96-bit unique ID (24 hex chars)
    # Using UUID4 and taking first 96 bits (24 hex chars)
    unique_id = uuid.uuid4().hex[:24].upper()
    
    return unique_id + pen_hex


def _roleflags_to_hex(flags: int) -> str:
    """Convert roleFlags integer to HexBinary16 (4 hex chars)."""
    return f"{flags:04X}"


@dataclass_json
@dataclass
class MirrorUsagePoint:
    """
    Mirror Usage Point for uploading meter data.
    
    IEEE 2030.5 MirrorUsagePoint is the primary resource for devices
    to upload metering data to the server. It mirrors a UsagePoint
    and contains MirrorMeterReading resources.
    
    Used for uploading BMS data:
    - Total SOC (%)
    - Total Current (A)
    - Charge/Discharge Power (W)
    - Charge Energy (Wh)
    - Discharge Energy (Wh)
    
    Note: mRID and roleFlags must be HexBinary format for IEEE 2030.5
    """
    href: Optional[str] = None
    mRID: Optional[str] = None  # HexBinary128 - will be auto-generated if None
    description: Optional[str] = None
    version: Optional[int] = None
    roleFlags: str = "0009"  # HexBinary16: IS_MIRROR | IS_DER = 0x0009
    serviceCategoryKind: int = ServiceKind.ELECTRICITY
    status: int = 1  # 0=off, 1=on
    deviceLFDI: Optional[str] = None  # HexBinary160
    MirrorMeterReading: List[MirrorMeterReading] = field(default_factory=list)
    postRate: int = 900  # Posting rate in seconds
    
    def __post_init__(self):
        """Auto-generate mRID if not provided."""
        if self.mRID is None:
            self.mRID = _generate_mrid()


@dataclass_json
@dataclass
class MirrorUsagePointList:
    """
    List of MirrorUsagePoint resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    pollRate: int = 900
    MirrorUsagePoint: List[MirrorUsagePoint] = field(default_factory=list)


# =============================================================================
# LogEvent Models
# =============================================================================

@dataclass_json
@dataclass
class LogEvent:
    """
    IEEE 2030.5 LogEvent resource.
    
    Used to report alarms and status changes to the server.
    Reference: IEEE Std 2030.5-2023
    """
    # Required fields
    createdDateTime: int = 0           # Unix timestamp when event occurred
    functionSet: int = 11              # 11 = DER function set
    logEventCode: int = 0              # Event code (maps to alarm type)
    logEventID: int = 0                # Unique event ID
    logEventPEN: int = 0               # 0 = IEEE defined codes
    profileID: int = 2                 # 2 = IEEE 2030.5 profile
    
    # Optional fields
    details: Optional[str] = None      # Human-readable description
    extendedData: Optional[int] = None # Extended data (if needed)
    href: Optional[str] = None         # Resource href (set by server)


@dataclass_json
@dataclass
class LogEventList:
    """
    List of LogEvent resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    pollRate: int = 900
    LogEvent: List[LogEvent] = field(default_factory=list)

# =============================================================================
# DER Control Models (功率控制)
# =============================================================================

@dataclass_json
@dataclass
class SignedPerCent:
    """
    Signed percentage value with multiplier.
    
    Used for power setpoints in DERControl.
    value × 10^multiplier = actual watts
    """
    value: int = 0
    multiplier: int = 0
    
    def to_watts(self) -> int:
        """Convert to watts."""
        return self.value * (10 ** self.multiplier)
    
    @classmethod
    def from_watts(cls, watts: int) -> "SignedPerCent":
        """Create from watts value."""
        if abs(watts) >= 1000000:
            return cls(value=watts // 1000000, multiplier=6)
        elif abs(watts) >= 1000:
            return cls(value=watts // 1000, multiplier=3)
        else:
            return cls(value=watts, multiplier=0)


@dataclass_json
@dataclass
class PerCent:
    """
    Unsigned percentage value (0-10000 = 0.00% - 100.00%).
    
    Used for limits in DERControl.
    """
    value: int = 0  # 0-10000
    
    def to_percent(self) -> float:
        """Convert to percentage (0.0 - 100.0)."""
        return self.value / 100.0
    
    @classmethod
    def from_percent(cls, percent: float) -> "PerCent":
        """Create from percentage (0.0 - 100.0)."""
        return cls(value=int(percent * 100))


@dataclass_json
@dataclass
class DateTimeInterval:
    """
    Time interval for DERControl scheduling.
    """
    duration: int = 0  # Duration in seconds (0 = indefinite)
    start: int = 0     # Start time as Unix timestamp
    
    def is_active(self, current_time: Optional[int] = None) -> bool:
        """Check if the interval is currently active."""
        import time
        now = current_time or int(time.time())
        
        if now < self.start:
            return False
        
        if self.duration == 0:
            return True  # Indefinite duration
        
        return now < (self.start + self.duration)
    
    def seconds_until_start(self, current_time: Optional[int] = None) -> int:
        """Get seconds until the interval starts."""
        import time
        now = current_time or int(time.time())
        return max(0, self.start - now)


@dataclass_json
@dataclass
class DERControlBase:
    """
    Base DER control parameters.
    
    Reference: IEEE Std 2030.5-2023, DERControlBase
    
    Power Sign Convention:
        - Positive (+): Discharge (export to grid)
        - Negative (-): Charge (import from grid)
    """
    # Fixed power modes
    opModFixedW: Optional[SignedPerCent] = None       # Fixed active power (W)
    opModFixedVar: Optional[SignedPerCent] = None     # Fixed reactive power (VAR)
    opModFixedPF: Optional[SignedPerCent] = None      # Fixed power factor
    
    # Limit modes
    opModMaxLimW: Optional[PerCent] = None            # Max power limit (% of rating)
    
    # Connect/Disconnect
    opModConnect: Optional[bool] = None               # True = connect, False = disconnect
    opModEnergize: Optional[bool] = None              # True = energize, False = de-energize
    
    # Ramp rate (gradient)
    rampTms: Optional[int] = None                     # Ramp time in seconds


@dataclass_json
@dataclass
class DERControl:
    """
    DER Control event from IEEE 2030.5 Server.
    
    Reference: IEEE Std 2030.5-2023, DERControl resource
    
    This represents a power control command from the EMS/Aggregator.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None                        # Unique identifier (hex string)
    description: Optional[str] = None
    version: int = 0
    
    # Creation and modification time
    creationTime: int = 0                             # Unix timestamp
    
    # Scheduling
    interval: Optional[DateTimeInterval] = None       # When this control is active
    
    # Event status
    randomizeStart: Optional[int] = None              # Random delay before start (seconds)
    randomizeDuration: Optional[int] = None           # Random adjustment to duration
    
    # Control parameters
    DERControlBase: Optional[DERControlBase] = None
    
    # Priority (lower = higher priority)
    primacy: int = 0
    
    def is_active(self, current_time: Optional[int] = None) -> bool:
        """Check if this control is currently active."""
        if self.interval is None:
            return True  # No interval means always active
        return self.interval.is_active(current_time)
    
    def get_power_setpoint_w(self) -> Optional[int]:
        """Get the power setpoint in watts, if specified."""
        if self.DERControlBase and self.DERControlBase.opModFixedW:
            return self.DERControlBase.opModFixedW.to_watts()
        return None


@dataclass_json
@dataclass
class DERControlList:
    """
    List of DERControl resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    pollRate: int = 300  # Default 5 minutes
    DERControl: List[DERControl] = field(default_factory=list)


@dataclass_json
@dataclass
class DERProgram:
    """
    DER Program containing DER controls.
    
    Reference: IEEE Std 2030.5-2023, DERProgram resource
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: int = 0
    primacy: int = 0                                  # Program priority
    
    # Links to control lists
    ActiveDERControlListLink: Optional[str] = None
    DefaultDERControlLink: Optional[str] = None
    DERControlListLink: Optional[str] = None
    DERCurveListLink: Optional[str] = None


@dataclass_json
@dataclass
class DERProgramList:
    """
    List of DERProgram resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    pollRate: int = 900
    DERProgram: List[DERProgram] = field(default_factory=list)