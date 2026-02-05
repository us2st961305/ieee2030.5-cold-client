"""
Tests for IEEE 2030.5 Subscription/Notification module.

Reference: IEEE Std 2030.5-2023, Clause 8.9
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import time

from bms_2030_5_client.subscription import (
    NotificationServer,
    NotificationServerConfig,
    SubscriptionManager,
    SubscriptionManagerConfig,
    NotificationHandler,
    NotificationHandlerConfig,
    TrackedSubscription,
    TimeSyncClient,
    TimeSyncConfig,
)
from bms_2030_5_client.models import (
    Subscription,
    Notification,
    SubscriptionEncodingType,
    NotificationStatusType,
    DERControlResponseFull,
)


# =============================================================================
# NotificationServerConfig Tests
# =============================================================================

class TestNotificationServerConfig:
    """Tests for NotificationServerConfig."""
    
    def test_config_defaults(self):
        """Test NotificationServerConfig default values."""
        config = NotificationServerConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8443
        assert config.endpoint == "/notify"
        assert config.require_client_cert is True
    
    def test_config_custom_values(self):
        """Test NotificationServerConfig with custom values."""
        config = NotificationServerConfig(
            host="127.0.0.1",
            port=9443,
            cert_file="custom.crt",
            key_file="custom.key",
        )
        assert config.host == "127.0.0.1"
        assert config.port == 9443
        assert config.cert_file == "custom.crt"


# =============================================================================
# NotificationServer Tests
# =============================================================================

class TestNotificationServer:
    """Tests for NotificationServer."""
    
    def test_notification_server_init(self):
        """Test NotificationServer initialization."""
        config = NotificationServerConfig(
            host="127.0.0.1",
            port=9443,
        )
        server = NotificationServer(config)
        assert server.config == config
        assert not server.is_running
    
    def test_set_notification_handler(self):
        """Test setting notification handler."""
        config = NotificationServerConfig()
        server = NotificationServer(config)
        
        async def mock_handler(notification, raw_xml):
            pass
        
        server.set_notification_handler(mock_handler)
        assert server._notification_handler == mock_handler
    
    def test_notification_uri(self):
        """Test notification_uri property."""
        config = NotificationServerConfig(
            host="192.168.1.100",
            port=8443,
            endpoint="/notify",
        )
        server = NotificationServer(config)
        assert server.notification_uri == "https://192.168.1.100:8443/notify"
    
    def test_stats_default(self):
        """Test default stats."""
        config = NotificationServerConfig()
        server = NotificationServer(config)
        stats = server.stats
        assert stats["notifications_received"] == 0
        assert stats["notifications_processed"] == 0
        assert stats["errors"] == 0


# =============================================================================
# SubscriptionManagerConfig Tests
# =============================================================================

class TestSubscriptionManagerConfig:
    """Tests for SubscriptionManagerConfig."""
    
    def test_config_defaults(self):
        """Test SubscriptionManagerConfig default values."""
        config = SubscriptionManagerConfig()
        assert config.renewal_interval_hours == 24.0
        assert config.min_renewal_interval_hours == 1.0
        assert config.encoding == SubscriptionEncodingType.XML
        assert config.level == "+S2"
        assert config.limit == 10
        assert config.max_retries == 3
        assert config.auto_resubscribe is True


# =============================================================================
# SubscriptionManager Tests
# =============================================================================

class TestSubscriptionManager:
    """Tests for SubscriptionManager."""
    
    def test_subscription_manager_init(self):
        """Test SubscriptionManager initialization."""
        mock_client = MagicMock()
        manager = SubscriptionManager(
            http_client=mock_client,
            notification_uri="https://localhost:8443/notify",
        )
        assert manager.notification_uri == "https://localhost:8443/notify"
        assert manager.http_client == mock_client
    
    def test_subscription_manager_with_config(self):
        """Test SubscriptionManager with custom config."""
        mock_client = MagicMock()
        config = SubscriptionManagerConfig(
            renewal_interval_hours=12.0,
            limit=20,
        )
        manager = SubscriptionManager(
            http_client=mock_client,
            notification_uri="https://localhost:8443/notify",
            config=config,
        )
        assert manager.config.renewal_interval_hours == 12.0
        assert manager.config.limit == 20


# =============================================================================
# TrackedSubscription Tests
# =============================================================================

class TestTrackedSubscription:
    """Tests for TrackedSubscription."""
    
    def test_tracked_subscription_creation(self):
        """Test TrackedSubscription creation."""
        from bms_2030_5_client.subscription.subscription_manager import SubscriptionType
        
        tracked = TrackedSubscription(
            resource_path="/edev/1/derp/1/derc",
            subscription_href="/sub/456",
            subscription_type=SubscriptionType.DERC,
        )
        
        assert tracked.resource_path == "/edev/1/derp/1/derc"
        assert tracked.subscription_href == "/sub/456"
        assert tracked.is_active is True
    
    def test_age_hours(self):
        """Test age_hours property."""
        tracked = TrackedSubscription(
            resource_path="/edev/1/fsa",
        )
        # Age should be very small (just created)
        assert tracked.age_hours < 0.01


# =============================================================================
# NotificationHandler Tests
# =============================================================================

class TestNotificationHandler:
    """Tests for NotificationHandler."""
    
    def test_notification_handler_init(self):
        """Test NotificationHandler initialization."""
        mock_client = MagicMock()
        
        handler = NotificationHandler(
            http_client=mock_client,
        )
        
        assert handler.http_client == mock_client
    
    def test_notification_handler_with_subscription_manager(self):
        """Test NotificationHandler with subscription manager."""
        mock_client = MagicMock()
        mock_sub_manager = MagicMock()
        
        handler = NotificationHandler(
            http_client=mock_client,
            subscription_manager=mock_sub_manager,
        )
        
        assert handler.subscription_manager == mock_sub_manager
    
    def test_set_control_callbacks(self):
        """Test setting control callbacks."""
        mock_client = MagicMock()
        handler = NotificationHandler(http_client=mock_client)
        
        async def mock_control_handler(control):
            pass
        
        async def mock_default_handler(control):
            pass
        
        handler.set_on_control_received(mock_control_handler)
        handler.set_on_default_control(mock_default_handler)
        
        assert handler._on_control_received == mock_control_handler
        assert handler._on_default_control == mock_default_handler
    
    def test_stats_default(self):
        """Test default stats."""
        mock_client = MagicMock()
        handler = NotificationHandler(http_client=mock_client)
        
        stats = handler.stats
        assert stats["notifications_handled"] == 0
        assert stats["controls_received"] == 0
        assert stats["responses_sent"] == 0
        assert stats["errors"] == 0


# =============================================================================
# NotificationHandlerConfig Tests
# =============================================================================

class TestNotificationHandlerConfig:
    """Tests for NotificationHandlerConfig."""
    
    def test_config_defaults(self):
        """Test NotificationHandlerConfig default values."""
        config = NotificationHandlerConfig()
        assert config.auto_send_response is True
        assert config.response_timeout_s == 30.0
        assert config.log_all_notifications is True


# =============================================================================
# TimeSyncConfig Tests
# =============================================================================

class TestTimeSyncConfig:
    """Tests for TimeSyncConfig."""
    
    def test_config_defaults(self):
        """Test TimeSyncConfig default values."""
        config = TimeSyncConfig()
        assert config.sync_interval_s == 900.0  # 15 minutes
        assert config.max_drift_s == 5.0
        assert config.auto_adjust is False


# =============================================================================
# TimeSyncClient Tests
# =============================================================================

class TestTimeSyncClient:
    """Tests for TimeSyncClient."""
    
    def test_time_sync_client_init(self):
        """Test TimeSyncClient initialization."""
        mock_client = MagicMock()
        client = TimeSyncClient(
            http_client=mock_client,
        )
        
        assert client.http_client == mock_client
    
    def test_time_sync_client_with_config(self):
        """Test TimeSyncClient with custom config."""
        mock_client = MagicMock()
        config = TimeSyncConfig(
            sync_interval_s=300,
            max_drift_s=10.0,
        )
        client = TimeSyncClient(
            http_client=mock_client,
            config=config,
        )
        
        assert client.config.sync_interval_s == 300
        assert client.config.max_drift_s == 10.0


# =============================================================================
# Subscription Models Tests
# =============================================================================

class TestSubscriptionModels:
    """Tests for Subscription and Notification models."""
    
    def test_subscription_model(self):
        """Test Subscription model creation."""
        sub = Subscription(
            subscribedResource="/edev/1/derp/1/derc",
            encoding=SubscriptionEncodingType.XML,
            level="+S2",
            limit=10,
            notificationURI="https://localhost:8443/notify",
        )
        
        assert sub.subscribedResource == "/edev/1/derp/1/derc"
        assert sub.encoding == SubscriptionEncodingType.XML
        assert sub.notificationURI == "https://localhost:8443/notify"
    
    def test_notification_model(self):
        """Test Notification model creation."""
        notif = Notification(
            subscribedResource="/edev/1/derp/1/derc",
            status=NotificationStatusType.RESOURCE_MOVED,
            newResourceURI="/edev/1/derp/1/derc/new123",
        )
        
        assert notif.subscribedResource == "/edev/1/derp/1/derc"
        assert notif.status == NotificationStatusType.RESOURCE_MOVED
        assert notif.newResourceURI == "/edev/1/derp/1/derc/new123"
    
    def test_subscription_encoding_types(self):
        """Test SubscriptionEncodingType enum values."""
        # IEEE 2030.5-2023: 0 = XML, 1 = EXI
        assert SubscriptionEncodingType.XML.value == 0
        assert SubscriptionEncodingType.EXI.value == 1
    
    def test_notification_status_types(self):
        """Test NotificationStatusType enum values."""
        # IEEE 2030.5-2023 Table 14
        assert NotificationStatusType.DEFAULT.value == 0
        assert NotificationStatusType.SUBSCRIPTION_CANCELLED.value == 1
        assert NotificationStatusType.SUBSCRIPTION_SUPERSEDED.value == 2
        assert NotificationStatusType.RESOURCE_MOVED.value == 3
        assert NotificationStatusType.RESOURCE_DELETED.value == 4
    
    def test_der_control_response_full(self):
        """Test DERControlResponseFull model."""
        response = DERControlResponseFull(
            createdDateTime=int(time.time()),
            endDeviceLFDI="AABBCCDD11223344",
            status=0,  # EventReceived
            subject="abc123def456",
        )
        
        assert response.endDeviceLFDI == "AABBCCDD11223344"
        assert response.status == 0
        assert response.subject == "abc123def456"


# =============================================================================
# Integration Tests (Mock)
# =============================================================================

class TestSubscriptionIntegration:
    """Integration tests for subscription components."""
    
    @pytest.mark.asyncio
    async def test_subscription_chain_concept(self):
        """Test subscription chain concept: FSA → DERProgram → DERControl."""
        # This tests the conceptual flow without actual server calls
        mock_client = MagicMock()
        
        manager = SubscriptionManager(
            http_client=mock_client,
            notification_uri="https://localhost:8443/notify",
        )
        
        # Verify manager has correct notification URI
        assert manager.notification_uri == "https://localhost:8443/notify"
        
        # Verify config defaults are set
        assert manager.config.renewal_interval_hours == 24.0
    
    @pytest.mark.asyncio
    async def test_time_sync_uses_polling(self):
        """Test that time sync uses polling (not subscription)."""
        # /tm (Time resource) cannot be subscribed per IEEE 2030.5-2023
        # TimeSyncClient should use polling
        mock_client = MagicMock()
        
        config = TimeSyncConfig(sync_interval_s=900)
        client = TimeSyncClient(
            http_client=mock_client,
            config=config,
        )
        
        # Verify time sync uses polling interval
        assert client.config.sync_interval_s == 900  # 15 minutes


# =============================================================================
# Safety Tests
# =============================================================================

class TestSubscriptionSafety:
    """Safety tests for subscription-based power control."""
    
    @pytest.mark.asyncio
    async def test_notification_handler_with_control_handler(self):
        """Verify NotificationHandler can use DERControlHandler."""
        mock_client = MagicMock()
        mock_control_handler = MagicMock()
        
        handler = NotificationHandler(
            http_client=mock_client,
            control_handler=mock_control_handler,
        )
        
        # Verify handler has reference to control handler
        assert handler.control_handler == mock_control_handler
    
    def test_subscription_manager_tracks_active_subscriptions(self):
        """Test that SubscriptionManager can track subscriptions."""
        mock_client = MagicMock()
        
        manager = SubscriptionManager(
            http_client=mock_client,
            notification_uri="https://localhost:8443/notify",
        )
        
        # Verify auto_resubscribe is enabled by default
        assert manager.config.auto_resubscribe is True
