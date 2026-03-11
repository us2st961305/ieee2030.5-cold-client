"""
SQLite database module for IEEE 2030.5 resources.

Provides persistent storage for:
- DeviceCapability
- EndDevice
- DER (Distributed Energy Resources)
- DERStatus, DERCapability, DERSettings, DERAvailability
- MirrorUsagePoint
- MirrorMeterReading
- FunctionSetAssignments
- DERProgram, DERControl
- Subscription

Usage:
    from bms_2030_5_client.db import get_database, init_database
    
    # Initialize database
    db = init_database("data/ieee2030_5.db")
    
    # Or get singleton instance
    db = get_database()
    
    # Quick path lookup
    edev = db.get_end_device_by_href("/edev/1")
"""

from bms_2030_5_client.db.database import (
    IEEE2030_5Database,
    get_database,
    init_database,
)
from bms_2030_5_client.db.models import (
    DeviceCapabilityRecord,
    EndDeviceRecord,
    DERRecord,
    DERStatusRecord,
    DERCapabilityRecord,
    DERSettingsRecord,
    DERAvailabilityRecord,
    MirrorUsagePointRecord,
    MirrorMeterReadingRecord,
    FSARecord,
    DERProgramRecord,
    SubscriptionRecord,
    MeterTypeRecord,
    UoMRecord,
)
from bms_2030_5_client.db.client_wrapper import DatabaseIEEE2030_5Client

__all__ = [
    "IEEE2030_5Database",
    "get_database",
    "init_database",
    "DatabaseIEEE2030_5Client",
    "DeviceCapabilityRecord",
    "EndDeviceRecord",
    "DERRecord",
    "DERStatusRecord",
    "DERCapabilityRecord",
    "DERSettingsRecord",
    "DERAvailabilityRecord",
    "MirrorUsagePointRecord",
    "MirrorMeterReadingRecord",
    "FSARecord",
    "DERProgramRecord",
    "SubscriptionRecord",
    "MeterTypeRecord",
    "UoMRecord",
]
