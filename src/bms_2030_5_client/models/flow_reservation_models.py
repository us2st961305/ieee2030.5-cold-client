"""
IEEE 2030.5-2023 Flow Reservation Function Set.

This module provides the complete Flow Reservation implementation including:
- FlowReservationRequest: Client request for power flow
- FlowReservationResponse: Server response with allocated flow
- FlowReservationResponseResponse: Client acknowledgment

Reference: IEEE Std 2030.5-2023
- Section 10.7: Flow Reservation Function Set
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List
from dataclasses_json import dataclass_json


# =============================================================================
# Flow Reservation Status
# =============================================================================

class FlowReservationStatusType(IntEnum):
    """
    Flow Reservation status enumeration.
    
    Indicates the status of a flow reservation request or response.
    """
    # 0: Request pending - awaiting server response
    PENDING = 0
    
    # 1: Request accepted - flow reserved
    ACCEPTED = 1
    
    # 2: Request rejected - flow not available
    REJECTED = 2
    
    # 3: Request cancelled by client
    CANCELLED = 3
    
    # 4: Reservation expired
    EXPIRED = 4
    
    # 5: Reservation in progress (active)
    IN_PROGRESS = 5
    
    # 6: Reservation completed successfully
    COMPLETED = 6
    
    # 7: Reservation failed/aborted
    FAILED = 7


# =============================================================================
# Power Sign Types
# =============================================================================

class EnergyFlowDirection(IntEnum):
    """
    Energy flow direction for reservation requests.
    """
    # 0: Import (consume/charge) - from grid to device
    IMPORT = 0
    
    # 1: Export (generate/discharge) - from device to grid
    EXPORT = 1
    
    # 2: Bidirectional - both import and export
    BIDIRECTIONAL = 2


# =============================================================================
# Signed Real Energy Type
# =============================================================================

@dataclass_json
@dataclass
class SignedRealEnergy:
    """
    Signed real energy value in Watt-hours.
    
    value × 10^multiplier = Wh
    Positive = Export/Inject, Negative = Import/Absorb
    """
    value: int = 0
    multiplier: int = 0
    
    def to_wh(self) -> int:
        """Convert to Watt-hours."""
        return int(self.value * (10 ** self.multiplier))
    
    def to_kwh(self) -> float:
        """Convert to kilowatt-hours."""
        return self.to_wh() / 1000.0
    
    @classmethod
    def from_wh(cls, wh: int) -> "SignedRealEnergy":
        """Create from Watt-hours."""
        if abs(wh) >= 1000000:
            return cls(value=wh // 1000000, multiplier=6)
        elif abs(wh) >= 1000:
            return cls(value=wh // 1000, multiplier=3)
        return cls(value=wh, multiplier=0)
    
    @classmethod
    def from_kwh(cls, kwh: float) -> "SignedRealEnergy":
        """Create from kilowatt-hours."""
        return cls.from_wh(int(kwh * 1000))


# =============================================================================
# Active Power Type (for requests)
# =============================================================================

@dataclass_json
@dataclass
class RequestedActivePower:
    """
    Requested active power for flow reservation.
    
    value × 10^multiplier = Watts
    Positive = Export, Negative = Import
    """
    value: int = 0
    multiplier: int = 0
    
    def to_watts(self) -> int:
        """Convert to Watts."""
        return int(self.value * (10 ** self.multiplier))
    
    def to_kw(self) -> float:
        """Convert to kilowatts."""
        return self.to_watts() / 1000.0
    
    @classmethod
    def from_watts(cls, watts: int) -> "RequestedActivePower":
        """Create from Watts."""
        if abs(watts) >= 1000000:
            return cls(value=watts // 1000000, multiplier=6)
        elif abs(watts) >= 1000:
            return cls(value=watts // 1000, multiplier=3)
        return cls(value=watts, multiplier=0)
    
    @classmethod
    def from_kw(cls, kw: float) -> "RequestedActivePower":
        """Create from kilowatts."""
        return cls.from_watts(int(kw * 1000))


# =============================================================================
# Flow Reservation Request
# =============================================================================

@dataclass_json
@dataclass
class FlowReservationRequest:
    """
    Flow Reservation Request.
    
    Reference: IEEE Std 2030.5-2023 Section 10.7
    
    A request from a client (e.g., EV) to reserve power flow
    at a specific time and for a specific duration/amount.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier (UInt128 as hex)
        description: Human-readable description
        version: Version number for tracking updates
        
        # Request timing
        creationTime: When the request was created (POSIX seconds)
        interval: DateTimeInterval with desired start/duration
        
        # Power/energy request
        energyRequested: Total energy requested (Wh)
        powerRequested: Peak power requested (W)
        
        # Duration limits
        durationRequested: Requested duration in seconds
        
        # Request status
        RequestStatus: Current status of the request
        
        # Reply URI
        replyTo: URI for server to send response
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    
    # Timing
    creationTime: Optional[int] = None
    interval: Optional[dict] = None  # DateTimeInterval
    
    # Power/energy request (signed - positive=export, negative=import)
    energyRequested: Optional[SignedRealEnergy] = None
    powerRequested: Optional[RequestedActivePower] = None
    
    # Duration
    durationRequested: Optional[int] = None  # seconds
    
    # Request status
    RequestStatus: Optional[dict] = None
    
    # Reply-To URI
    replyTo: Optional[str] = None
    
    def get_requested_energy_kwh(self) -> float:
        """Get requested energy in kWh."""
        if self.energyRequested is None:
            return 0.0
        return self.energyRequested.to_kwh()
    
    def get_requested_power_kw(self) -> float:
        """Get requested power in kW."""
        if self.powerRequested is None:
            return 0.0
        return self.powerRequested.to_kw()
    
    def is_import_request(self) -> bool:
        """Check if this is an import (charge) request."""
        if self.powerRequested is None:
            return False
        return self.powerRequested.to_watts() < 0
    
    def is_export_request(self) -> bool:
        """Check if this is an export (discharge) request."""
        if self.powerRequested is None:
            return False
        return self.powerRequested.to_watts() > 0


