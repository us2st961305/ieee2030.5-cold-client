# BMSAdapter Fix Log

This document details the technical changes made to the `BMSAdapter` and related components as part of the "Surgical Fix" to ensure compliance with IEEE 2030.5 and improve system reliability. This log serves as a reference for resolving merge conflicts during integration into the `main` branch.

## Modified Files
- `src/bms_2030_5_client/adapters/bms_adapter.py`
- `src/bms_2030_5_client/mup/adapter.py` (Referenced by BMSAdapter)
- `src/bms_2030_5_client/client.py` (Referenced by BMSAdapter)

---

## Detailed Changes

### 1. `src/bms_2030_5_client/adapters/bms_adapter.py`

#### Change A: mRID Persistence Support
- **Before**: `create_bms_mirror_usage_point` generated a new random UUID for the `mRID` every time it was called.
- **After**: Added `mup_mrid` optional parameter to `create_bms_mirror_usage_point` to allow reusing a persisted mRID.
- **Logic Change**: Added `mup_mrid: str | None = None` to arguments; used `mup_mrid` if provided, otherwise fell back to `_generate_mrid()`.
- **Why**: IEEE 2030.5 Section 10.11.3(a)(4) requires stable identification. Reusing the mRID prevents the server from creating duplicate `MirrorUsagePoint` resources across client restarts.

#### Change B: Meter Reading Filtering (`skip_missing_mrids`)
- **Before**: `snapshot_to_meter_readings` always attempted to generate or use mRIDs for all readings.
- **After**: Added `skip_missing_mrids` passthrough parameter.
- **Logic Change**: Added `skip_missing_mrids: bool = False` to `snapshot_to_meter_readings` and passed it to the underlying `MirrorUsagePointAdapter`.
- **Why**: Allows the system to skip readings that don't have a cached mRID instead of forcing the creation of new ones, reducing unnecessary registration traffic.

#### Change C: Timezone-Aware Timestamps
- **Before**: Used `datetime.now().timestamp()`, which is naive and depends on the local system timezone.
- **After**: Replaced with `datetime.now(timezone.utc).timestamp()`.
- **Logic Change**: Changed `datetime.now()` to `datetime.now(timezone.utc)`.
- **Why**: Prevents Python 3.12 deprecation warnings and ensures consistency in UTC timestamps across different deployment environments.

#### Change D: State of Charge (SOC) Clamping & Scaling
- **Before**: `_to_soc` multiplied the raw percentage by 100 without bounds checking.
- **After**: Added clamping to the range `[0.0, 100.0]`.
- **Logic Change**: Added `clamped = max(0.0, min(100.0, percent))` before calculating `int(clamped * 100)`.
- **Why**: Ensures the value sent to the server is always within the valid IEEE 2030.5 range (0-10000), preventing API errors due to out-of-bounds data.

#### Change E: Alarm Status Formatting
- **Before**: `alarmStatus` was only sent if it was non-zero, or used a complex `AlarmStatusValue` object.
- **After**: Always send `alarmStatus` as a formatted 8-character hex string.
- **Logic Change**: Changed to `alarmStatus=f"{alarm_status:08X}"`.
- **Why**: Simplifies the data model and ensures the server always receives a consistent state (even if zero), matching the expected `hexBinary` format.

#### Change F: Architecture Refactoring (Delegation)
- **Before**: `BMSAdapter` contained all conversion logic for Status, Availability, and Metering.
- **After**: `BMSAdapter` now acts as a facade, delegating to specialized adapters (`DERStatusAdapter`, `DERAvailabilityAdapter`, `MirrorUsagePointAdapter`).
- **Logic Change**: Initialized `_ders_adapter`, `_dera_adapter`, and `_mup_adapter` in `__init__` and updated methods to call these sub-adapters.
- **Why**: Improves maintainability, reduces file size, and allows independent testing of each IEEE 2030.5 resource conversion logic.

---

## Final Verification Results
- **Test Suite**: All core adapter tests passed.
- **mRID Persistence**: Verified that `MirrorUsagePoint` is reused across restarts when `mup_mrid` is provided.
- **Compliance**: Validated that SOC and Alarm status formats align with IEEE 2030.5 specifications.
- **API Compatibility**: Verified that `pymodbus` API changes (slave $\rightarrow$ device_id) are correctly handled in the underlying modbus clients used by the adapter.
