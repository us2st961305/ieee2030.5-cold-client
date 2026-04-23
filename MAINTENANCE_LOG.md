
## [2026-04-23] TimeSyncClient Precision Fix (Prevention of Fake Success & Regression)
- **Issue**: The `TimeSyncClient` was logging the time delta but not applying it to the actual meter readings. Testing was passing due to mocks that bypassed the actual offset application. Furthermore, stale `site-packages` in the venv masked code changes.
- **Resolution**:
  - Unified `time_client.py` implementation in `src/bms_2030_5_client/core/time_client.py`.
  - Enforced that `sync_and_log_time()` calculates and **stores** the offset in `_time_offset`.
  - Introduced `get_corrected_time()` which returns `int(time.time()) + self._time_offset`.
  - Propagated `time_sync_client` down through `BMSClient` -> `BMSAdapter` -> `MirrorUsagePointAdapter` so all meter reading timestamps strictly use the server-aligned time.
- **Strict Guardrails**: 
  - DO NOT revert `get_server_time()` to return a `Time` object; it MUST return `Optional[int]` for type safety across callers. 
  - DO NOT omit or bypass `get_corrected_time()`. Merely logging the time delta is considered a failure.
  - When working on this module, ensure the venv's editable install is actually syncing with `src/` correctly.
