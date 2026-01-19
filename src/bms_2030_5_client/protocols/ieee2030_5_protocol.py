"""
IEEE 2030.5 Smart Energy Profile Protocol Definitions.

Reference: IEEE Std 2030.5™-2023 (Revision of IEEE Std 2030.5-2018)

This module contains constants, enumerations, and definitions for implementing
IEEE 2030.5 Smart Energy Profile Application Protocol for BMS/EMS communication.

Key Features:
- RESTful architecture using HTTP/HTTPS
- XML or EXI content encoding
- TLS security with certificate-based authentication
- Support for DER (Distributed Energy Resources) including battery storage
"""

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Final, Optional, Dict, List


# =============================================================================
# IEEE 2030.5 Protocol Configuration
# =============================================================================

class IEEE2030_5_CONFIG:
    """IEEE 2030.5 protocol configuration constants."""
    
    # Content Types (Clause 4.2)
    CONTENT_TYPE_XML: Final[str] = "application/sep+xml"
    CONTENT_TYPE_EXI: Final[str] = "application/sep-exi"
    
    # Default HTTP/HTTPS Ports
    HTTP_PORT: Final[int] = 80
    HTTPS_PORT: Final[int] = 443
    
    # TLS Configuration (Clause 6)
    TLS_VERSION: Final[str] = "1.2"  # TLS 1.2 minimum required
    CIPHER_SUITE: Final[str] = "TLS_ECDHE_ECDSA_WITH_AES_128_CCM_8"
    
    # Discovery (Clause 7)
    MDNS_SERVICE_TYPE: Final[str] = "_sep2._tcp"
    XMDNS_SERVICE_TYPE: Final[str] = "_sep2._tcp"
    
    # Polling defaults
    DEFAULT_POLL_RATE: Final[int] = 900  # 15 minutes in seconds


# =============================================================================
# HTTP Methods (Clause 4.1)
# =============================================================================

class HTTPMethod:
    """HTTP methods used in IEEE 2030.5 RESTful interface."""
    GET: Final[str] = "GET"       # Retrieve resource representation
    HEAD: Final[str] = "HEAD"     # Get headers without body
    PUT: Final[str] = "PUT"       # Update existing resource
    POST: Final[str] = "POST"     # Create new resource
    DELETE: Final[str] = "DELETE" # Remove resource


# =============================================================================
# HTTP Status Codes (Clause 5)
# =============================================================================

class HTTPStatus:
    """Common HTTP status codes for IEEE 2030.5."""
    
    # Success
    OK: Final[int] = 200
    CREATED: Final[int] = 201
    NO_CONTENT: Final[int] = 204
    
    # Redirection
    NOT_MODIFIED: Final[int] = 304
    
    # Client Errors
    BAD_REQUEST: Final[int] = 400
    UNAUTHORIZED: Final[int] = 401
    FORBIDDEN: Final[int] = 403
    NOT_FOUND: Final[int] = 404
    METHOD_NOT_ALLOWED: Final[int] = 405
    CONFLICT: Final[int] = 409
    PRECONDITION_FAILED: Final[int] = 412
    
    # Server Errors
    INTERNAL_SERVER_ERROR: Final[int] = 500
    NOT_IMPLEMENTED: Final[int] = 501
    SERVICE_UNAVAILABLE: Final[int] = 503


# =============================================================================
# Function Sets (Clause 8-10)
# =============================================================================

