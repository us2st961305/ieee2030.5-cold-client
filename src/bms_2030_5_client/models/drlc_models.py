"""
IEEE 2030.5-2023 Demand Response and Load Control (DRLC) Function Set.

This module provides the complete DRLC implementation including:
- DemandResponseProgram: Container for load control events
- EndDeviceControl: Individual load control events
- LoadShedAvailability: Device load shed capabilities
- ApplianceLoadReduction: Appliance-specific load reduction

Reference: IEEE Std 2030.5-2023
- Section 10.8: Demand Response Function Set
- Table 27: deviceCategory values
- Table 28: appliance type values
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag, IntEnum
from typing import Optional, List
from dataclasses_json import dataclass_json


# =============================================================================
# Device Category (Table 27) - HexBinary32
# =============================================================================

class DeviceCategoryType(IntFlag):
    """
    Device Category bitmap (HexBinary32).
    
    Reference: IEEE Std 2030.5-2023 Table 27
    
    Indicates the types of end device loads that can be controlled.
    Multiple categories can be combined.
    """
    # Bit 0: Programmable Communicating Thermostat
    PROGRAMMABLE_COMMUNICATING_THERMOSTAT = 0x00000001
    
    # Bit 1: Strip Heaters
    STRIP_HEATERS = 0x00000002
    
    # Bit 2: Baseboard Heaters
    BASEBOARD_HEATERS = 0x00000004
    
    # Bit 3: Water Heater
    WATER_HEATER = 0x00000008
    
    # Bit 4: Pool Pump
    POOL_PUMP = 0x00000010
    
    # Bit 5: Sauna
    SAUNA = 0x00000020
    
    # Bit 6: Hot Tub
    HOT_TUB = 0x00000040
    
    # Bit 7: Smart Appliance
    SMART_APPLIANCE = 0x00000080
    
    # Bit 8: Irrigation Pump
    IRRIGATION_PUMP = 0x00000100
    
    # Bit 9: Managed Commercial & Industrial Loads
    MANAGED_COMMERCIAL_INDUSTRIAL = 0x00000200
    
    # Bit 10: Simple Misc. Loads
    SIMPLE_MISC_LOADS = 0x00000400
    
    # Bit 11: Exterior Lighting
    EXTERIOR_LIGHTING = 0x00000800
    
    # Bit 12: Interior Lighting
    INTERIOR_LIGHTING = 0x00001000
    
    # Bit 13: Electric Vehicle
    ELECTRIC_VEHICLE = 0x00002000
    
    # Bit 14: Generation Systems
    GENERATION_SYSTEMS = 0x00004000
    
    # Bit 15: Load Control Switch
    LOAD_CONTROL_SWITCH = 0x00008000
    
    # Bit 16: Smart Inverter
    SMART_INVERTER = 0x00010000
    
    # Bit 17: EVSE (EV Supply Equipment)
    EVSE = 0x00020000
    
    # Bit 18: Residential Energy Storage Unit
    RESIDENTIAL_ENERGY_STORAGE = 0x00040000
    
    # Bit 19: Energy Management System
    ENERGY_MANAGEMENT_SYSTEM = 0x00080000
    
    # Bit 20: Smart Energy Module
    SMART_ENERGY_MODULE = 0x00100000
    
    # Bits 21-31: Reserved


# =============================================================================
# Appliance Load Reduction Type (Table 28)
# =============================================================================

class ApplianceLoadReductionType(IntEnum):
    """
    Appliance Load Reduction Type.
    
    Reference: IEEE Std 2030.5-2023 Table 28
    
    Specifies the type of load reduction for appliances.
    """
    # 0: Delay Appliance Load (e.g., delay start of dishwasher)
    DELAY_APPLIANCE_LOAD = 0
    
    # 1: Temporary Appliance Load Reduction
    TEMPORARY_APPLIANCE_LOAD_REDUCTION = 1
    
    # 2: Reserved
    RESERVED_2 = 2
    
    # 3: Reserved
    RESERVED_3 = 3
    
    # 4: User Defined
    USER_DEFINED = 4


# =============================================================================
# Duty Cycle Type
# =============================================================================

@dataclass_json
@dataclass
class DutyCycleType:
    """
    Duty cycle information for load cycling.
    
    Specifies the normal and critical duty cycle percentages
    for cycling loads on/off.
    
    Attributes:
        normalValue: Normal duty cycle percentage (0-100)
        criticalValue: Critical duty cycle percentage (0-100)
    """
    normalValue: int = 100  # 100% = always on
    criticalValue: int = 0  # 0% = always off


# =============================================================================
# Set Point Type
# =============================================================================

@dataclass_json
@dataclass
class SetPointType:
    """
    Temperature set point for HVAC load control.
    
    Attributes:
        coolingSetpoint: Cooling temperature setpoint (°C or °F × 100)
        heatingSetpoint: Heating temperature setpoint (°C or °F × 100)
    """
    coolingSetpoint: Optional[int] = None
    heatingSetpoint: Optional[int] = None


# =============================================================================
# Offset Type
# =============================================================================

@dataclass_json
@dataclass
class OffsetType:
    """
    Temperature offset from current setpoint.
    
    Used for relative temperature adjustments during DR events.
    
    Attributes:
        coolingOffset: Offset to apply to cooling setpoint (°C or °F × 100)
        heatingOffset: Offset to apply to heating setpoint (°C or °F × 100)
        loadAdjustmentPercentageOffset: Load adjustment as percentage (0-100)
    """
    coolingOffset: Optional[int] = None
    heatingOffset: Optional[int] = None
    loadAdjustmentPercentageOffset: Optional[int] = None


# =============================================================================
# Target Reduction Type
# =============================================================================

@dataclass_json
@dataclass
class TargetReductionType:
    """
    Target reduction for demand response.
    
    Specifies the requested reduction amount as either
    an absolute value or percentage.
    
    Attributes:
        type_: Type of reduction (0=kWh, 1=kW, 2=%, 3=Watts, 4=Wh)
        value: Reduction value (interpretation depends on type_)
    """
    type_: int = 0  # 0=kWh
    value: int = 0


class TargetReductionTypeEnum(IntEnum):
    """Target reduction type values."""
    KWH = 0
    KW = 1
    PERCENT = 2
    WATTS = 3
    WH = 4


# =============================================================================
# Appliance Load Reduction
# =============================================================================

@dataclass_json
@dataclass
class ApplianceLoadReduction:
    """
    Appliance Load Reduction settings.
    
    Reference: IEEE Std 2030.5-2023
    
    Specifies load reduction behavior for smart appliances.
    
    Attributes:
        type_: Type of appliance load reduction
    """
    type_: ApplianceLoadReductionType = ApplianceLoadReductionType.TEMPORARY_APPLIANCE_LOAD_REDUCTION


# =============================================================================
# Load Shed Availability
# =============================================================================

@dataclass_json
@dataclass
class LoadShedAvailability:
    """
    Load Shed Availability for an EndDevice.
    
    Reference: IEEE Std 2030.5-2023
    
    Reports the device's capability to reduce load during DR events.
    
    Attributes:
        href: URI of this resource
        availabilityDuration: Time in seconds the device can shed load
        demandResponseLevel: DR level the device can participate in (0-15)
        sheddablePercent: Percentage of load that can be shed (0-100)
        sheddablePower: Power that can be shed (Watts)
    """
    href: Optional[str] = None
    availabilityDuration: Optional[int] = None
    demandResponseLevel: Optional[int] = None  # 0-15
    sheddablePercent: Optional[int] = None     # 0-100
    sheddablePower: Optional[int] = None       # Watts


@dataclass_json
@dataclass
class LoadShedAvailabilityList:
    """List of LoadShedAvailability resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    LoadShedAvailability: List[LoadShedAvailability] = field(default_factory=list)


