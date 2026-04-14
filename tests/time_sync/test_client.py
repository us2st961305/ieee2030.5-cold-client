"""
Tests for TimeSyncClient.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, Mock, patch

from bms_2030_5_client.time_sync.client import TimeSyncClient
from bms_2030_5_client.runtime_config import TimeSyncConfig
from bms_2030_5_client.core.sep_client import SepClient, SepClientError
from bms_2030_5_client.models.ieee2030_5_models import Time


@pytest.fixture
def mock_sep_client():
    """Mock SepClient for testing."""
    client = Mock(spec=SepClient)
    client.get = AsyncMock()
    return client


@pytest.fixture
def time_sync_config():
    """Test configuration for TimeSyncClient."""
    return TimeSyncConfig(
        enabled=True,
        interval_seconds=900  # 15 minutes
    )


@pytest.fixture
def disabled_time_sync_config():
    """Disabled configuration for TimeSyncClient."""
    return TimeSyncConfig(
        enabled=False,
        interval_seconds=900
    )


@pytest.fixture
def time_sync_client(mock_sep_client, time_sync_config):
    """TimeSyncClient instance for testing."""
    return TimeSyncClient(mock_sep_client, time_sync_config)


class TestTimeSyncClient:
    """Tests for TimeSyncClient."""

    @pytest.mark.asyncio
    async def test_sync_time_success(self, time_sync_client, mock_sep_client):
        """Test successful time synchronization."""
        # Mock server response
        mock_response = Mock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<Time xmlns="urn:ieee:std:2030.5:ns">
    <currentTime>1640995200</currentTime>
    <dstOffset>0</dstOffset>
    <tzOffset>-28800</tzOffset>
    <quality>7</quality>
</Time>"""
        mock_response.raise_for_status = Mock()
        mock_sep_client.get.return_value = mock_response

        # Mock time.time() to return a known value
        with patch('time.time', return_value=1640995100):
            await time_sync_client.sync_time()

        # Verify the client made the correct request
        mock_sep_client.get.assert_called_once_with("/tm")
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_time_http_error(self, time_sync_client, mock_sep_client):
        """Test handling of HTTP errors during time sync."""
        # Mock SepClientError
        mock_sep_client.get.side_effect = SepClientError("HTTP 404 Not Found")

        # Should not raise exception, but log error
        await time_sync_client.sync_time()

        mock_sep_client.get.assert_called_once_with("/tm")

    @pytest.mark.asyncio
    async def test_sync_time_invalid_xml(self, time_sync_client, mock_sep_client):
        """Test handling of invalid XML response."""
        # Mock server response with invalid XML
        mock_response = Mock()
        mock_response.text = "<invalid>xml</invalid>"
        mock_response.raise_for_status = Mock()
        mock_sep_client.get.return_value = mock_response

        # Should not raise exception, but log error
        await time_sync_client.sync_time()

        mock_sep_client.get.assert_called_once_with("/tm")
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_time_http_status_error(self, time_sync_client, mock_sep_client):
        """Test handling of HTTP status errors."""
        # Mock server response that raises on status check
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500 Internal Server Error")
        mock_sep_client.get.return_value = mock_response

        # Should not raise exception, but log error
        await time_sync_client.sync_time()

        mock_sep_client.get.assert_called_once_with("/tm")
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_loop_and_stop(self, time_sync_client, mock_sep_client):
        """Test the run loop and stop functionality."""
        # Mock successful response
        mock_response = Mock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<Time xmlns="urn:ieee:std:2030.5:ns">
    <currentTime>1640995200</currentTime>
    <dstOffset>0</dstOffset>
    <tzOffset>-28800</tzOffset>
    <quality>7</quality>
</Time>"""
        mock_response.raise_for_status = Mock()
        mock_sep_client.get.return_value = mock_response

        # Start the run task
        run_task = asyncio.create_task(time_sync_client.run())

        # Let it run for a short time
        await asyncio.sleep(0.1)

        # Stop the client
        time_sync_client.stop()

        # Wait for the task to complete
        await run_task

        # Verify at least one sync attempt was made
        assert mock_sep_client.get.call_count >= 1
        mock_sep_client.get.assert_called_with("/tm")

    @pytest.mark.asyncio
    async def test_run_disabled_by_config(self, mock_sep_client, disabled_time_sync_config):
        """Test that run method does nothing when disabled by config."""
        client = TimeSyncClient(mock_sep_client, disabled_time_sync_config)

        await client.run()

        # Verify no sync attempts were made
        mock_sep_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_handles_sync_exceptions(self, time_sync_client, mock_sep_client):
        """Test that run loop continues even when sync_time raises exceptions."""
        # Make sync_time raise an exception
        mock_sep_client.get.side_effect = Exception("Unexpected error")

        # Start the run task
        run_task = asyncio.create_task(time_sync_client.run())

        # Let it run for a short time
        await asyncio.sleep(0.1)

        # Stop the client
        time_sync_client.stop()

        # Wait for the task to complete
        await run_task

        # Verify sync attempts were made despite exceptions
        assert mock_sep_client.get.call_count >= 1

    def test_stop_sets_running_false(self, time_sync_client):
        """Test that stop method sets _running to False."""
        time_sync_client._running = True
        time_sync_client.stop()
        assert time_sync_client._running is False

    @pytest.mark.asyncio
    async def test_sync_time_logs_time_offset(self, time_sync_client, mock_sep_client, caplog):
        """Test that sync_time logs the time offset correctly."""
        # Mock server response
        mock_response = Mock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<Time xmlns="urn:ieee:std:2030.5:ns">
    <currentTime>1640995200</currentTime>
    <dstOffset>0</dstOffset>
    <tzOffset>-28800</tzOffset>
    <quality>7</quality>
</Time>"""
        mock_response.raise_for_status = Mock()
        mock_sep_client.get.return_value = mock_response

        # Mock time.time() to return a known value
        with patch('time.time', return_value=1640995100):
            await time_sync_client.sync_time()

        # Check that the log contains the expected offset (100 seconds)
        assert "Offset: 100s" in caplog.text
        assert "Time sync successful" in caplog.text