class FunctionSetIdentifiers:
    """
    IEEE 2030.5 Function Set Identifiers.
    
    Function sets are logical groupings of resources that cooperate
    to implement IEEE 2030.5 features.
    """
    
    # Support Function Sets (Clause 8)
    DEVICE_CAPABILITY: Final[str] = "DeviceCapability"
    SELF_DEVICE: Final[str] = "SelfDevice"
    END_DEVICE: Final[str] = "EndDevice"
    FUNCTION_SET_ASSIGNMENTS: Final[str] = "FunctionSetAssignments"
    SUBSCRIPTION_NOTIFICATION: Final[str] = "Subscription"
    RESPONSE: Final[str] = "Response"
    
    # Common Function Sets (Clause 9)
    TIME: Final[str] = "Time"
    POWER_STATUS: Final[str] = "PowerStatus"
    DEVICE_INFORMATION: Final[str] = "DeviceInformation"
    LOG_EVENT: Final[str] = "LogEvent"
    CONFIGURATION: Final[str] = "Configuration"
    FILE_DOWNLOAD: Final[str] = "FileDownload"
    
    # Smart Energy Function Sets (Clause 10)
    DEMAND_RESPONSE_LOAD_CONTROL: Final[str] = "DemandResponseProgram"
    METERING: Final[str] = "UsagePoint"
    PRICING: Final[str] = "TariffProfile"
    MESSAGING: Final[str] = "MessagingProgram"
    BILLING: Final[str] = "BillingPeriod"
    PREPAYMENT: Final[str] = "Prepayment"
    FLOW_RESERVATION: Final[str] = "FlowReservation"
    DER: Final[str] = "DER"
    METERING_MIRROR: Final[str] = "MirrorUsagePoint"


# =============================================================================
# DER Types (Clause 10.10 - Distributed Energy Resources)
# =============================================================================

class DERType(IntEnum):
    """
    DER device types as defined in IEEE 2030.5.
    
    Reference: IEEE Std 2030.5-2023, Clause 10.10
    """
    NOT_APPLICABLE = 0
    VIRTUAL_MIXED = 1          # Virtual or mixed DER
    RECIPROCATING_ENGINE = 2   # Engine generator
    FUEL_CELL = 3
    PHOTOVOLTAIC = 4           # Solar PV
    COMBINED_HEAT_POWER = 5    # CHP
    OTHER_GENERATION = 6
    BATTERY_STORAGE = 7        # ← BMS systems use this
    EV = 8                     # Electric Vehicle
    HVAC = 9
    IRRIGATION_PUMP = 10
    WATER_HEATER = 11
    POOL_PUMP = 12
    OTHER_LOAD = 13


class ConnectStatusType(IntFlag):
    """
    DER connection status flags.
    
    Reference: IEEE Std 2030.5-2023, ConnectStatusType
    """
    CONNECTED = 0x01      # DER is connected to grid
    AVAILABLE = 0x02      # DER is available for operation
    OPERATING = 0x04      # DER is currently operating
    TEST = 0x08           # DER is in test mode
    FAULT = 0x10          # DER has a fault condition


class OperationalModeStatusType(IntFlag):
    """
    DER operational mode status.
    
    Reference: IEEE Std 2030.5-2023, OperationalModeStatusType
    """
    OFF = 0x00            # DER is off
    OPERATING = 0x01      # Normal operation
    CHARGING = 0x02       # Battery is charging
    DISCHARGING = 0x04    # Battery is discharging


class InverterStatusType(IntEnum):
    """
    Inverter status values.
    
    Reference: IEEE Std 2030.5-2023
    """
    NOT_APPLICABLE = 0
    OFF = 1
    SLEEPING = 2          # Auto-shutdown
    STARTING = 3
    TRACKING_MPPT = 4     # Running MPPT
    FORCED_POWER_REDUCTION = 5
    SHUTTING_DOWN = 6
    FAULT = 7
    STANDBY = 8


class StorageModeStatusType(IntEnum):
    """
    Storage mode status values for battery systems.
    
    Reference: IEEE Std 2030.5-2023
    """
    NOT_APPLICABLE = 0
    CHARGING = 1
    DISCHARGING = 2
    HOLDING = 3           # Neither charging nor discharging
    TESTING = 4


