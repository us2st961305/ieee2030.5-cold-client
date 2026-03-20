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
    rtgAbnormalCategory: Optional[int] = None  # IEEE 1547 abnormal category: 0=N/A, 1=Cat I, 2=Cat II, 3=Cat III
    rtgMaxWh: Optional[ActivePower] = None  # Maximum energy storage capacity (Wh)
    type_: DERType = DERType.BATTERY_STORAGE


@dataclass_json
@dataclass
class DERSettings:
    """
    DER device settings.
    
    Current operational settings of the DER.
    """
    href: Optional[str] = None
    setGradW: Optional[int] = None  # Default ramp rate: % setMaxW/s, resolution 0.01 %/s (UInt16)
    setMaxW: Optional[ActivePower] = None  # Maximum active power
    setMaxVar: Optional[ReactivePower] = None
    setMaxChargeRateW: Optional[ActivePower] = None
    setMaxDischargeRateW: Optional[ActivePower] = None
    modesEnabled: Optional[int] = None  # DERControlType bitmask (HexBinary32) - enabled subset of modesSupported
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


# IANA Private Enterprise Number (PEN) for this organization
# See https://www.iana.org/assignments/enterprise-numbers/
DEFAULT_IANA_PEN = 0x2C155C03

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
# UsagePoint Models (Standard, non-Mirror — for server recovery via GET /upt)
# =============================================================================

@dataclass_json
@dataclass
class UsagePoint:
    """
    Standard UsagePoint resource (IEEE 2030.5 Section 10.11.3(b)).

    Server creates a UsagePoint for each MirrorUsagePoint POSTed.
    Used for recovery: GET /upt → find matching mRID → drill into sub-resources.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    roleFlags: Optional[str] = None
    serviceCategoryKind: int = 0
    status: int = 1
    deviceLFDI: Optional[str] = None
    MeterReadingListLink: Optional[Link] = None


@dataclass_json
@dataclass
class UsagePointList:
    """
    List of UsagePoint resources (GET /upt).
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    UsagePoint: List[UsagePoint] = field(default_factory=list)


@dataclass_json
@dataclass
class MeterReadingEntry:
    """
    Standard MeterReading resource from UsagePoint path (non-Mirror).

    Contains Link references to ReadingType, Reading, and ReadingSetList
    rather than inline data. Used for recovery via GET /upt/{id}/mr.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    ReadingLink: Optional[Link] = None
    ReadingSetListLink: Optional[Link] = None
    ReadingTypeLink: Optional[Link] = None


@dataclass_json
@dataclass
class MeterReadingListResponse:
    """
    List of standard MeterReading resources (GET /upt/{id}/mr).
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    MeterReading: List[MeterReadingEntry] = field(default_factory=list)


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
class EventStatus:
    """
    Current status of an event (IEEE Std 2030.5-2023, Section 12.16).
    
    currentStatus values:
        0 = Scheduled
        1 = Active
        2 = Cancelled
        3 = CancelledRandom
        4 = Superseded
    """
    currentStatus: int = 0
    dateTime: int = 0                                 # Unix timestamp of status change
    potentiallySuperseded: bool = False


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
    
    # Event status (from server, Section 12.16)
    EventStatus: Optional[EventStatus] = None
    randomizeStart: Optional[int] = None              # Random delay before start (seconds)
    randomizeDuration: Optional[int] = None           # Random adjustment to duration
    
    # Control parameters
    DERControlBase: Optional[DERControlBase] = None
    
    # Priority (lower = higher priority)
    primacy: int = 0
    
    # Response configuration (IEEE 2030.5-2023)
    replyTo: Optional[str] = None                     # URI to POST response to
    responseRequired: Optional[int] = None            # Bitmask: see ResponseRequired flags
    
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
    
    Note: 
    - Link fields may be parsed as Link objects by XML parser.
      Use get_*_href() methods to safely get the href strings.
    - ActiveDERControlListLink is DEPRECATED in IEEE 2030.5-2023.
      Use DERControlListLink (/derp/{id}/derc) instead.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: int = 0
    primacy: int = 0                                  # Program priority
    
    # Links to control lists (may be Link objects or strings)
    # DEPRECATED: ActiveDERControlListLink - use DERControlListLink instead
    ActiveDERControlListLink: Optional["Link"] = None
    DefaultDERControlLink: Optional["Link"] = None
    DERControlListLink: Optional["Link"] = None       # Preferred: /derp/{id}/derc
    DERCurveListLink: Optional["Link"] = None
    
    def _get_link_href(self, link: Optional["Link"]) -> Optional[str]:
        """Safely get href from a Link field."""
        if link is None:
            return None
        if isinstance(link, str):
            return link
        if hasattr(link, 'href'):
            return link.href
        return None
    
    def get_active_der_control_list_href(self) -> Optional[str]:
        """
        Safely get ActiveDERControlListLink href.
        
        DEPRECATED: Use get_der_control_list_href() instead per IEEE 2030.5-2023.
        """
        return self._get_link_href(self.ActiveDERControlListLink)
    
    def get_default_der_control_href(self) -> Optional[str]:
        """Safely get DefaultDERControlLink href."""
        return self._get_link_href(self.DefaultDERControlLink)
    
    def get_der_control_list_href(self) -> Optional[str]:
        """Safely get DERControlListLink href. This is the preferred method."""
        return self._get_link_href(self.DERControlListLink)
    
    def get_der_curve_list_href(self) -> Optional[str]:
        """Safely get DERCurveListLink href."""
        return self._get_link_href(self.DERCurveListLink)


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


