"""
Tests for TimeSyncClient.

Tests the time synchronization functionality with IEEE 2030.5 server.

API contract (locked — do not change without updating time_client.py):
- get_server_time() returns Optional[int] (Unix epoch seconds)
- sync_and_log_time() stores the offset in _time_offset
- get_corrected_time() returns int(time.time()) + _time_offset
"""

import pytest
import logging
from unittest.mock import AsyncMock, Mock, patch

from bms_2030_5_client.core.time_client import TimeSyncClient
from bms_2030_5_client.core.sep_client import SepClientError
from bms_2030_5_client.models.ieee2030_5_models import Time


@pytest.fixture
def mock_sep_client():
    """Create a mock SepClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def time_sync_client(mock_sep_client):
    """Create a TimeSyncClient with mocked dependencies (no config — manual sync)."""
    return TimeSyncClient(client=mock_sep_client)


@pytest.fixture
def time_sync_client_with_config(mock_sep_client):
    """Create a TimeSyncClient with config (for run() loop tests)."""
    mock_config = Mock()
    mock_config.enabled = True
    mock_config.interval_seconds = 900
    return TimeSyncClient(client=mock_sep_client, config=mock_config)


# ---------------------------------------------------------------------------
# get_server_time()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_server_time_success(time_sync_client, mock_sep_client):
    """Test successful server time retrieval — returns int."""
    mock_response = Mock()
    mock_response.is_success = True
    mock_response.body = """<?xml version="1.0" encoding="UTF-8"?>
    <Time xmlns="urn:ieee:std:2030.5:ns">
        <href>/tm</href>
        <currentTime>1704585600</currentTime>
        <dstEndTime>0</dstEndTime>
        <dstOffset>0</dstOffset>
        <dstStartTime>0</dstStartTime>
        <localTime>1704585600</localTime>
        <quality>0</quality>
        <tzOffset>0</tzOffset>
    </Time>"""
    mock_sep_client.get.return_value = mock_response

    expected_time = 1704585600

    with patch('bms_2030_5_client.core.time_client.xml_to_dataclass',
               return_value=Time(currentTime=expected_time)):
        result = await time_sync_client.get_server_time()

    assert result == expected_time
    assert isinstance(result, int), "get_server_time() MUST return int, not a Time object"


@pytest.mark.asyncio
async def test_get_server_time_http_failure(time_sync_client, mock_sep_client):
    """Test get_server_time returns None on HTTP failure."""
    mock_response = Mock()
    mock_response.is_success = False
    mock_response.status_code = 404
    mock_sep_client.get.return_value = mock_response

    result = await time_sync_client.get_server_time()
    assert result is None


@pytest.mark.asyncio
async def test_get_server_time_zero_is_invalid(time_sync_client, mock_sep_client):
    """Test that currentTime=0 is treated as invalid and returns None."""
    mock_response = Mock()
    mock_response.is_success = True
    mock_response.body = "<Time/>"
    mock_sep_client.get.return_value = mock_response

    with patch('bms_2030_5_client.core.time_client.xml_to_dataclass',
               return_value=Time(currentTime=0)):
        result = await time_sync_client.get_server_time()

    assert result is None


@pytest.mark.asyncio
async def test_get_server_time_exception_returns_none(time_sync_client, mock_sep_client):
    """Test that exceptions in get_server_time() return None gracefully."""
    mock_sep_client.get.side_effect = SepClientError("connection refused")

    result = await time_sync_client.get_server_time()
    assert result is None


# ---------------------------------------------------------------------------
# sync_and_log_time() — offset MUST be stored
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_and_log_time_stores_positive_offset(time_sync_client, caplog):
    """Test that a positive offset (local behind server) is stored and logged."""
    server_time_val = 1704585600  # server time

    with caplog.at_level(logging.INFO, logger="bms_2030_5_client.core.time_client"):
        with patch.object(time_sync_client, 'get_server_time', return_value=server_time_val), \
             patch('bms_2030_5_client.core.time_client.time.time', return_value=1704585590):  # local 10s behind
            await time_sync_client.sync_and_log_time()

    # Offset must be stored — this is the core fix
    assert time_sync_client._time_offset == 10, (
        "_time_offset MUST be stored after sync (server - local = +10). "
        "Merely logging it is not enough."
    )
    assert time_sync_client.is_synced is True
    assert "Time synchronized with server" in caplog.text
    assert "Server Time: 1704585600" in caplog.text
    assert "Local Time: 1704585590" in caplog.text
    assert "Delta: 10s" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_stores_negative_offset(time_sync_client, caplog):
    """Test that a negative offset (local ahead of server) is stored correctly."""
    server_time_val = 1704585600

    with caplog.at_level(logging.INFO, logger="bms_2030_5_client.core.time_client"):
        with patch.object(time_sync_client, 'get_server_time', return_value=server_time_val), \
             patch('bms_2030_5_client.core.time_client.time.time', return_value=1704585700):  # local 100s ahead
            await time_sync_client.sync_and_log_time()

    assert time_sync_client._time_offset == -100
    assert "Delta: -100s" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_stores_large_delta(time_sync_client, caplog):
    """Test large time difference (1 hour)."""
    server_time_val = 1704585600

    with caplog.at_level(logging.INFO, logger="bms_2030_5_client.core.time_client"):
        with patch.object(time_sync_client, 'get_server_time', return_value=server_time_val), \
             patch('bms_2030_5_client.core.time_client.time.time', return_value=1704582000):  # 1h behind
            await time_sync_client.sync_and_log_time()

    assert time_sync_client._time_offset == 3600
    assert "Delta: 3600s" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_failure_does_not_change_offset(time_sync_client, caplog):
    """Test that a failed sync does NOT overwrite a previously good offset."""
    # First a successful sync
    with patch.object(time_sync_client, 'get_server_time', return_value=1704585600), \
         patch('bms_2030_5_client.core.time_client.time.time', return_value=1704585590):
        await time_sync_client.sync_and_log_time()

    assert time_sync_client._time_offset == 10  # stored from first sync

    # Now a failed sync
    with patch.object(time_sync_client, 'get_server_time', return_value=None):
        await time_sync_client.sync_and_log_time()

    # Offset must remain from last successful sync
    assert time_sync_client._time_offset == 10, (
        "A failed sync must NOT reset _time_offset to 0. "
        "The last known good offset should be preserved."
    )
    assert "Could not synchronize time with server" in caplog.text
    assert "Falling back to local system time" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_invalid_zero_time(time_sync_client, caplog):
    """Test that zero/invalid server time triggers fallback."""
    with patch.object(time_sync_client, 'get_server_time', return_value=None):
        await time_sync_client.sync_and_log_time()

    assert "Could not synchronize time with server" in caplog.text
    assert "Falling back to local system time" in caplog.text
    assert time_sync_client.is_synced is False


# ---------------------------------------------------------------------------
# get_corrected_time()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_corrected_time_applies_offset(time_sync_client):
    """Test that get_corrected_time() returns local_time + stored_offset."""
    # Simulate a +10s offset (local is 10s behind server)
    with patch.object(time_sync_client, 'get_server_time', return_value=1704585600), \
         patch('bms_2030_5_client.core.time_client.time.time', return_value=1704585590):
        await time_sync_client.sync_and_log_time()

    with patch('bms_2030_5_client.core.time_client.time.time', return_value=1704585590):
        corrected = time_sync_client.get_corrected_time()

    assert corrected == 1704585600, (
        "get_corrected_time() must return local_time + offset = 1704585590 + 10 = 1704585600"
    )


def test_get_corrected_time_without_sync_returns_local(time_sync_client):
    """Before any sync, get_corrected_time() returns local time (offset=0)."""
    fake_now = 1704585600
    with patch('bms_2030_5_client.core.time_client.time.time', return_value=fake_now):
        corrected = time_sync_client.get_corrected_time()

    assert corrected == fake_now
    assert time_sync_client._time_offset == 0


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def test_initialization_without_config(mock_sep_client):
    """TimeSyncClient works without config (manual sync mode)."""
    client = TimeSyncClient(client=mock_sep_client)
    assert client._client is mock_sep_client
    assert client._config is None
    assert client._time_offset == 0
    assert client.is_synced is False


def test_initialization_with_config(mock_sep_client):
    """TimeSyncClient accepts config for run() loop."""
    mock_config = Mock()
    mock_config.enabled = True
    mock_config.interval_seconds = 300
    client = TimeSyncClient(client=mock_sep_client, config=mock_config)
    assert client._config is mock_config


@pytest.mark.asyncio
async def test_run_loop_requires_config(time_sync_client):
    """run() without config must raise RuntimeError."""
    with pytest.raises(RuntimeError, match="requires a config object"):
        await time_sync_client.run()


@pytest.mark.asyncio
async def test_run_loop_disabled_by_config(time_sync_client_with_config, caplog):
    """run() with config.enabled=False exits immediately."""
    time_sync_client_with_config._config.enabled = False
    with caplog.at_level(logging.INFO, logger="bms_2030_5_client.core.time_client"):
        await time_sync_client_with_config.run()
    assert "disabled by configuration" in caplog.text