class AlarmStatusType(IntFlag):
    """
    DER alarm status flags.
    
    Reference: IEEE Std 2030.5-2023, AlarmStatusType
    Used in DERStatus.alarmStatus field.
    
    Bits 11-31 are reserved per IEEE 2030.5 specification.
    """
    # Standard DER Fault/Condition flags (Bits 0-10)
    DER_FAULT_OVER_CURRENT = 0x00000001          # Bit 0: 過電流故障
    DER_FAULT_OVER_VOLTAGE = 0x00000002          # Bit 1: 過電壓故障
    DER_FAULT_UNDER_VOLTAGE = 0x00000004         # Bit 2: 欠壓故障
    DER_FAULT_OVER_FREQUENCY = 0x00000008        # Bit 3: 過頻率故障
    DER_FAULT_UNDER_FREQUENCY = 0x00000010       # Bit 4: 欠頻率故障
    DER_FAULT_VOLTAGE_IMBALANCE = 0x00000020     # Bit 5: 電壓不平衡故障
    DER_FAULT_CURRENT_IMBALANCE = 0x00000040     # Bit 6: 電流不平衡故障
    DER_FAULT_EMERGENCY_LOCAL = 0x00000080       # Bit 7: 在地緊急故障
    DER_FAULT_EMERGENCY_REMOTE = 0x00000100      # Bit 8: 遠端緊急故障
    DER_FAULT_LOW_POWER_INPUT = 0x00000200       # Bit 9: 低功率輸入故障
    DER_FAULT_PHASE_ROTATION = 0x00000400        # Bit 10: 相序旋轉故障
    # Bits 11-31: Reserved (保留位元)


# =============================================================================
# DER Control Modes (IEEE Std 1547-2018 via IEEE 2030.5)
# =============================================================================

class DERControlType(IntFlag):
    """
    DER control modes supported.
    
    Reference: IEEE Std 2030.5-2023, Annex E (Mapping to IEEE Std 1547-2018)
    """
    # Basic Controls
    CHARGE_MODE = 0x0001           # opModEnergize for charging
    DISCHARGE_MODE = 0x0002        # opModEnergize for discharging
    FIXED_POWER_FACTOR = 0x0004    # opModFixedPF
    FIXED_VAR = 0x0008             # opModFixedVar
    FIXED_W = 0x0010               # opModFixedW
    
    # Voltage Controls
    VOLT_VAR = 0x0020              # opModVoltVar (Volt-VAR)
    VOLT_WATT = 0x0040             # opModVoltWatt (Volt-Watt)
    FREQ_WATT = 0x0080             # opModFreqWatt (Frequency-Watt)
    
    # Limit Controls
    LIMIT_MAX_W = 0x0100           # opModMaxLimW
    LIMIT_MAX_VAR = 0x0200         # opModTargetVar
    LIMIT_MAX_DISCHARGE_W = 0x0400
    LIMIT_MAX_CHARGE_W = 0x0800
    
    # Grid Support
    FREQ_DROOP = 0x1000            # opModFreqDroop
    LFRT = 0x2000                  # Low Frequency Ride Through
    HFRT = 0x4000                  # High Frequency Ride Through
    LVRT = 0x8000                  # Low Voltage Ride Through
    HVRT = 0x10000                 # High Voltage Ride Through


# =============================================================================
# Units of Measure (UOM) - IEEE 2030.5 / IEC 61968
# =============================================================================

class UnitOfMeasure(IntEnum):
    """
    Units of measure codes from IEC 61968 / IEEE 2030.5.
    
    Reference: IEEE Std 2030.5-2023, UomType
    """
    NOT_APPLICABLE = 0
    AMPERES = 5           # A - Current
    KELVIN = 6            # K - Temperature
    DEGREES_CELSIUS = 23  # °C - Temperature
    VOLTAGE = 29          # V - Voltage
    JOULES = 31           # J - Energy
    HERTZ = 33            # Hz - Frequency
    WATTS = 38            # W - Active Power
    VOLT_AMPERES = 61     # VA - Apparent Power
    VAR = 63              # var - Reactive Power
    COSINE_THETA = 65     # cos(θ) - Power Factor
    VOLT_SECONDS = 66     # V·s
    VOLT_SQUARED = 67     # V²
    AMP_SQUARED = 69      # A²
    AMP_SQUARED_HOURS = 70  # A²h
    WATT_HOURS = 72       # Wh - Energy
    VAR_HOURS = 73        # varh - Reactive Energy
    VA_HOURS = 71         # VAh - Apparent Energy
    WATTS_PER_HERTZ = 75  # W/Hz - Frequency response
    PERCENT = 100         # % - Percentage
    AMP_HOURS = 106       # Ah - Capacity
    COUNT = 111           # Count/Number