# =============================================================================
# Function Set Assignments (FSA) Models
# =============================================================================

@dataclass_json
@dataclass
class FunctionSetAssignments:
    """
    Function Set Assignments resource.
    
    Reference: IEEE Std 2030.5-2023, FunctionSetAssignments
    
    FSA defines which function sets (programs, time resources, etc.) 
    are assigned to an EndDevice. The client must poll/subscribe to 
    detect changes.
    
    Note: Link fields may be parsed as Link objects by XML parser.
    Use get_der_program_list_href() to safely get the href string.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: int = 0
    
    # Links to function sets (may be Link objects or strings depending on parser)
    DERProgramListLink: Optional["Link"] = None
    ResponseSetListLink: Optional["Link"] = None
    TimeLink: Optional["Link"] = None
    
    # Other function set links (as needed)
    CustomerAccountListLink: Optional["Link"] = None
    DemandResponseProgramListLink: Optional["Link"] = None
    FileListLink: Optional["Link"] = None
    MessagingProgramListLink: Optional["Link"] = None
    PrepaymentListLink: Optional["Link"] = None
    TariffProfileListLink: Optional["Link"] = None
    UsagePointListLink: Optional["Link"] = None
    
    def get_der_program_list_href(self) -> Optional[str]:
        """Safely get DERProgramListLink href string."""
        if self.DERProgramListLink is None:
            return None
        if isinstance(self.DERProgramListLink, str):
            return self.DERProgramListLink
        if hasattr(self.DERProgramListLink, 'href'):
            return self.DERProgramListLink.href
        return None


@dataclass_json
@dataclass
class FunctionSetAssignmentsList:
    """
    List of FunctionSetAssignments resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    pollRate: int = 900
    FunctionSetAssignments: List[FunctionSetAssignments] = field(default_factory=list)


# =============================================================================
# Response Models (回報狀態)
# =============================================================================

class ResponseStatusType(IntEnum):
    """
    Response status codes for DER control events.
    
    Reference: IEEE Std 2030.5-2023 Table 27
    
    NOTE: Values are 1-based per spec. 0 is reserved.
    """
    RESERVED = 0                     # Reserved (do not use)
    EVENT_RECEIVED = 1               # Event received
    EVENT_STARTED = 2                # Event started (executed)
    EVENT_COMPLETED = 3              # Event completed normally
    EVENT_SUPERSEDED = 4             # Event superseded by higher priority
    EVENT_CANCELLED_WITH_RANDOM = 5  # Event cancelled with randomization
    EVENT_CANCELLED = 6              # Event cancelled
    EVENT_EXPIRED = 7                # Event expired (not executed)
    NO_USER_OPT_IN = 8              # User did not opt-in
    NO_USER_OPT_OUT = 9             # User opted out
    PARTIAL_OPT_OUT = 10             # Partial opt-out
    EVENT_ABORTED_SERVER = 11        # Server aborted
    EVENT_ABORTED_OVERSUB = 12       # Oversubscription
    EVENT_NOT_APPLICABLE = 253       # Event not applicable


