"""Regression tests for metering MirrorUsagePoint recovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bms_2030_5_client.client import BMSClient


@pytest.mark.asyncio
async def test_register_meter_keeps_cached_mup_href_when_verification_is_transient():
    """A verification transport error must not erase the last-known-good MUP href."""
    client = object.__new__(BMSClient)
    client._mup_href = "/mup/569295"
    client._mup_mrid = "mup-mrid"
    client._reading_mrids = {"power": "mrid-power"}
    client._db = None
    client.ieee2030_5_client = MagicMock()
    client.ieee2030_5_client.get_mirror_usage_point = AsyncMock(
        side_effect=TimeoutError("temporary DNS failure")
    )
    client.ieee2030_5_client.create_mirror_usage_point = AsyncMock()
    client.ieee2030_5_client.post_mirror_meter_reading_list = AsyncMock()
    client._recover_from_server = AsyncMock()

    await client._register_meter()

    assert client._mup_href == "/mup/569295"
    assert client._reading_mrids == {"power": "mrid-power"}
    client.ieee2030_5_client.create_mirror_usage_point.assert_not_awaited()
    client._recover_from_server.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_meter_readings_recovers_missing_mup_href_from_local_cache(sample_snapshot):
    """A transient lost _mup_href must not permanently skip metering uploads.

    Regression coverage for field issue: after a DNS/network recovery path cleared the
    runtime MUP href, the metering loop only logged "No MirrorUsagePoint href" and
    skipped forever until the container was restarted.  The upload path should reload
    last-known-good MUP state from SQLite before giving up.
    """
    client = object.__new__(BMSClient)
    client.data_collector = SimpleNamespace(latest_snapshot=sample_snapshot)
    client.config = SimpleNamespace(
        ieee2030_5=SimpleNamespace(poll_rate=180, meter_poll_rate=180)
    )
    client.ieee2030_5_client = MagicMock()
    client.ieee2030_5_client.post_mirror_meter_reading_list = AsyncMock(return_value=True)
    client.adapter = MagicMock()
    client.adapter.snapshot_to_meter_readings.return_value = [
        SimpleNamespace(description="Battery Total Power", mRID="mrid-power")
    ]

    client._mup_href = None
    client._mup_mrid = None
    client._reading_mrids = {"power": "mrid-power"}
    client._last_soc = None
    client._charge_accumulated = 0.0
    client._discharge_accumulated = 0.0
    client._cycle_count = 0
    client._partial_upload_count = 0
    client._partial_upload_threshold = 10

    def load_cached_resources():
        client._mup_href = "/mup/569295"
        client._mup_mrid = "mup-mrid"
        return True

    client._load_cached_resources = MagicMock(side_effect=load_cached_resources)
    client._recover_from_server = AsyncMock(return_value=False)
    client._register_meter = AsyncMock()
    client._save_cycle_tracking = MagicMock()
    client._record_meter_upload = MagicMock()
    client._sync_reading_mrids_to_db = MagicMock()
    client._recover_reading_mrids_from_server = AsyncMock(return_value=False)

    await client._upload_meter_readings()

    client._load_cached_resources.assert_called_once()
    client._recover_from_server.assert_not_awaited()
    client._register_meter.assert_not_awaited()
    client.ieee2030_5_client.post_mirror_meter_reading_list.assert_awaited_once_with(
        "/mup/569295",
        client.adapter.snapshot_to_meter_readings.return_value,
    )


@pytest.mark.asyncio
async def test_upload_meter_readings_attempts_server_recovery_before_skip(sample_snapshot):
    """If local cache cannot restore the href, try server-side MUP recovery before skipping."""
    client = object.__new__(BMSClient)
    client.data_collector = SimpleNamespace(latest_snapshot=sample_snapshot)
    client.config = SimpleNamespace(
        ieee2030_5=SimpleNamespace(poll_rate=180, meter_poll_rate=180)
    )
    client.ieee2030_5_client = MagicMock()
    client.ieee2030_5_client.post_mirror_meter_reading_list = AsyncMock(return_value=True)
    client.adapter = MagicMock()
    client.adapter.snapshot_to_meter_readings.return_value = [
        SimpleNamespace(description="Battery Total Power", mRID="mrid-power")
    ]

    client._mup_href = None
    client._mup_mrid = None
    client._reading_mrids = {"power": "mrid-power"}
    client._last_soc = None
    client._charge_accumulated = 0.0
    client._discharge_accumulated = 0.0
    client._cycle_count = 0
    client._partial_upload_count = 0
    client._partial_upload_threshold = 10

    client._load_cached_resources = MagicMock(return_value=False)

    async def recover_from_server():
        client._mup_href = "/mup/569295"
        client._mup_mrid = "mup-mrid"
        return True

    client._recover_from_server = AsyncMock(side_effect=recover_from_server)
    client._register_meter = AsyncMock()
    client._save_cycle_tracking = MagicMock()
    client._record_meter_upload = MagicMock()
    client._sync_reading_mrids_to_db = MagicMock()
    client._recover_reading_mrids_from_server = AsyncMock(return_value=False)

    await client._upload_meter_readings()

    client._load_cached_resources.assert_called_once()
    client._recover_from_server.assert_awaited_once()
    client._register_meter.assert_not_awaited()
    client.ieee2030_5_client.post_mirror_meter_reading_list.assert_awaited_once_with(
        "/mup/569295",
        client.adapter.snapshot_to_meter_readings.return_value,
    )