# =============================================================================
# Power of Ten Multiplier (for scaling values)
# =============================================================================

class PowerOfTenMultiplier(IntEnum):
    """
    Power of ten multiplier for IEEE 2030.5 values.
    
    Value = integer_value × 10^multiplier
    """
    PICO = -12    # p
    NANO = -9     # n
    MICRO = -6    # μ
    MILLI = -3    # m
    CENTI = -2    # c
    DECI = -1     # d
    NONE = 0      # 1
    DECA = 1      # da
    HECTO = 2     # h
    KILO = 3      # k
    MEGA = 6      # M
    GIGA = 9      # G
    TERA = 12     # T


# =============================================================================
# Common URI Paths (Clause 4 & WADL)
# =============================================================================

class URIPaths:
    """
    Common IEEE 2030.5 URI paths.
    
    Reference: IEEE Std 2030.5-2023 WADL (sep_wadl.xml)
    """
    # Device Capability (root)
    DEVICE_CAPABILITY: Final[str] = "/dcap"
    
    # Self Device
    SELF_DEVICE: Final[str] = "/sdev"
    
    # End Devices
    END_DEVICE_LIST: Final[str] = "/edev"
    
    # Time
    TIME: Final[str] = "/tm"
    
    # DER Resources
    DER_LIST: Final[str] = "/der"
    DER_PROGRAM_LIST: Final[str] = "/derp"
    DER_CONTROL_LIST: Final[str] = "/derc"
    DER_CAPABILITY: Final[str] = "/dercap"
    DER_SETTINGS: Final[str] = "/derg"
    DER_STATUS: Final[str] = "/ders"
    DER_AVAILABILITY: Final[str] = "/dera"
    
    # Metering
    USAGE_POINT_LIST: Final[str] = "/upt"
    METER_READING_LIST: Final[str] = "/mr"
    READING_TYPE: Final[str] = "/rt"
    READING_LIST: Final[str] = "/r"
    
    # Mirror Metering (for client-side meters)
    MIRROR_USAGE_POINT_LIST: Final[str] = "/mup"
    MIRROR_METER_READING: Final[str] = "/mmr"
    
    # Demand Response
    DEMAND_RESPONSE_PROGRAM_LIST: Final[str] = "/dr"
    END_DEVICE_CONTROL_LIST: Final[str] = "/edc"
    
    # Pricing
    TARIFF_PROFILE_LIST: Final[str] = "/tp"
    
    # Response
    RESPONSE_LIST: Final[str] = "/rsps"
    
    # Subscription
    SUBSCRIPTION_LIST: Final[str] = "/sub"
    NOTIFICATION_LIST: Final[str] = "/ntfy"
    
    @staticmethod
    def for_end_device(edev_id: str, sub_path: str = "") -> str:
        """Build path for specific EndDevice resource."""
        return f"/edev/{edev_id}{sub_path}"
    
    @staticmethod
    def for_der(der_id: str, sub_path: str = "") -> str:
        """Build path for specific DER resource."""
        return f"/der/{der_id}{sub_path}"


# =============================================================================
# Device Identifier Formats (Clause 6)
# =============================================================================

