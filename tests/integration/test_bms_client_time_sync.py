"""
Integration tests for BMSClient time synchronization.

Tests the integration of TimeSyncClient with BMSClient startup process.
"""

import pytest
import logging
from unittest.mock import AsyncMock, Mock, patch
import asyncio

from bms_2030_5_client.client import BMSClient
from bms_2030_5_client.config import Config
from bms_2030_5_client.models.ieee2030_5_models import Time


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = Mock(spec=Config)
    config.modbus = Mock()
    config.modbus.refresh_interval = 5
    config.ieee2030_5 = Mock()
    config.ieee2030_5.poll_rate = 60
    config.ieee2030_5.pin = "123456"
    config.subscription = Mock()
    config.subscription.enabled = False
    config.subscription.notification_host = "localhost"
    config.subscription.notification_port = 8443
    return config


@pytest.fixture
def mock_modbus_client():
    """Create a mock Modbus client."""
    client = AsyncMock()
    client.connect.return_value = True
    client.connected = True
    return client


@pytest.fixture
def mock_ieee2030_5_client():
    """Create a mock IEEE 2030.5 client."""
    client = AsyncMock()
    client.connect.return_value = True
    client.lfdi = "1234567890ABCDEF1234567890ABCDEF12345678"
    client.sfdi = 12345
    return client


@pytest.fixture
def mock_data_collector():
    """Create a mock data collector."""
    collector = AsyncMock()
    collector.start.return_value = None
    collector.stop.return_value = None
    return collector


@pytest.mark.asyncio
async def test_bms_client_time_sync_on_startup(
    mock_config, mock_modbus_client, mock_ieee2030_5_client, mock_data_collector
):
    """Test that BMSClient calls time sync during startup."""
    # Create BMSClient with mocked dependencies
    with patch('bms_2030_5_client.client.ModbusBMSClient') as mock_modbus_cls, \
         patch('bms_2030_5_client.client.BMSDataCollector') as mock_collector_cls, \
         patch('bms_2030_5_client.client.IEEE2030_5Client') as mock_ieee_cls, \
         patch('bms_2030_5_client.client.BMSAdapter'), \
         patch('bms_2030_5_client.client.init_database'), \
         patch('bms_2030_5_client.client.TaskSupervisor') as mock_supervisor_cls:
        
        # Setup mocks
        mock_modbus_cls.from_config.return_value = mock_modbus_client
        mock_collector_cls.return_value = mock_data_collector
        mock_ieee_cls.from_config.return_value = mock_ieee2030_5_client
        
        mock_supervisor = AsyncMock()
        mock_supervisor_cls.return_value = mock_supervisor
        
        # Create client
        client = BMSClient(
            config=mock_config,
            auto_register=False,  # Skip registration for this test
            enable_metering=False,
            enable_der_control=False,
        )
        
        # Mock the time sync client's sync_and_log_time method
        mock_sync_and_log = AsyncMock()
        client.time_sync_client.sync_and_log_time = mock_sync_and_log
        
        try:
            # Start the client
            await client.start()
            
            # Verify that time sync was called during startup
            mock_sync_and_log.assert_called_once()
            
        finally:
            # Clean up
            await client.stop()


@pytest.mark.asyncio
async def test_bms_client_time_sync_success_logging(
    mock_config, mock_modbus_client, mock_ieee2030_5_client, mock_data_collector, caplog
):
    """Test that successful time sync is logged during BMSClient startup."""
    # Create BMSClient with mocked dependencies
    with patch('bms_2030_5_client.client.ModbusBMSClient') as mock_modbus_cls, \
         patch('bms_2030_5_client.client.BMSDataCollector') as mock_collector_cls, \
         patch('bms_2030_5_client.client.IEEE2030_5Client') as mock_ieee_cls, \
         patch('bms_2030_5_client.client.BMSAdapter'), \
         patch('bms_2030_5_client.client.init_database'), \
         patch('bms_2030_5_client.client.TaskSupervisor') as mock_supervisor_cls:
        
        # Setup mocks
        mock_modbus_cls.from_config.return_value = mock_modbus_client
        mock_collector_cls.return_value = mock_data_collector
        mock_ieee_cls.from_config.return_value = mock_ieee2030_5_client
        
        mock_supervisor = AsyncMock()
        mock_supervisor_cls.return_value = mock_supervisor
        
        # Create client
        client = BMSClient(
            config=mock_config,
            auto_register=False,
            enable_metering=False,
            enable_der_control=False,
        )
        
        # Mock successful time sync
        server_time_val = 1704585600
        with patch.object(client.time_sync_client, 'get_server_time', return_value=server_time_val), \
             patch('time.time', return_value=1704585590):

            try:
                with caplog.at_level(logging.INFO, logger="bms_2030_5_client.core.time_client"):
                    await client.start()

                # Check that time sync success message appears in logs
                assert "Time synchronized with server" in caplog.text

            finally:
                await client.stop()


