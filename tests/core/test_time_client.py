"""
Tests for TimeSyncClient.

Tests the time synchronization functionality with IEEE 2030.5 server.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import time

from bms_2030_5_client.core.time_client import TimeSyncClient
from bms_2030_5_client.core.sep_client import SepClientError
from bms_2030_5_client.models.ieee2030_5_models import Time


@pytest.fixture
def mock_ieee2030_5_client():
    """Create a mock IEEE2030_5Client."""
    client = AsyncMock()
    return client


@pytest.fixture
def time_sync_client(mock_ieee2030_5_client):
    """Create a TimeSyncClient with mocked dependencies."""
    mock_config = Mock()
    mock_config.enabled = True
    mock_config.interval_seconds = 900
    return TimeSyncClient(client=mock_ieee2030_5_client, config=mock_config)


@pytest.mark.asyncio
async def test_get_server_time_success(time_sync_client, mock_ieee2030_5_client):
    """Test successful server time retrieval."""
    # Mock successful HTTP response
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
    mock_ieee2030_5_client.get.return_value = mock_response
    
    expected_time = 1704585600
    
    with patch('bms_2030_5_client.core.time_client.xml_to_dataclass', return_value=Time(currentTime=expected_time)):
        result = await time_sync_client.get_server_time()
        assert result == expected_time

@pytest.mark.asyncio
async def test_sync_and_log_time_success(time_sync_client, caplog):
    """Test successful time synchronization and logging."""
    # Mock successful time retrieval
    mock_response = Mock()
    mock_response.is_success = True
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
    <Time xmlns="urn:ieee:std:2030.5:ns">
        <currentTime>1704585600</currentTime>
    </Time>"""
    
    server_time_val = 1704585600
    
    with patch.object(time_sync_client._client, 'get', return_value=mock_response):
        with patch('bms_2030_5_client.core.time_client.xml_to_dataclass', return_value=Time(currentTime=server_time_val)):
            with patch('time.time', return_value=1704585590):  # 10 seconds behind
                await time_sync_client.sync_and_log_time()
    
    # Check that success message was logged
    assert "Time synchronized with server" in caplog.text
    assert f"Server Time: {server_time_val}" in caplog.text
    assert "Local Time: 1704585590" in caplog.text
    assert "Delta: 10s" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_failure(time_sync_client, caplog):
    """Test time synchronization failure and graceful degradation."""
    # Mock failed time retrieval
    mock_response = Mock()
    mock_response.is_success = False
    mock_response.status_code = 404
    
    with patch.object(time_sync_client._client, 'get', return_value=mock_response):
        # Force raise_for_status to fail
        mock_response.raise_for_status.side_effect = Exception("HTTP 404")
        await time_sync_client.sync_and_log_time()
    
    # Check that warning message was logged
    assert "Could not synchronize time with server" in caplog.text
    assert "Falling back to local system time" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_invalid_server_time(time_sync_client, caplog):
    """Test time synchronization with invalid server time (zero timestamp)."""
    # Mock server time with zero currentTime
    mock_response = Mock()
    mock_response.is_success = True
    server_time_obj = Time(currentTime=0)
    
    with patch.object(time_sync_client._client, 'get', return_value=mock_response):
        with patch('bms_2030_5_client.core.time_client.xml_to_dataclass', return_value=server_time_obj):
            await time_sync_client.sync_and_log_time()
    
    # Should treat zero timestamp as invalid and fall back
    assert "Could not synchronize time with server" in caplog.text
    assert "Falling back to local system time" in caplog.text


@pytest.mark.asyncio
async def test_time_sync_client_initialization():
    """Test TimeSyncClient initialization."""
    mock_client = AsyncMock()
    mock_config = Mock()
    time_sync_client = TimeSyncClient(client=mock_client, config=mock_config)
    
    assert time_sync_client._client is mock_client
    assert time_sync_client._config is mock_config


@pytest.mark.asyncio
async def test_sync_and_log_time_large_delta(time_sync_client, caplog):
    """Test time synchronization with large time difference."""
    # Mock server time that's significantly ahead
    mock_response = Mock()
    mock_response.is_success = True
    server_time_val = 1704585600
    
    with patch.object(time_sync_client._client, 'get', return_value=mock_response):
        with patch('bms_2030_5_client.core.time_client.xml_to_dataclass', return_value=Time(currentTime=server_time_val)):
            with patch('time.time', return_value=1704582000):  # 1 hour behind
                await time_sync_client.sync_and_log_time()
    
    # Check that large delta is logged correctly
    assert "Time synchronized with server" in caplog.text
    assert f"Server Time: {server_time_val}" in caplog.text
    assert "Delta: 3600s" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_negative_delta(time_sync_client, caplog):
    """Test time synchronization with negative time difference (local ahead)."""
    # Mock server time that's behind local time
    mock_response = Mock()
    mock_response.is_success = True
    server_time_val = 1704585600
    
    with patch.object(time_sync_client._client, 'get', return_value=mock_response):
        with patch('bms_2030_5_client.core.time_client.xml_to_dataclass', return_value=Time(currentTime=server_time_val)):
            with patch('time.time', return_value=1704585700):  # 100 seconds ahead
                await time_sync_client.sync_and_log_time()
    
    # Check that negative delta is logged correctly
    assert "Time synchronized with server" in caplog.text
    assert f"Server Time: {server_time_val}" in caplog.text
    assert "Delta: -100s" in caplog.text