# =============================================================================
# End Device Control (Load Control Event)
# =============================================================================

@dataclass_json
@dataclass
class EndDeviceControl:
    """
    End Device Control (Load Control Event).
    
    Reference: IEEE Std 2030.5-2023 Section 10.8
    
    Represents a demand response load control event that can be
    sent to end devices to request load reduction.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier (UInt128 as hex)
        description: Human-readable description
        version: Version number for tracking updates
        
        # Event timing
        creationTime: Time when event was created (POSIX seconds)
        interval: DateTimeInterval with start/duration
        EventStatus: Current status of the event
        
        # Target devices
        deviceCategory: Bitmap of targeted device categories
        
        # Load control parameters
        drProgramMandatory: If true, participation is mandatory
        loadShiftForward: If true, defer load to later time
        overrideDuration: Duration device can override event (seconds)
        
        # Temperature control
        setPoints: Target temperature setpoints
        offsets: Temperature offsets from current setpoints
        
        # Power/duty cycle control
        dutyCycle: Duty cycle for cycling loads
        targetReduction: Target power reduction
        
        # Appliance control
        ApplianceLoadReduction: Appliance-specific load reduction
        
        # Response settings
        randomizeDuration: Random delay range for response (seconds)
        randomizeStart: Random delay range for start (seconds)
        responseRequired: Bitmap of required responses
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Event timing
    creationTime: Optional[int] = None
    interval: Optional[dict] = None  # DateTimeInterval
    EventStatus: Optional[dict] = None
    
    # Target devices
    deviceCategory: DeviceCategoryType = DeviceCategoryType(0)
    
    # Control parameters
    drProgramMandatory: bool = False
    loadShiftForward: bool = False
    overrideDuration: Optional[int] = None
    
    # Temperature control
    setPoints: Optional[SetPointType] = None
    offsets: Optional[OffsetType] = None
    
    # Duty cycle control
    dutyCycle: Optional[DutyCycleType] = None
    
    # Target reduction
    targetReduction: Optional[TargetReductionType] = None
    
    # Appliance control
    ApplianceLoadReduction: Optional[ApplianceLoadReduction] = None
    
    # Randomization
    randomizeDuration: Optional[int] = None
    randomizeStart: Optional[int] = None
    
    # Response requirements
    responseRequired: Optional[int] = None  # HexBinary8
    
    # Reply-To URI for responses
    replyTo: Optional[str] = None
    
    def is_active(self, current_time: int) -> bool:
        """
        Check if the event is currently active.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            True if event is active
        """
        if not self.interval:
            return False
        
        start = self.interval.get("start", 0)
        duration = self.interval.get("duration", 0)
        
        return start <= current_time < (start + duration)
    
    def get_target_categories(self) -> List[str]:
        """Get list of targeted device category names."""
        categories = []
        for cat in DeviceCategoryType:
            if self.deviceCategory & cat:
                categories.append(cat.name)
        return categories


@dataclass_json
@dataclass
class EndDeviceControlList:
    """List of EndDeviceControl (load control event) resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    EndDeviceControl: List[EndDeviceControl] = field(default_factory=list)