@dataclass_json
@dataclass
class DERControlResponse:
    """
    Response to a DERControl event.
    
    Reference: IEEE Std 2030.5-2023, Response resource
    
    Clients must send responses to the replyTo URI when 
    responseRequired is specified in the event.
    """
    href: Optional[str] = None
    
    # Client identification (required)
    endDeviceLFDI: str = ""                           # 40 hex chars
    
    # Response status
    status: int = ResponseStatusType.EVENT_RECEIVED   # ResponseStatusType
    
    # Event identification
    subject: str = ""                                 # mRID of the DERControl
    
    # Timestamp
    createdDateTime: int = 0                          # Unix timestamp


@dataclass_json
@dataclass
class ResponseSet:
    """
    Response Set for grouping responses.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: int = 0
    ResponseListLink: Optional[str] = None


@dataclass_json
@dataclass
class ResponseSetList:
    """
    List of ResponseSet resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    ResponseSet: List[ResponseSet] = field(default_factory=list)


# =============================================================================
# DefaultDERControl Model
# =============================================================================

@dataclass_json
@dataclass
class DefaultDERControl:
    """
    Default DER Control settings.
    
    Reference: IEEE Std 2030.5-2023, DefaultDERControl
    
    Applied when no active DERControl events are present.
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: int = 0
    
    # Default control parameters
    DERControlBase: Optional[DERControlBase] = None
    
    # Ramp rate settings
    setGradW: Optional[int] = None                    # Default active power ramp rate


# =============================================================================
# Subscription / Notification Models (訂閱/通知模型)
# =============================================================================

class SubscriptionEncodingType(IntEnum):
    """
    Subscription encoding types.
    
    Reference: IEEE Std 2030.5-2023, Subscription resource
    """
    XML = 0     # application/sep+xml
    EXI = 1     # application/sep-exi


class NotificationStatusType(IntEnum):
    """
    Notification status codes.
    
    Reference: IEEE Std 2030.5-2023 Table 14
    """
    DEFAULT = 0                     # Subscription valid
    SUBSCRIPTION_CANCELLED = 1      # Subscription cancelled by server
    SUBSCRIPTION_SUPERSEDED = 2     # Subscription replaced
    RESOURCE_MOVED = 3              # subscribed resource moved
    RESOURCE_DELETED = 4            # subscribed resource removed


@dataclass_json
@dataclass
class Subscription:
    """
    IEEE 2030.5 Subscription resource.
    
    Reference: IEEE Std 2030.5-2023, Subscription resource (Clause 8.9)
    
    Used to subscribe to resource changes and receive push notifications.
    
    Example XML:
        <Subscription xmlns="urn:ieee:std:2030.5:ns" schemaVer="2.2">
            <subscribedResource>/derp/1/derc</subscribedResource>
            <notificationURI>https://client:8443/notify</notificationURI>
            <encoding>0</encoding>
            <level>+S2</level>
            <limit>10</limit>
        </Subscription>
    """
    href: Optional[str] = None
    
    # Required fields
    subscribedResource: str = ""              # Resource path to subscribe
    notificationURI: str = ""                 # Client endpoint for notifications
    encoding: int = SubscriptionEncodingType.XML  # 0=XML, 1=EXI
    level: str = "+S2"                        # Schema extension level
    limit: int = 10                           # Max resources per notification (0=all)
    
    # Optional
    newResourceURI: Optional[str] = None      # For create notifications
    
    # Set by server
    mRID: Optional[str] = None


@dataclass_json
@dataclass
class SubscriptionList:
    """
    List of Subscription resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    pollRate: int = 900
    Subscription: List[Subscription] = field(default_factory=list)


@dataclass_json
@dataclass
class Notification:
    """
    IEEE 2030.5 Notification resource.
    
    Reference: IEEE Std 2030.5-2023, Notification resource (Clause 8.9)
    
    Sent by server when a subscribed resource changes.
    
    Example XML:
        <Notification xmlns="urn:ieee:std:2030.5:ns">
            <subscribedResource>/derp/1/derc</subscribedResource>
            <newResourceURI>/derp/1/derc/5</newResourceURI>
            <status>0</status>
            <Resource xsi:type="DERControl">
                <!-- Embedded resource content -->
            </Resource>
        </Notification>
    """
    # Which resource triggered the notification
    subscribedResource: str = ""
    
    # URI of the new/changed resource (if applicable)
    newResourceURI: Optional[str] = None
    
    # Notification status (0 = subscription valid)
    status: int = NotificationStatusType.DEFAULT
    
    # The embedded resource (parsed separately based on xsi:type)
    # Type is determined by subscribed resource path
    Resource: Optional[str] = None            # Raw XML or parsed object