@pytest.mark.asyncio
async def test_bms_client_time_sync_failure_graceful_degradation(
    mock_config, mock_modbus_client, mock_ieee2030_5_client, mock_data_collector, caplog
):
    """Test that BMSClient continues startup even if time sync fails."""
    # Create BMSClient with mocked dependencies
    with patch('bms_2030_5_client.client.ModbusBMSClient') as mock_modbus_cls, \
         patch('bms_2030_5_client.client.BMSDataCollector') as mock_collector_cls, \
         patch('bms_2030_5_client.client.IEEE2030_5Client') as mock_ieee_cls, \
         patch('bms_2030_5_client.client.BMSAdapter'), \
         patch('bms_2030_5_client.client.init_database'), \
         patch('bms_2030_5_client.client.TaskSupervisor') as mock_supervisor_cls:
        
        # Setup mocks
        mock_modbus_cls.from_config.return_value = mock_modbus_client
        mock_collector_cls.return_value = mock_data_collector
        mock_ieee_cls.from_config.return_value = mock_ieee2030_5_client
        
        mock_supervisor = AsyncMock()
        mock_supervisor_cls.return_value = mock_supervisor
        
        # Create client
        client = BMSClient(
            config=mock_config,
            auto_register=False,
            enable_metering=False,
            enable_der_control=False,
        )
        
        # Mock failed time sync
        with patch.object(client.time_sync_client, 'get_server_time', return_value=None):
            
            try:
                # Start should succeed even with time sync failure
                await client.start()
                
                # Check that graceful degradation message appears in logs
                assert "Could not synchronize time with server" in caplog.text
                assert "Falling back to local system time" in caplog.text
                
                # Verify client is still running
                assert client.is_running
                
            finally:
                await client.stop()


@pytest.mark.asyncio
async def test_bms_client_time_sync_client_initialization():
    """Test that BMSClient properly initializes TimeSyncClient."""
    mock_config = Mock(spec=Config)
    mock_config.modbus = Mock()
    mock_config.ieee2030_5 = Mock()
    mock_config.subscription = Mock()
    mock_config.subscription.enabled = False
    mock_config.subscription.notification_host = "localhost"
    mock_config.subscription.notification_port = 8443
    
    with patch('bms_2030_5_client.client.ModbusBMSClient'), \
         patch('bms_2030_5_client.client.BMSDataCollector'), \
         patch('bms_2030_5_client.client.IEEE2030_5Client') as mock_ieee_cls, \
         patch('bms_2030_5_client.client.BMSAdapter'), \
         patch('bms_2030_5_client.client.init_database'), \
         patch('bms_2030_5_client.client.TaskSupervisor'):
        
        mock_ieee2030_5_client = AsyncMock()
        mock_ieee_cls.from_config.return_value = mock_ieee2030_5_client
        
        # Create client
        client = BMSClient(config=mock_config)
        
        # Verify TimeSyncClient was initialized
        assert client.time_sync_client is not None
        assert client.time_sync_client._client is mock_ieee2030_5_client


@pytest.mark.asyncio
async def test_bms_client_startup_sequence_with_time_sync(
    mock_config, mock_modbus_client, mock_ieee2030_5_client, mock_data_collector
):
    """Test that time sync happens at the correct point in startup sequence."""
    startup_calls = []
    
    # Create BMSClient with mocked dependencies
    with patch('bms_2030_5_client.client.ModbusBMSClient') as mock_modbus_cls, \
         patch('bms_2030_5_client.client.BMSDataCollector') as mock_collector_cls, \
         patch('bms_2030_5_client.client.IEEE2030_5Client') as mock_ieee_cls, \
         patch('bms_2030_5_client.client.BMSAdapter'), \
         patch('bms_2030_5_client.client.init_database'), \
         patch('bms_2030_5_client.client.TaskSupervisor') as mock_supervisor_cls:
        
        # Setup mocks to track call order
        def track_modbus_connect():
            startup_calls.append("modbus_connect")
            return True
        
        def track_ieee_connect():
            startup_calls.append("ieee_connect")
            return True
        
        def track_data_collector_start():
            startup_calls.append("data_collector_start")
        
        async def track_time_sync():
            startup_calls.append("time_sync")
        
        mock_modbus_client.connect.side_effect = track_modbus_connect
        mock_ieee2030_5_client.connect.side_effect = track_ieee_connect
        mock_data_collector.start.side_effect = track_data_collector_start
        
        mock_modbus_cls.from_config.return_value = mock_modbus_client
        mock_collector_cls.return_value = mock_data_collector
        mock_ieee_cls.from_config.return_value = mock_ieee2030_5_client
        
        mock_supervisor = AsyncMock()
        mock_supervisor_cls.return_value = mock_supervisor
        
        # Create client
        client = BMSClient(
            config=mock_config,
            auto_register=False,
            enable_metering=False,
            enable_der_control=False,
        )
        
        # Mock time sync
        client.time_sync_client.sync_and_log_time = track_time_sync
        
        try:
            await client.start()
            
            # Verify startup sequence: time_sync should happen first
            expected_sequence = ["time_sync", "modbus_connect", "ieee_connect", "data_collector_start"]
            assert startup_calls == expected_sequence
            
        finally:
            await client.stop()
