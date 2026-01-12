# DER Status (ders) Module

This module handles DER (Distributed Energy Resource) Status reporting for IEEE 2030.5.

## Components

### `DERStatusAdapter`
Converts BMS snapshots to `DERStatus` objects compliant with IEEE 2030.5 standards.

**Key Features:**
- Converts battery system state to DER connection status
- Maps operational modes (charging, discharging, standby)
- Handles fault detection and reporting
- Provides State of Charge (SOC) status

**Usage:**
```python
from bms_2030_5_client.ders import DERStatusAdapter

adapter = DERStatusAdapter()
der_status = adapter.snapshot_to_der_status(bms_snapshot, href="/edev/1/der/1/ders")
```

### `DERStatusClient`
Handles communication with the IEEE 2030.5 server for status updates.

**Key Features:**
- Updates DER status on the server via PUT requests
- Handles error conditions gracefully

**Usage:**
```python
from bms_2030_5_client.ders import DERStatusClient

client = DERStatusClient(ieee_client)
success = await client.update_status("/edev/1/der/1", der_status)
```

## Integration

This module is integrated into `BMSAdapter` for backward compatibility:

```python
from bms_2030_5_client.adapters import BMSAdapter

adapter = BMSAdapter()
# Automatically uses DERStatusAdapter internally
der_status = adapter.snapshot_to_der_status(snapshot)
```

## IEEE 2030.5 Compliance

- Implements `DERStatus` resource as per IEEE 2030.5-2023
- Follows URI path convention: `/edev/{id}/der/{id}/ders`
- Supports connection status flags (CONNECTED, AVAILABLE, OPERATING, FAULT)
- Complies with operational mode status types