@dataclass_json
@dataclass
class FlowReservationRequestList:
    """List of FlowReservationRequest resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    FlowReservationRequest: List[FlowReservationRequest] = field(default_factory=list)


# =============================================================================
# Flow Reservation Response
# =============================================================================

@dataclass_json
@dataclass
class FlowReservationResponse:
    """
    Flow Reservation Response from server.
    
    Reference: IEEE Std 2030.5-2023 Section 10.7
    
    Server's response to a FlowReservationRequest, indicating
    the allocated power/energy and timing.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier (UInt128 as hex)
        description: Human-readable description
        version: Version number for tracking updates
        
        # Response to specific request
        subject: URI of the FlowReservationRequest
        
        # Allocated timing
        interval: DateTimeInterval with actual start/duration
        
        # Allocated power/energy
        energyAvailable: Energy allocated (Wh)
        powerAvailable: Power allocated (W)
        
        # Event status
        EventStatus: Current status of the response
        
        # Response requirements
        responseRequired: Whether client must acknowledge
        replyTo: URI for client acknowledgment
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Reference to original request
    subject: Optional[str] = None
    
    # Timing
    creationTime: Optional[int] = None
    interval: Optional[dict] = None  # DateTimeInterval
    
    # Allocated power/energy (signed)
    energyAvailable: Optional[SignedRealEnergy] = None
    powerAvailable: Optional[RequestedActivePower] = None
    
    # Event status
    EventStatus: Optional[dict] = None
    
    # Response settings
    responseRequired: Optional[int] = None
    replyTo: Optional[str] = None
    
    def get_available_energy_kwh(self) -> float:
        """Get available energy in kWh."""
        if self.energyAvailable is None:
            return 0.0
        return self.energyAvailable.to_kwh()
    
    def get_available_power_kw(self) -> float:
        """Get available power in kW."""
        if self.powerAvailable is None:
            return 0.0
        return self.powerAvailable.to_kw()
    
    def is_active(self, current_time: int) -> bool:
        """
        Check if the reservation is currently active.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            True if reservation is active
        """
        if not self.interval:
            return False
        
        start = self.interval.get("start", 0)
        duration = self.interval.get("duration", 0)
        
        return start <= current_time < (start + duration)
    
    def is_expired(self, current_time: int) -> bool:
        """
        Check if the reservation has expired.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            True if reservation has expired
        """
        if not self.interval:
            return False
        
        start = self.interval.get("start", 0)
        duration = self.interval.get("duration", 0)
        
        return current_time >= (start + duration)
    
    def get_start_time(self) -> Optional[int]:
        """Get reservation start time."""
        if self.interval:
            return self.interval.get("start")
        return None
    
    def get_end_time(self) -> Optional[int]:
        """Get reservation end time."""
        if self.interval:
            start = self.interval.get("start", 0)
            duration = self.interval.get("duration", 0)
            return start + duration
        return None


