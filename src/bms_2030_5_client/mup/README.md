# MirrorUsagePoint (mup) Module

This module handles MirrorUsagePoint (metering) operations for IEEE 2030.5.

## Components

### `MirrorUsagePointAdapter`
Creates MirrorUsagePoint meters and converts BMS data to meter readings.

**Key Features:**
- Creates meter registration with reading types
- Generates unique mRIDs for resources
- Converts BMS snapshots to meter readings:
  - Battery SOC (State of Charge) - %
  - Total Current - A
  - Total Power - kW
  - Charge Energy - kWh (cumulative)
  - Discharge Energy - kWh (cumulative)
- Handles two-step server registration process

**Usage:**
```python
from bms_2030_5_client.mup import MirrorUsagePointAdapter

adapter = MirrorUsagePointAdapter()

# Create meter (without readings for POST)
mup = adapter.create_mirror_usage_point(
    device_lfdi="AABBCCDD...",
    description="BMS Battery Storage Meter",
    post_rate=60,
    include_readings=False  # For initial POST
)

# Convert snapshot to readings
readings = adapter.snapshot_to_meter_readings(snapshot, reading_mrids)
```

### `MirrorUsagePointClient`
Manages meter registration and reading uploads to the IEEE 2030.5 server.

**Key Features:**
- Handles two-step registration process:
  1. POST MirrorUsagePoint without readings
  2. PUT MirrorUsagePoint with readings
- Caches reading mRIDs for efficient updates
- Uploads individual meter readings
- Tracks MirrorUsagePoint href

**Usage:**
```python
from bms_2030_5_client.mup import MirrorUsagePointClient

client = MirrorUsagePointClient(ieee_client)

# Step 1: Register meter
mup_href = await client.register_meter(mup)

# Step 2: Update with readings
success = await client.update_meter_with_readings(mup_with_readings)

# Upload new readings
uploaded = await client.upload_readings(readings)
```

## Integration

This module is integrated into `BMSAdapter` for backward compatibility:

```python
from bms_2030_5_client.adapters import BMSAdapter

adapter = BMSAdapter()
# Automatically uses MirrorUsagePointAdapter internally
mup = adapter.create_bms_mirror_usage_point(device_lfdi, include_readings=True)
readings = adapter.snapshot_to_meter_readings(snapshot, reading_mrids)
```

## Reading Types

The module creates the following meter reading types:

| Reading | Unit | Type | Flow Direction | Description |
|---------|------|------|----------------|-------------|
| SOC | % (0.1%) | Instantaneous | N/A | State of Charge |
| Current | A (0.1A) | Instantaneous | NET | Total current (±) |
| Power | W (100W) | Instantaneous | NET | Total power (±) |
| Charge Energy | Wh (100Wh) | Cumulative | FORWARD | Energy charged into battery |
| Discharge Energy | Wh (100Wh) | Cumulative | REVERSE | Energy discharged from battery |

## Two-Step Registration Process

IEEE 2030.5 servers require a specific sequence:

1. **POST** `MirrorUsagePoint` without `MirrorMeterReading` → Returns location href
2. **PUT** `MirrorUsagePoint` with `MirrorMeterReading` → Registers readings
3. **POST** individual readings to upload new data

## IEEE 2030.5 Compliance

- Implements `MirrorUsagePoint` resource as per IEEE 2030.5-2023
- Follows URI path convention: `/mup`
- Supports role flags (IS_MIRROR | IS_DER)
- Complies with Reading Type specifications
- Uses appropriate UOM (Unit of Measure) codes
- Handles accumulation behavior (INSTANTANEOUS, CUMULATIVE)
