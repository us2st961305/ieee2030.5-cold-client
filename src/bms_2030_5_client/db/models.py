"""
SQLite database record models for IEEE 2030.5 resources.

These dataclasses map to SQLite tables and provide type-safe
access to stored IEEE 2030.5 resource data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import json


@dataclass
class DeviceCapabilityRecord:
    """DeviceCapability database record."""
    id: Optional[int] = None
    server_url: str = ""
    href: str = "/dcap"
    poll_rate: int = 900
    end_device_list_link: Optional[str] = None
    mirror_usage_point_list_link: Optional[str] = None
    self_device_link: Optional[str] = None
    time_link: Optional[str] = None
    der_program_list_link: Optional[str] = None
    response_set_list_link: Optional[str] = None
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "server_url": self.server_url,
            "href": self.href,
            "poll_rate": self.poll_rate,
            "end_device_list_link": self.end_device_list_link,
            "mirror_usage_point_list_link": self.mirror_usage_point_list_link,
            "self_device_link": self.self_device_link,
            "time_link": self.time_link,
            "der_program_list_link": self.der_program_list_link,
            "response_set_list_link": self.response_set_list_link,
        }


@dataclass
class EndDeviceRecord:
    """EndDevice database record."""
    id: Optional[int] = None
    href: str = ""
    lfdi: Optional[str] = None  # 40 hex chars
    sfdi: Optional[int] = None
    changed_time: int = 0
    enabled: bool = True
    
    # Sub-resource links
    der_list_link: Optional[str] = None
    device_information_link: Optional[str] = None
    fsa_list_link: Optional[str] = None
    registration_link: Optional[str] = None
    power_status_link: Optional[str] = None
    device_status_link: Optional[str] = None
    log_event_list_link: Optional[str] = None
    subscription_list_link: Optional[str] = None
    response_set_list_link: Optional[str] = None
    
    # Device Information
    mf_id: Optional[int] = None
    mf_model: Optional[str] = None
    mf_serial_number: Optional[str] = None
    mf_hw_ver: Optional[str] = None
    sw_ver: Optional[str] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "href": self.href,
            "lfdi": self.lfdi,
            "sfdi": self.sfdi,
            "changed_time": self.changed_time,
            "enabled": self.enabled,
            "der_list_link": self.der_list_link,
            "device_information_link": self.device_information_link,
            "fsa_list_link": self.fsa_list_link,
            "mf_model": self.mf_model,
            "sw_ver": self.sw_ver,
        }


@dataclass
class DERRecord:
    """DER database record."""
    id: Optional[int] = None
    href: str = ""
    mrid: Optional[str] = None  # HexBinary128
    description: Optional[str] = None
    version: Optional[int] = None
    
    # Parent reference
    end_device_href: Optional[str] = None
    
    # Sub-resource links
    der_capability_link: Optional[str] = None
    der_settings_link: Optional[str] = None
    der_status_link: Optional[str] = None
    der_availability_link: Optional[str] = None
    associated_der_program_list_link: Optional[str] = None
    current_der_program_link: Optional[str] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "href": self.href,
            "mrid": self.mrid,
            "description": self.description,
            "end_device_href": self.end_device_href,
            "der_capability_link": self.der_capability_link,
            "der_status_link": self.der_status_link,
        }


@dataclass
class DERStatusRecord:
    """DERStatus database record."""
    id: Optional[int] = None
    der_href: str = ""
    href: Optional[str] = None
    reading_time: int = 0
    
    # Status values
    alarm_status: Optional[str] = None  # HexBinary32
    gen_connect_status: Optional[str] = None
    inverter_status: Optional[str] = None
    operational_mode_status: Optional[str] = None
    state_of_charge: Optional[int] = None  # 0-10000 (0.00%-100.00%)
    state_of_charge_time: Optional[int] = None
    stor_mode_status: Optional[str] = None
    stor_connect_status: Optional[str] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "der_href": self.der_href,
            "reading_time": self.reading_time,
            "state_of_charge": self.state_of_charge,
            "operational_mode_status": self.operational_mode_status,
            "alarm_status": self.alarm_status,
        }


@dataclass
class DERCapabilityRecord:
    """DERCapability database record."""
    id: Optional[int] = None
    der_href: str = ""
    href: Optional[str] = None
    
    modes_supported: int = 0
    der_type: int = 7  # Battery Storage
    
    # Ratings
    rtg_max_w: Optional[int] = None
    rtg_max_w_multiplier: int = 0
    rtg_max_var: Optional[int] = None
    rtg_max_charge_rate_w: Optional[int] = None
    rtg_max_discharge_rate_w: Optional[int] = None
    rtg_max_charge_rate_va: Optional[int] = None
    rtg_max_discharge_rate_va: Optional[int] = None
    rtg_ah: Optional[int] = None
    rtg_wh: Optional[int] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "der_href": self.der_href,
            "modes_supported": self.modes_supported,
            "der_type": self.der_type,
            "rtg_max_w": self.rtg_max_w,
            "rtg_max_charge_rate_w": self.rtg_max_charge_rate_w,
            "rtg_max_discharge_rate_w": self.rtg_max_discharge_rate_w,
        }


@dataclass
class DERSettingsRecord:
    """DERSettings database record."""
    id: Optional[int] = None
    der_href: str = ""
    href: Optional[str] = None
    updated_time: Optional[int] = None
    
    set_grad_w: Optional[int] = None
    set_max_w: Optional[int] = None
    set_max_w_multiplier: int = 0
    set_max_var: Optional[int] = None
    set_max_charge_rate_w: Optional[int] = None
    set_max_discharge_rate_w: Optional[int] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DERAvailabilityRecord:
    """DERAvailability database record."""
    id: Optional[int] = None
    der_href: str = ""
    href: Optional[str] = None
    reading_time: int = 0
    
    availability_duration: Optional[int] = None
    max_charge_duration: Optional[int] = None
    reserve_charge_percent: Optional[int] = None
    reserve_percent: Optional[int] = None
    stat_w_avail: Optional[int] = None
    stat_var_avail: Optional[int] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class MirrorUsagePointRecord:
    """MirrorUsagePoint database record."""
    id: Optional[int] = None
    href: str = ""
    mrid: Optional[str] = None  # HexBinary128
    description: Optional[str] = None
    version: Optional[int] = None
    
    role_flags: str = "0009"  # IS_MIRROR | IS_DER
    service_category_kind: int = 0  # Electricity
    status: int = 1  # On
    device_lfdi: Optional[str] = None
    post_rate: int = 900
    
    # Meter configuration
    meter_name: Optional[str] = None
    meter_type: Optional[str] = None  # power, energy, soc, temperature, etc.
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "href": self.href,
            "mrid": self.mrid,
            "description": self.description,
            "meter_name": self.meter_name,
            "meter_type": self.meter_type,
            "device_lfdi": self.device_lfdi,
            "post_rate": self.post_rate,
            "status": self.status,
        }


@dataclass
class MirrorMeterReadingRecord:
    """MirrorMeterReading database record."""
    id: Optional[int] = None
    mup_href: str = ""  # Parent MirrorUsagePoint
    href: Optional[str] = None
    mrid: Optional[str] = None
    description: Optional[str] = None
    
    # Reading type configuration
    reading_type_href: Optional[str] = None
    accumulation_behaviour: int = 0
    commodity: int = 1  # Electricity
    data_qualifier: int = 0
    flow_direction: int = 0
    kind: int = 0
    phase: Optional[int] = None
    power_of_ten_multiplier: int = 0
    uom: int = 0
    
    # Current reading
    last_value: Optional[int] = None
    last_reading_time: Optional[int] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mup_href": self.mup_href,
            "href": self.href,
            "description": self.description,
            "kind": self.kind,
            "uom": self.uom,
            "last_value": self.last_value,
            "last_reading_time": self.last_reading_time,
        }


@dataclass
class FSARecord:
    """FunctionSetAssignments database record."""
    id: Optional[int] = None
    href: str = ""
    mrid: Optional[str] = None
    description: Optional[str] = None
    
    # Parent reference
    end_device_href: Optional[str] = None
    
    # Sub-resource links
    der_program_list_link: Optional[str] = None
    time_link: Optional[str] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "href": self.href,
            "description": self.description,
            "der_program_list_link": self.der_program_list_link,
        }


@dataclass
class DERProgramRecord:
    """DERProgram database record."""
    id: Optional[int] = None
    href: str = ""
    mrid: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    
    # Parent reference
    fsa_href: Optional[str] = None
    
    primacy: int = 0
    
    # Sub-resource links
    der_control_list_link: Optional[str] = None
    active_der_control_list_link: Optional[str] = None
    default_der_control_link: Optional[str] = None
    
    raw_xml: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "href": self.href,
            "description": self.description,
            "primacy": self.primacy,
            "der_control_list_link": self.der_control_list_link,
            "default_der_control_link": self.default_der_control_link,
        }


@dataclass
class SubscriptionRecord:
    """Subscription database record."""
    id: Optional[int] = None
    href: str = ""
    
    subscribed_resource: str = ""
    notification_uri: str = ""
    encoding: int = 0  # XML
    level: str = "+S2"
    limit: int = 10
    
    # State
    state: str = "disabled"  # disabled, pending, active, failed
    
    # Timing
    created_at: Optional[datetime] = None
    last_renewed_at: Optional[datetime] = None
    next_renewal_at: Optional[datetime] = None
    
    renewal_count: int = 0
    failure_count: int = 0
    last_error: Optional[str] = None
    
    raw_xml: Optional[str] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "href": self.href,
            "subscribed_resource": self.subscribed_resource,
            "notification_uri": self.notification_uri,
            "state": self.state,
            "renewal_count": self.renewal_count,
        }


@dataclass
class UoMRecord:
    """
    IEEE 2030.5 Unit of Measure (UoM) reference table record.
    
    Stores all standard UoM codes and their descriptions
    per IEEE 2030.5 specification.
    """
    code: int  # UoM code (primary key)
    symbol: str = ""  # Unit symbol (e.g., "W", "A", "V")
    name: str = ""  # Full name (e.g., "Watts", "Amperes", "Volts")
    description: str = ""  # Description in Chinese/English
    category: str = ""  # Category (Power, Energy, Current, etc.)
    
    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "symbol": self.symbol,
            "name": self.name,
            "description": self.description,
            "category": self.category,
        }


@dataclass
class MeterTypeRecord:
    """
    Record of configured meter reading types.
    
    Stores the meter types (descriptions) that are being uploaded,
    without storing the actual values. This allows tracking which
    meters have been registered for a MirrorUsagePoint.
    
    Example meter types:
    - Battery Total Current
    - Battery Total Power
    - Battery Charge Energy
    - Battery Discharge Energy
    - Battery Max Temperature
    - Battery Min Temperature
    - Battery Avg Temperature
    - Battery SOH
    - Battery Cycle Count
    - BMS Timestamp
    """
    id: Optional[int] = None
    mup_href: str = ""  # Parent MirrorUsagePoint href
    description: str = ""  # Meter description/name
    mrid: Optional[str] = None  # HexBinary128 mRID (32 hex chars)
    uom_code: int = 0  # Unit of measure code (FK to uom table)
    kind: int = 0  # Reading kind
    commodity: int = 1  # Default: Electricity
    flow_direction: int = 0  # 0=NA, 1=Forward, 19=Reverse
    accumulation_behaviour: int = 0  # 0=NA, 3=Cumulative, 12=Instantaneous
    power_of_ten_multiplier: int = 0  # Multiplier for value scaling
    is_active: bool = True  # Whether this meter type is currently active
    
    # Joined from uom table
    uom_symbol: Optional[str] = None
    uom_name: Optional[str] = None
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        # Handle created_at/updated_at which may be string or datetime
        created_at_str = None
        if self.created_at:
            if isinstance(self.created_at, str):
                created_at_str = self.created_at
            else:
                created_at_str = self.created_at.isoformat()
        
        updated_at_str = None
        if self.updated_at:
            if isinstance(self.updated_at, str):
                updated_at_str = self.updated_at
            else:
                updated_at_str = self.updated_at.isoformat()
        
        return {
            "id": self.id,
            "mup_href": self.mup_href,
            "description": self.description,
            "mrid": self.mrid,
            "uom_code": self.uom_code,
            "uom_symbol": self.uom_symbol,
            "uom_name": self.uom_name,
            "kind": self.kind,
            "commodity": self.commodity,
            "flow_direction": self.flow_direction,
            "accumulation_behaviour": self.accumulation_behaviour,
            "power_of_ten_multiplier": self.power_of_ten_multiplier,
            "is_active": self.is_active,
            "created_at": created_at_str,
            "updated_at": updated_at_str,
        }