@dataclass_json
@dataclass
class FlowReservationResponseList:
    """List of FlowReservationResponse resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    FlowReservationResponse: List[FlowReservationResponse] = field(default_factory=list)
    
    def get_active_reservations(self, current_time: int) -> List[FlowReservationResponse]:
        """Get all currently active reservations."""
        return [r for r in self.FlowReservationResponse if r.is_active(current_time)]
    
    def get_upcoming_reservations(self, current_time: int) -> List[FlowReservationResponse]:
        """Get upcoming (future) reservations."""
        result = []
        for r in self.FlowReservationResponse:
            start = r.get_start_time()
            if start and start > current_time and not r.is_expired(current_time):
                result.append(r)
        return result


# =============================================================================
# Flow Reservation Response Response (Client Acknowledgment)
# =============================================================================

class FlowReservationAckStatus(IntEnum):
    """
    Acknowledgment status for flow reservation responses.
    """
    # 0: Reservation accepted
    ACCEPTED = 0
    
    # 1: Reservation started
    STARTED = 1
    
    # 2: Reservation completed
    COMPLETED = 2
    
    # 3: Reservation rejected by client
    REJECTED = 3
    
    # 4: Reservation aborted by client
    ABORTED = 4
    
    # 5: Partial utilization
    PARTIAL = 5


@dataclass_json
@dataclass
class FlowReservationResponseResponse:
    """
    Client acknowledgment for a FlowReservationResponse.
    
    Sent by the client to acknowledge receipt or completion
    of a flow reservation.
    """
    href: Optional[str] = None
    createdDateTime: Optional[int] = None
    endDeviceLFDI: Optional[str] = None
    status: FlowReservationAckStatus = FlowReservationAckStatus.ACCEPTED
    subject: Optional[str] = None  # URI of the FlowReservationResponse
    
    # Actual utilization (optional)
    energyUsed: Optional[SignedRealEnergy] = None
    peakPowerUsed: Optional[RequestedActivePower] = None


@dataclass_json
@dataclass
class FlowReservationResponseResponseList:
    """List of FlowReservationResponseResponse resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    FlowReservationResponseResponse: List[FlowReservationResponseResponse] = field(default_factory=list)


# =============================================================================
# Helper Functions
# =============================================================================

def create_charging_request(
    mRID: str,
    energy_kwh: float,
    power_kw: float,
    start_time: int,
    duration_seconds: int,
    description: str = "EV Charging Request"
) -> FlowReservationRequest:
    """
    Create an EV charging (import) flow reservation request.
    
    Args:
        mRID: Unique identifier for the request
        energy_kwh: Energy requested in kWh (positive for charging)
        power_kw: Maximum charging power in kW
        start_time: Desired start time (POSIX seconds)
        duration_seconds: Duration in seconds
        description: Human-readable description
        
    Returns:
        Configured FlowReservationRequest for charging
    """
    # Note: Import (charge) uses negative values per IEEE 2030.5 convention
    return FlowReservationRequest(
        mRID=mRID,
        description=description,
        interval={
            "start": start_time,
            "duration": duration_seconds,
        },
        energyRequested=SignedRealEnergy.from_kwh(-abs(energy_kwh)),
        powerRequested=RequestedActivePower.from_kw(-abs(power_kw)),
        durationRequested=duration_seconds,
    )


def create_discharging_request(
    mRID: str,
    energy_kwh: float,
    power_kw: float,
    start_time: int,
    duration_seconds: int,
    description: str = "V2G Discharge Request"
) -> FlowReservationRequest:
    """
    Create a V2G discharging (export) flow reservation request.
    
    Args:
        mRID: Unique identifier for the request
        energy_kwh: Energy to export in kWh
        power_kw: Maximum discharge power in kW
        start_time: Desired start time (POSIX seconds)
        duration_seconds: Duration in seconds
        description: Human-readable description
        
    Returns:
        Configured FlowReservationRequest for discharging
    """
    # Note: Export (discharge) uses positive values
    return FlowReservationRequest(
        mRID=mRID,
        description=description,
        interval={
            "start": start_time,
            "duration": duration_seconds,
        },
        energyRequested=SignedRealEnergy.from_kwh(abs(energy_kwh)),
        powerRequested=RequestedActivePower.from_kw(abs(power_kw)),
        durationRequested=duration_seconds,
    )


def create_reservation_response(
    mRID: str,
    request_uri: str,
    energy_kwh: float,
    power_kw: float,
    start_time: int,
    duration_seconds: int,
    description: str = "Flow Reservation"
) -> FlowReservationResponse:
    """
    Create a flow reservation response.
    
    Args:
        mRID: Unique identifier for the response
        request_uri: URI of the original request
        energy_kwh: Energy allocated in kWh (signed)
        power_kw: Power allocated in kW (signed)
        start_time: Reservation start time (POSIX seconds)
        duration_seconds: Duration in seconds
        description: Human-readable description
        
    Returns:
        Configured FlowReservationResponse
    """
    return FlowReservationResponse(
        mRID=mRID,
        description=description,
        subject=request_uri,
        interval={
            "start": start_time,
            "duration": duration_seconds,
        },
        energyAvailable=SignedRealEnergy.from_kwh(energy_kwh),
        powerAvailable=RequestedActivePower.from_kw(power_kw),
    )


def calculate_required_charging_time(
    energy_kwh: float,
    power_kw: float,
    efficiency: float = 0.90
) -> int:
    """
    Calculate required charging time in seconds.
    
    Args:
        energy_kwh: Energy needed in kWh
        power_kw: Available charging power in kW
        efficiency: Charging efficiency (0.0 to 1.0)
        
    Returns:
        Required time in seconds
    """
    if power_kw <= 0:
        return 0
    
    effective_power = power_kw * efficiency
    hours_needed = energy_kwh / effective_power
    return int(hours_needed * 3600)