@dataclass
class DeviceIdentifier:
    """
    IEEE 2030.5 Device Identifiers.
    
    LFDI (Long Form Device Identifier): 40 hex characters (160 bits)
    SFDI (Short Form Device Identifier): Derived from LFDI
    """
    
    @staticmethod
    def calculate_sfdi(lfdi: str) -> int:
        """
        Calculate SFDI from LFDI.
        
        SFDI = First 36 bits of LFDI (leftmost 9 hex chars) + 4-bit checksum
        
        Args:
            lfdi: 40-character hex string (160 bits)
            
        Returns:
            SFDI as integer
        """
        if len(lfdi) != 40:
            raise ValueError(f"LFDI must be 40 hex characters, got {len(lfdi)}")
        
        # Take first 36 bits (9 hex characters)
        truncated = int(lfdi[:9], 16) << 4
        
        # Calculate checksum (sum of nibbles mod 16)
        checksum = sum(int(c, 16) for c in lfdi[:9]) % 16
        
        return truncated | checksum
    
    @staticmethod
    def format_sfdi(sfdi: int) -> str:
        """Format SFDI as groups: XXXXX-XXXXX (human readable)."""
        sfdi_str = f"{sfdi:010d}"
        return f"{sfdi_str[:5]}-{sfdi_str[5:]}"


# =============================================================================
# Response Required Flags
# =============================================================================

class ResponseRequired(IntFlag):
    """
    Response required flags for DER controls.
    
    Reference: IEEE Std 2030.5-2023, responseRequired attribute
    """
    MESSAGE_RECEIVED = 0x01      # Response to indicate message received
    EVENT_STARTED = 0x02         # Response when event starts
    EVENT_COMPLETED = 0x04       # Response when event completes
    EVENT_CANCELLED = 0x08       # Response if event cancelled


class ResponseStatus(IntEnum):
    """
    Response status values.
    
    Reference: IEEE Std 2030.5-2023, status element in Response
    """
    EVENT_RECEIVED = 1
    EVENT_STARTED = 2
    EVENT_COMPLETED = 3
    EVENT_SUPERSEDED = 4
    EVENT_CANCELLED = 5
    EVENT_REJECTED = 6           # Client unable to comply
    EVENT_ABORTED = 7


# =============================================================================
# Quality Flags for Readings
# =============================================================================

class QualityFlags(IntFlag):
    """
    Quality flags for meter readings.
    
    Reference: IEEE Std 2030.5-2023, QualityFlags
    """
    VALID = 0x0001               # Data is valid
    MANUALLY_EDITED = 0x0002     # Data manually edited
    ESTIMATED = 0x0004           # Data is estimated
    QUESTIONABLE = 0x0008        # Quality is questionable
    DERIVED = 0x0010             # Derived/calculated value
    PROJECTED = 0x0020           # Projected (forecast) value


# =============================================================================
# Helper Functions
# =============================================================================

def watts_to_sep_value(watts: float, multiplier: int = 0) -> tuple[int, int]:
    """
    Convert watts to IEEE 2030.5 ActivePower format.
    
    Args:
        watts: Power in watts
        multiplier: Power of ten multiplier
        
    Returns:
        Tuple of (value, multiplier) for ActivePower
    """
    value = int(watts / (10 ** multiplier))
    return (value, multiplier)


def sep_value_to_watts(value: int, multiplier: int) -> float:
    """
    Convert IEEE 2030.5 ActivePower to watts.
    
    Args:
        value: Integer value from ActivePower
        multiplier: Power of ten multiplier
        
    Returns:
        Power in watts
    """
    return value * (10 ** multiplier)


def soc_to_sep_value(soc_percent: float) -> int:
    """
    Convert SOC percentage (0-100) to IEEE 2030.5 format (0-10000).
    
    Args:
        soc_percent: SOC as percentage (0.00 - 100.00)
        
    Returns:
        SOC value for IEEE 2030.5 (0-10000, representing 0.00%-100.00%)
    """
    return int(soc_percent * 100)


def sep_value_to_soc(sep_value: int) -> float:
    """
    Convert IEEE 2030.5 SOC value (0-10000) to percentage.
    
    Args:
        sep_value: IEEE 2030.5 SOC value (0-10000)
        
    Returns:
        SOC as percentage (0.00 - 100.00)
    """
    return sep_value / 100.0