# =============================================================================
# Demand Response Program
# =============================================================================

@dataclass_json
@dataclass
class DemandResponseProgram:
    """
    Demand Response Program container.
    
    Reference: IEEE Std 2030.5-2023 Section 10.8
    
    A DemandResponseProgram contains load control events and
    manages device enrollment for demand response.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier (UInt128 as hex)
        description: Human-readable description
        version: Version number for tracking updates
        
        primacy: Priority (lower = higher priority)
        
        # Links to related resources
        ActiveEndDeviceControlListLink: URI to active events
        EndDeviceControlListLink: URI to all events
        AvailabilityLink: URI to availability info
        
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Priority (lower = higher priority, 0-255)
    primacy: int = 255
    
    # Links to related resources
    ActiveEndDeviceControlListLink: Optional[dict] = None
    EndDeviceControlListLink: Optional[dict] = None
    AvailabilityLink: Optional[dict] = None
    
    def get_priority(self) -> int:
        """Get program priority (0 = highest)."""
        return self.primacy
    
    def is_higher_priority_than(self, other: "DemandResponseProgram") -> bool:
        """Check if this program has higher priority than another."""
        return self.primacy < other.primacy


@dataclass_json
@dataclass
class DemandResponseProgramList:
    """List of DemandResponseProgram resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    DemandResponseProgram: List[DemandResponseProgram] = field(default_factory=list)


# =============================================================================
# DR Event Response
# =============================================================================

class DREventResponseStatus(IntEnum):
    """
    Demand Response Event Response Status.
    
    Status codes for responding to load control events.
    """
    # 0: Event received
    EVENT_RECEIVED = 0
    
    # 1: Event started
    EVENT_STARTED = 1
    
    # 2: Event completed
    EVENT_COMPLETED = 2
    
    # 3: User opted out
    USER_OPTED_OUT = 3
    
    # 4: User opted out - no longer participating
    USER_OPTED_OUT_PERMANENT = 4
    
    # 5: Event superseded
    EVENT_SUPERSEDED = 5
    
    # 6: Event partially completed due to override
    EVENT_PARTIALLY_COMPLETED_OVERRIDE = 6
    
    # 7: Event partially completed due to timeout
    EVENT_PARTIALLY_COMPLETED_TIMEOUT = 7
    
    # 8: Event aborted due to server command
    EVENT_ABORTED_SERVER = 8
    
    # 9: Event aborted due to local override
    EVENT_ABORTED_LOCAL = 9
    
    # 10-199: Reserved
    # 200-255: Manufacturer specific


