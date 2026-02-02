"""
DER Availability (dera) module.

Handles DER availability reporting, conversion, and power control.
"""

from bms_2030_5_client.dera.adapter import DERAvailabilityAdapter
from bms_2030_5_client.dera.client import DERAvailabilityClient
from bms_2030_5_client.dera.handler import (
    DERControlHandler,
    DERControlHandlerConfig,
    DERControlEvent,
    DERControlEventStatus,
    parse_der_control_from_xml,
    parse_der_control_list_from_xml,
)

__all__ = [
    "DERAvailabilityAdapter",
    "DERAvailabilityClient",
    # DER Control Handler
    "DERControlHandler",
    "DERControlHandlerConfig",
    "DERControlEvent",
    "DERControlEventStatus",
    "parse_der_control_from_xml",
    "parse_der_control_list_from_xml",
