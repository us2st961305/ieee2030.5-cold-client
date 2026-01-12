# DER Availability (dera) Module

This module handles DER (Distributed Energy Resource) Availability reporting for IEEE 2030.5.

## Components

### `DERAvailabilityAdapter`
Converts BMS snapshots to `DERAvailability` objects showing available power capacity.

**Key Features:**
- Calculates available discharge power based on SOC
- Calculates available charge power based on remaining capacity
- Considers rack current limits and voltage constraints
- Provides reserve charge percentage

**Usage:**
```python
from bms_2030_5_client.dera import DERAvailabilityAdapter

adapter = DERAvailabilityAdapter(max_power=100000.0)  # 100 kW
availability = adapter.snapshot_to_der_availability(bms_snapshot, href="/edev/1/der/1/dera")
```

### `DERAvailabilityClient`
Handles communication with the IEEE 2030.5 server for availability updates.

**Key Features:**
- Updates DER availability on the server via PUT requests
- Manages availability resource lifecycle

**Usage:**
```python
from bms_2030_5_client.dera import DERAvailabilityClient

client = DERAvailabilityClient(ieee_client)
success = await client.update_availability("/edev/1/der/1", availability)
```

## Integration

This module is integrated into `BMSAdapter` for backward compatibility:

```python
from bms_2030_5_client.adapters import BMSAdapter

adapter = BMSAdapter(max_power=100000.0)
# Automatically uses DERAvailabilityAdapter internally
availability = adapter.snapshot_to_der_availability(snapshot)
```

## Availability Calculation

The module calculates available power considering:

1. **SOC-based discharge capacity**: Lower SOC reduces available discharge power
2. **Remaining capacity for charging**: Higher SOC reduces available charge power
3. **Rack current limits**: Maximum charge/discharge currents from active racks
4. **Voltage constraints**: Current capacity multiplied by average voltage

## IEEE 2030.5 Compliance

- Implements `DERAvailability` resource as per IEEE 2030.5-2023
- Follows URI path convention: `/edev/{id}/der/{id}/dera`
- Provides reserve charge percentage (0-10000 representing 0.00%-100.00%)
- Reports available power with appropriate multipliers for scaling