@dataclass_json
@dataclass
class DrEventResponse:
    """
    Demand Response Event Response.
    
    Sent by the client to indicate the status of event participation.
    """
    href: Optional[str] = None
    createdDateTime: Optional[int] = None
    endDeviceLFDI: Optional[str] = None
    status: DREventResponseStatus = DREventResponseStatus.EVENT_RECEIVED
    subject: Optional[str] = None  # URI of the event being responded to
    
    # Optional load shed info
    appliedTargetReduction: Optional[TargetReductionType] = None


@dataclass_json
@dataclass
class DrEventResponseList:
    """List of DrEventResponse resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    DrEventResponse: List[DrEventResponse] = field(default_factory=list)


# =============================================================================
# Helper Functions
# =============================================================================

def device_category_to_names(bitmap: int) -> List[str]:
    """
    Convert DeviceCategoryType bitmap to list of category names.
    
    Args:
        bitmap: DeviceCategoryType bitmap value
        
    Returns:
        List of category name strings
    """
    names = []
    for cat in DeviceCategoryType:
        if bitmap & cat:
            names.append(cat.name)
    return names


def create_load_control_event(
    mRID: str,
    start_time: int,
    duration: int,
    device_categories: DeviceCategoryType,
    target_reduction_percent: Optional[int] = None,
    cooling_offset: Optional[int] = None,
    heating_offset: Optional[int] = None,
    duty_cycle: Optional[int] = None,
    description: str = "Load Control Event",
    mandatory: bool = False
) -> EndDeviceControl:
    """
    Create a load control event with common parameters.
    
    Args:
        mRID: Unique identifier for the event
        start_time: Event start time (POSIX seconds)
        duration: Event duration (seconds)
        device_categories: Target device categories
        target_reduction_percent: Target reduction as percentage
        cooling_offset: Cooling setpoint offset (×100)
        heating_offset: Heating setpoint offset (×100)
        duty_cycle: Duty cycle percentage for cycling
        description: Human-readable description
        mandatory: Whether participation is mandatory
        
    Returns:
        Configured EndDeviceControl event
    """
    event = EndDeviceControl(
        mRID=mRID,
        description=description,
        deviceCategory=device_categories,
        drProgramMandatory=mandatory,
        interval={
            "start": start_time,
            "duration": duration,
        },
    )
    
    if target_reduction_percent is not None:
        event.targetReduction = TargetReductionType(
            type_=TargetReductionTypeEnum.PERCENT,
            value=target_reduction_percent
        )
    
    if cooling_offset is not None or heating_offset is not None:
        event.offsets = OffsetType(
            coolingOffset=cooling_offset,
            heatingOffset=heating_offset
        )
    
    if duty_cycle is not None:
        event.dutyCycle = DutyCycleType(normalValue=duty_cycle)
    
    return event


def create_thermostat_event(
    mRID: str,
    start_time: int,
    duration: int,
    cooling_setpoint: int,
    heating_setpoint: int,
    description: str = "Thermostat Control Event"
) -> EndDeviceControl:
    """
    Create a thermostat control event.
    
    Args:
        mRID: Unique identifier for the event
        start_time: Event start time (POSIX seconds)
        duration: Event duration (seconds)
        cooling_setpoint: Target cooling setpoint (×100)
        heating_setpoint: Target heating setpoint (×100)
        description: Human-readable description
        
    Returns:
        Configured EndDeviceControl for thermostat
    """
    return EndDeviceControl(
        mRID=mRID,
        description=description,
        deviceCategory=DeviceCategoryType.PROGRAMMABLE_COMMUNICATING_THERMOSTAT,
        interval={
            "start": start_time,
            "duration": duration,
        },
        setPoints=SetPointType(
            coolingSetpoint=cooling_setpoint,
            heatingSetpoint=heating_setpoint
        ),
    )


def create_ev_charging_event(
    mRID: str,
    start_time: int,
    duration: int,
    target_reduction_watts: int,
    description: str = "EV Charging Control Event"
) -> EndDeviceControl:
    """
    Create an EV charging control event.
    
    Args:
        mRID: Unique identifier for the event
        start_time: Event start time (POSIX seconds)
        duration: Event duration (seconds)
        target_reduction_watts: Target power reduction in Watts
        description: Human-readable description
        
    Returns:
        Configured EndDeviceControl for EV/EVSE
    """
    return EndDeviceControl(
        mRID=mRID,
        description=description,
        deviceCategory=DeviceCategoryType.ELECTRIC_VEHICLE | DeviceCategoryType.EVSE,
        interval={
            "start": start_time,
            "duration": duration,
        },
        targetReduction=TargetReductionType(
            type_=TargetReductionTypeEnum.WATTS,
            value=target_reduction_watts
        ),
    )