@dataclass_json
@dataclass
class NotificationList:
    """
    List of Notification resources.
    """
    href: Optional[str] = None
    all: int = 0
    results: int = 0
    Notification: List[Notification] = field(default_factory=list)


# =============================================================================
# DERControlResponse Extended (完整回應欄位)
# =============================================================================

class DERControlModesType(IntEnum):
    """
    DER Control modes bitmap for modesResponded field.
    
    Reference: IEEE Std 2030.5-2023, DERControlBase modes
    """
    OP_MOD_CONNECT = 0x0001           # Bit 0: opModConnect
    OP_MOD_ENERGIZE = 0x0002          # Bit 1: opModEnergize
    OP_MOD_FIXED_PF_ABSORB_W = 0x0004 # Bit 2: opModFixedPFAbsorbW
    OP_MOD_FIXED_PF_INJECT_W = 0x0008 # Bit 3: opModFixedPFInjectW
    OP_MOD_FIXED_VAR = 0x0010         # Bit 4: opModFixedVar
    OP_MOD_FIXED_W = 0x0020           # Bit 5: opModFixedW
    OP_MOD_FREQ_DROOP = 0x0040        # Bit 6: opModFreqDroop
    OP_MOD_FREQ_WATT = 0x0080         # Bit 7: opModFreqWatt
    OP_MOD_HFRT_MAY_TRIP = 0x0100     # Bit 8: opModHFRTMayTrip
    OP_MOD_HFRT_MUST_TRIP = 0x0200    # Bit 9: opModHFRTMustTrip
    OP_MOD_HVRT_MAY_TRIP = 0x0400     # Bit 10: opModHVRTMayTrip
    OP_MOD_HVRT_MUST_TRIP = 0x0800    # Bit 11: opModHVRTMustTrip
    OP_MOD_LFRT_MAY_TRIP = 0x1000     # Bit 12: opModLFRTMayTrip
    OP_MOD_MAX_LIM_W = 0x2000         # Bit 13: opModMaxLimW
    OP_MOD_TARGET_VAR = 0x4000        # Bit 14: opModTargetVar
    OP_MOD_TARGET_W = 0x8000          # Bit 15: opModTargetW
    OP_MOD_VOLT_VAR = 0x10000         # Bit 16: opModVoltVar
    OP_MOD_VOLT_WATT = 0x20000        # Bit 17: opModVoltWatt
    OP_MOD_WATT_PF = 0x40000          # Bit 18: opModWattPF
    OP_MOD_WATT_VAR = 0x80000         # Bit 19: opModWattVar


@dataclass_json
@dataclass
class DERControlResponseFull:
    """
    Full DERControlResponse with all required fields.
    
    Reference: IEEE Std 2030.5-2023, DERControlResponse
    
    Must be POST to the DERControl's replyTo URI when responseRequired is set.
    
    Example XML:
        <DERControlResponse xmlns="urn:ieee:std:2030.5:ns">
            <createdDateTime>1706900123</createdDateTime>
            <endDeviceLFDI>C7A14F7DA4E51A12ED9E3BCD6D818A5250462829</endDeviceLFDI>
            <status>1</status>
            <subject>A1B2C3D4E5F6...</subject>
            <modesResponded>0001</modesResponded>
        </DERControlResponse>
    """
    # Required: Response creation timestamp (Unix time)
    createdDateTime: int = 0
    
    # Required: Client's Long-Form Device Identifier (40 hex chars)
    endDeviceLFDI: str = ""
    
    # Required: Response status code
    status: int = ResponseStatusType.EVENT_RECEIVED
    
    # Required: mRID of the DERControl being responded to
    subject: str = ""
    
    # Required: Bitmap indicating which control modes this response applies to
    # HexBinary32 (8 hex chars, e.g., "00000001" for opModConnect)
    modesResponded: str = "00000000"
    
    @staticmethod
    def modes_to_hex(modes: int) -> str:
        """Convert modes bitmap to HexBinary32 string."""
        return f"{modes:08X}"
    
    @staticmethod
    def hex_to_modes(hex_str: str) -> int:
        """Convert HexBinary32 string to modes bitmap."""
        return int(hex_str, 16)