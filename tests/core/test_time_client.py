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
    return TimeSyncClient(client=mock_ieee2030_5_client)


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
    
    # Mock xml_to_dataclass to return a Time object
    expected_time = Time(
        href="/tm",
        currentTime=1704585600,
        dstEndTime=0,
        dstOffset=0,
        dstStartTime=0,
        localTime=1704585600,
        quality=0,
        tzOffset=0,
    )
    
    with patch('bms_2030_5_client.core.time_client.xml_to_dataclass', return_value=expected_time):
        result = await time_sync_client.get_server_time()
    
    # Verify the result
    assert result is not None
    assert result.currentTime == 1704585600
    assert result.href == "/tm"
    
    # Verify the HTTP call was made correctly
    mock_ieee2030_5_client.get.assert_called_once_with("/tm")


@pytest.mark.asyncio
async def test_get_server_time_http_error(time_sync_client, mock_ieee2030_5_client):
    """Test server time retrieval with HTTP error."""
    # Mock failed HTTP response
    mock_response = Mock()
    mock_response.is_success = False
    mock_response.status_code = 404
    mock_response.body = "Not Found"
    mock_ieee2030_5_client.get.return_value = mock_response
    
    result = await time_sync_client.get_server_time()
    
    # Should return None on HTTP error
    assert result is None
    mock_ieee2030_5_client.get.assert_called_once_with("/tm")


@pytest.mark.asyncio
async def test_get_server_time_connection_error(time_sync_client, mock_ieee2030_5_client):
    """Test server time retrieval with connection error."""
    # Mock SepClientError
    mock_ieee2030_5_client.get.side_effect = SepClientError("Connection failed")
    
    result = await time_sync_client.get_server_time()
    
    # Should return None on connection error
    assert result is None
    mock_ieee2030_5_client.get.assert_called_once_with("/tm")


@pytest.mark.asyncio
async def test_get_server_time_xml_parse_error(time_sync_client, mock_ieee2030_5_client):
    """Test server time retrieval with XML parsing error."""
    # Mock successful HTTP response with invalid XML
    mock_response = Mock()
    mock_response.is_success = True
    mock_response.body = "Invalid XML"
    mock_ieee2030_5_client.get.return_value = mock_response
    
    # Mock xml_to_dataclass to raise an exception
    with patch('bms_2030_5_client.core.time_client.xml_to_dataclass', side_effect=Exception("Parse error")):
        result = await time_sync_client.get_server_time()
    
    # Should return None on parsing error
    assert result is None


@pytest.mark.asyncio
async def test_sync_and_log_time_success(time_sync_client, caplog):
    """Test successful time synchronization and logging."""
    # Mock successful time retrieval
    server_time = Time(currentTime=1704585600)
    
    with patch.object(time_sync_client, 'get_server_time', return_value=server_time):
        with patch('time.time', return_value=1704585590):  # 10 seconds behind
            await time_sync_client.sync_and_log_time()
    
    # Check that success message was logged
    assert "Time synchronized with server" in caplog.text
    assert "Server Time: 1704585600" in caplog.text
    assert "Local Time: 1704585590" in caplog.text
    assert "Delta: 10s" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_failure(time_sync_client, caplog):
    """Test time synchronization failure and graceful degradation."""
    # Mock failed time retrieval
    with patch.object(time_sync_client, 'get_server_time', return_value=None):
        await time_sync_client.sync_and_log_time()
    
    # Check that warning message was logged
    assert "Could not synchronize time with server" in caplog.text
    assert "Falling back to local system time" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_invalid_server_time(time_sync_client, caplog):
    """Test time synchronization with invalid server time (zero timestamp)."""
    # Mock server time with zero currentTime
    server_time = Time(currentTime=0)
    
    with patch.object(time_sync_client, 'get_server_time', return_value=server_time):
        await time_sync_client.sync_and_log_time()
    
    # Should treat zero timestamp as invalid and fall back
    assert "Could not synchronize time with server" in caplog.text
    assert "Falling back to local system time" in caplog.text


@pytest.mark.asyncio
async def test_time_sync_client_initialization():
    """Test TimeSyncClient initialization."""
    mock_client = AsyncMock()
    time_sync_client = TimeSyncClient(client=mock_client)
    
    assert time_sync_client._client is mock_client
    assert time_sync_client._time_resource_path == "/tm"


@pytest.mark.asyncio
async def test_sync_and_log_time_large_delta(time_sync_client, caplog):
    """Test time synchronization with large time difference."""
    # Mock server time that's significantly ahead
    server_time = Time(currentTime=1704585600)
    
    with patch.object(time_sync_client, 'get_server_time', return_value=server_time):
        with patch('time.time', return_value=1704582000):  # 1 hour behind
            await time_sync_client.sync_and_log_time()
    
    # Check that large delta is logged correctly
    assert "Time synchronized with server" in caplog.text
    assert "Delta: 3600s" in caplog.text


@pytest.mark.asyncio
async def test_sync_and_log_time_negative_delta(time_sync_client, caplog):
    """Test time synchronization with negative time difference (local ahead)."""
    # Mock server time that's behind local time
    server_time = Time(currentTime=1704585600)
    
    with patch.object(time_sync_client, 'get_server_time', return_value=server_time):
        with patch('time.time', return_value=1704585700):  # 100 seconds ahead
            await time_sync_client.sync_and_log_time()
    
    # Check that negative delta is logged correctly
    assert "Time synchronized with server" in caplog.text
    assert "Delta: -100s" in caplog.text