# =============================================================================
# LogEvent Definitions (IEEE Std 2030.5-2023)
# =============================================================================

class FunctionSetIdentifier(IntEnum):
    """
    Function Set identifiers for LogEvent.
    
    Reference: IEEE Std 2030.5-2023, Table 27
    """
    GENERAL = 0               # General / unspecified
    TIME = 1                  # Time function set
    DEVICE_INFORMATION = 2    # Device Information
    DEVICE_CAPABILITY = 3     # Device Capability
    END_DEVICE = 4            # End Device
    SELF_DEVICE = 5           # Self Device
    FLOW_RESERVATION = 6      # Flow Reservation
    METERING = 7              # Metering
    MESSAGING = 8             # Messaging
    PRICING = 9               # Pricing
    DEMAND_RESPONSE = 10      # Demand Response / Load Control
    DER = 11                  # Distributed Energy Resources
    PREPAYMENT = 12           # Prepayment
    LOG_EVENT = 13            # Log Event (recursive)
    CONFIGURATION = 14        # Configuration
    SECURITY = 15             # Security


class LogEventCode(IntEnum):
    """
    Log event codes for DER alarms (Function Set = 11).
    
    Maps directly to AlarmStatusType bit positions.
    Reference: IEEE Std 2030.5-2023, LogEventCode for DER
    """
    # DER Fault codes (matching alarmStatus bit positions)
    DER_FAULT_OVER_CURRENT = 0       # Bit 0: 過電流故障
    DER_FAULT_OVER_VOLTAGE = 1       # Bit 1: 過電壓故障
    DER_FAULT_UNDER_VOLTAGE = 2      # Bit 2: 欠壓故障
    DER_FAULT_OVER_FREQUENCY = 3     # Bit 3: 過頻率故障
    DER_FAULT_UNDER_FREQUENCY = 4    # Bit 4: 欠頻率故障
    DER_FAULT_VOLTAGE_IMBALANCE = 5  # Bit 5: 電壓不平衡故障
    DER_FAULT_CURRENT_IMBALANCE = 6  # Bit 6: 電流不平衡故障
    DER_FAULT_EMERGENCY_LOCAL = 7    # Bit 7: 在地緊急故障
    DER_FAULT_EMERGENCY_REMOTE = 8   # Bit 8: 遠端緊急故障
    DER_FAULT_LOW_POWER_INPUT = 9    # Bit 9: 低功率輸入故障
    DER_FAULT_PHASE_ROTATION = 10    # Bit 10: 相序旋轉故障
    # Cleared events (use 128+ to indicate alarm cleared)
    DER_FAULT_CLEARED = 128          # Generic fault cleared


# LogEvent code descriptions for logging
LOG_EVENT_CODE_DESCRIPTIONS: Dict[int, str] = {
    LogEventCode.DER_FAULT_OVER_CURRENT: "Over current fault detected",
    LogEventCode.DER_FAULT_OVER_VOLTAGE: "Over voltage fault detected",
    LogEventCode.DER_FAULT_UNDER_VOLTAGE: "Under voltage fault detected",
    LogEventCode.DER_FAULT_OVER_FREQUENCY: "Over frequency fault detected",
    LogEventCode.DER_FAULT_UNDER_FREQUENCY: "Under frequency fault detected",
    LogEventCode.DER_FAULT_VOLTAGE_IMBALANCE: "Voltage imbalance fault detected",
    LogEventCode.DER_FAULT_CURRENT_IMBALANCE: "Current imbalance fault detected",
    LogEventCode.DER_FAULT_EMERGENCY_LOCAL: "Local emergency fault detected",
    LogEventCode.DER_FAULT_EMERGENCY_REMOTE: "Remote emergency fault detected",
    LogEventCode.DER_FAULT_LOW_POWER_INPUT: "Low power input fault detected",
    LogEventCode.DER_FAULT_PHASE_ROTATION: "Phase rotation fault detected",
    LogEventCode.DER_FAULT_CLEARED: "Fault cleared",
}
