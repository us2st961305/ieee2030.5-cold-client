"""
IEEE 2030.5 Notification Server for receiving push notifications.

Implements the client-side notification endpoint (POST /notify) as required by
IEEE Std 2030.5-2023 for receiving Notification resources from the server.

Features:
- Receives POST requests with sep+xml content
- Parses Notification/NotificationList resources
- Stores in ring buffer for logging
- Optional: Write to Modbus based on configured mappings
- TLS server support for secure notifications

Reference: IEEE 2030.5-2023, Table 6 (NotificationList POST Mandatory)
"""

from __future__ import annotations

import logging
import re
import ssl
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from bms_2030_5_client.runtime_config import (
    RuntimeConfig,
    NotificationServerConfig,
    SubscriptionConfig,
)
from bms_2030_5_client.web.log_buffer import log_buffer

logger = logging.getLogger(__name__)


# ============================================
# Notification Types
# ============================================

class NotificationStatus(int, Enum):
    """Notification status codes (IEEE 2030.5 NotificationStatus)."""
    DEFAULT = 0
    SUBSCRIPTION_CANCELLED = 1
    SUBSCRIPTION_UPDATED = 2
    RESOURCE_MODIFIED = 3
    RESOURCE_DELETED = 4


@dataclass
class ParsedNotification:
    """Parsed IEEE 2030.5 Notification."""
    subscription_uri: str          # subscriptionURI - which subscription triggered this
    subscribed_resource: str       # subscribedResource - the resource being watched
    status: NotificationStatus     # newResourceURI or status
    new_resource_uri: Optional[str] = None
    resource_content: Optional[str] = None  # Embedded resource if present
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "subscription_uri": self.subscription_uri,
            "subscribed_resource": self.subscribed_resource,
            "status": self.status.value,
            "new_resource_uri": self.new_resource_uri,
            "resource_content": self.resource_content[:200] if self.resource_content else None,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class NotificationServerStatus:
    """Notification server status."""
    running: bool = False
    tls_enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 8443
    endpoint_path: str = "/notify"
    started_at: Optional[datetime] = None
    notifications_received: int = 0
    last_notification_at: Optional[datetime] = None
    last_error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "running": self.running,
            "tls_enabled": self.tls_enabled,
            "listen_host": self.listen_host,
            "listen_port": self.listen_port,
            "endpoint_path": self.endpoint_path,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "notifications_received": self.notifications_received,
            "last_notification_at": self.last_notification_at.isoformat() if self.last_notification_at else None,
            "last_error": self.last_error,
        }


# ============================================
# Notification Parser
# ============================================

class NotificationParser:
    """
    Parse IEEE 2030.5 Notification/NotificationList XML.
    
    Notification structure:
    <Notification>
      <subscriptionURI>/sub/123</subscriptionURI>
      <subscribedResource>/edev/1/der/1/derc</subscribedResource>
      <status>3</status>  <!-- 3 = RESOURCE_MODIFIED -->
      <newResourceURI>/edev/1/der/1/derc/456</newResourceURI>
      <Resource>...</Resource>  <!-- Optional embedded resource -->
    </Notification>
    
    NotificationList structure:
    <NotificationList>
      <Notification>...</Notification>
      <Notification>...</Notification>
    </NotificationList>
    """
    
    @classmethod
    def parse(cls, xml_text: str) -> List[ParsedNotification]:
        """
        Parse Notification or NotificationList XML.
        
        Args:
            xml_text: XML body from POST request
            
        Returns:
            List of ParsedNotification objects
        """
        try:
            # Strip namespaces for easier parsing
            clean_xml = cls._strip_namespaces(xml_text)
            root = ET.fromstring(clean_xml)
            
            notifications = []
            
            # Check if it's a NotificationList or single Notification
            if root.tag == "NotificationList":
                for notification_elem in root.findall("Notification"):
                    parsed = cls._parse_notification_element(notification_elem)
                    if parsed:
                        notifications.append(parsed)
            elif root.tag == "Notification":
                parsed = cls._parse_notification_element(root)
                if parsed:
                    notifications.append(parsed)
            else:
                logger.warning(f"Unexpected root element: {root.tag}")
            
            return notifications
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse notification XML: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing notification: {e}")
            return []
    
    @classmethod
    def _parse_notification_element(cls, elem: ET.Element) -> Optional[ParsedNotification]:
        """Parse a single Notification element."""
        try:
            subscription_uri = cls._get_text(elem, "subscriptionURI") or ""
            subscribed_resource = cls._get_text(elem, "subscribedResource") or ""
            status_text = cls._get_text(elem, "status") or "0"
            new_resource_uri = cls._get_text(elem, "newResourceURI")
            
            # Get embedded resource if present
            resource_content = None
            resource_elem = elem.find("Resource")
            if resource_elem is not None:
                resource_content = ET.tostring(resource_elem, encoding="unicode")
            
            status = NotificationStatus(int(status_text))
            
            return ParsedNotification(
                subscription_uri=subscription_uri,
                subscribed_resource=subscribed_resource,
                status=status,
                new_resource_uri=new_resource_uri,
                resource_content=resource_content,
            )
            
        except Exception as e:
            logger.error(f"Error parsing notification element: {e}")
            return None
    
    @classmethod
    def _get_text(cls, elem: ET.Element, tag: str) -> Optional[str]:
        """Get text content of child element."""
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None
    
    @classmethod
    def _strip_namespaces(cls, xml_text: str) -> str:
        """Strip namespace declarations and prefixes."""
        # Remove xmlns declarations
        xml_text = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_text)
        # Remove namespace prefixes from tags
        xml_text = re.sub(r'<(\/?)\w+:', r'<\1', xml_text)
        return xml_text


# ============================================
# Notification Handler
# ============================================

class NotificationHandler:
    """
    Handle received notifications.
    
    - Logs to ring buffer
    - Matches to subscriptions
    - Optionally triggers Modbus writes
    """
    
    def __init__(
        self,
        config: RuntimeConfig,
        on_notification: Optional[Callable[[ParsedNotification], None]] = None,
    ):
        """
        Initialize notification handler.
        
        Args:
            config: Runtime configuration
            on_notification: Optional callback for each notification
        """
        self._config = config
        self._on_notification = on_notification
        
        # Build subscription lookup: resource_uri -> SubscriptionConfig
        self._subscription_map: Dict[str, SubscriptionConfig] = {}
        for sub in config.subscriptions:
            self._subscription_map[sub.resource_uri] = sub
    
    def handle(self, notifications: List[ParsedNotification]) -> int:
        """
        Handle a batch of notifications.
        
        Args:
            notifications: List of parsed notifications
            
        Returns:
            Number of notifications processed
        """
        processed = 0
        
        for notification in notifications:
            try:
                self._handle_single(notification)
                processed += 1
            except Exception as e:
                logger.error(f"Error handling notification: {e}")
        
        return processed
    
    def _handle_single(self, notification: ParsedNotification) -> None:
        """Handle a single notification."""
        # Log to buffer
        status_name = notification.status.name
        log_buffer.add(
            f"[NTFY] {notification.subscribed_resource} - {status_name}",
            level="INFO",
            logger_name="notification",
        )
        
        logger.info(
            f"Received notification: resource={notification.subscribed_resource}, "
            f"status={status_name}, new_uri={notification.new_resource_uri}"
        )
        
        # Match to subscription config
        sub_config = self._subscription_map.get(notification.subscribed_resource)
        if sub_config and sub_config.modbus_write:
            # TODO: Parse resource content and write to Modbus
            # This is optional functionality for future implementation
            logger.debug(
                f"Notification matched subscription {sub_config.id}, "
                f"Modbus write to {sub_config.modbus_write.address} (not implemented)"
            )
        
        # Call custom callback if set
        if self._on_notification:
            try:
                self._on_notification(notification)
            except Exception as e:
                logger.error(f"Error in notification callback: {e}")


# ============================================
# Notification Server Manager
# ============================================

class NotificationServerManager:
    """
    Manages the notification server lifecycle.
    
    Can run in two modes:
    1. Embedded in Flask app (shared process)
    2. Standalone HTTPS server (separate thread with TLS)
    
    For TLS mode, uses Python's built-in ssl module.
    """
    
    def __init__(self, config: RuntimeConfig):
        """
        Initialize server manager.
        
        Args:
            config: Runtime configuration
        """
        self._config = config
        self._ns_config = config.notification_server
        self._handler = NotificationHandler(config)
        
        self._status = NotificationServerStatus(
            tls_enabled=self._ns_config.tls_server_enabled,
            listen_host=self._ns_config.listen_host,
            listen_port=self._ns_config.listen_port,
            endpoint_path=self._ns_config.endpoint_path,
        )
        
        self._server_thread: Optional[threading.Thread] = None
        self._should_stop = threading.Event()
    
    @property
    def status(self) -> NotificationServerStatus:
        """Get current server status."""
        return self._status
    
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._status.running
    
    @property
    def handler(self) -> NotificationHandler:
        """Get notification handler."""
        return self._handler
    
    def start(self) -> bool:
        """
        Start the notification server.
        
        Returns:
            True if started successfully
        """
        if self._status.running:
            logger.warning("Notification server already running")
            return False
        
        logger.info(
            f"Starting notification server on "
            f"{self._ns_config.listen_host}:{self._ns_config.listen_port}"
        )
        
        self._status.running = True
        self._status.started_at = datetime.now()
        self._status.last_error = None
        
        log_buffer.add(
            f"Notification server started (TLS: {self._ns_config.tls_server_enabled})",
            level="INFO",
            logger_name="notification.server",
        )
        
        return True
    
    def stop(self) -> bool:
        """
        Stop the notification server.
        
        Returns:
            True if stopped successfully
        """
        if not self._status.running:
            logger.warning("Notification server not running")
            return False
        
        logger.info("Stopping notification server")
        
        self._should_stop.set()
        self._status.running = False
        
        log_buffer.add(
            "Notification server stopped",
            level="INFO",
            logger_name="notification.server",
        )
        
        return True
    
    def handle_notification_request(
        self,
        body: bytes,
        content_type: str,
    ) -> Tuple[int, str]:
        """
        Handle incoming notification POST request.
        
        This is called by Flask route or standalone server.
        
        Args:
            body: Raw request body
            content_type: Content-Type header
            
        Returns:
            Tuple of (status_code, response_body)
        """
        # Check content type
        if "sep+xml" not in content_type and "xml" not in content_type:
            logger.warning(f"Unexpected content type: {content_type}")
            # Continue anyway, might still be valid XML
        
        try:
            # Decode body
            xml_text = body.decode("utf-8")
            
            # Parse notifications
            notifications = NotificationParser.parse(xml_text)
            
            if not notifications:
                logger.warning("No notifications parsed from request")
                return (400, "<error>No valid notifications in request</error>")
            
            # Handle notifications
            processed = self._handler.handle(notifications)
            
            # Update stats
            self._status.notifications_received += processed
            self._status.last_notification_at = datetime.now()
            
            logger.info(f"Processed {processed} notification(s)")
            
            # IEEE 2030.5 expects 204 No Content for successful notification
            return (204, "")
            
        except Exception as e:
            logger.error(f"Error processing notification: {e}")
            self._status.last_error = str(e)
            return (500, f"<error>{e}</error>")
    
    def reload(self, new_config: RuntimeConfig) -> None:
        """Reload with new configuration."""
        self._config = new_config
        self._ns_config = new_config.notification_server
        self._handler = NotificationHandler(new_config)
        
        self._status.tls_enabled = self._ns_config.tls_server_enabled
        self._status.listen_host = self._ns_config.listen_host
        self._status.listen_port = self._ns_config.listen_port
        self._status.endpoint_path = self._ns_config.endpoint_path
        
        logger.info("Notification server configuration reloaded")
    
    def create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """
        Create SSL context for TLS server.
        
        Returns:
            SSLContext or None if TLS not configured
        """
        if not self._ns_config.tls_server_enabled:
            return None
        
        try:
            # Create server-side SSL context
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            
            # Load server certificate and key
            cert_path = Path(self._ns_config.tls_server_cert_path)
            key_path = Path(self._ns_config.tls_server_key_path)
            
            if not cert_path.exists():
                raise FileNotFoundError(f"Server certificate not found: {cert_path}")
            if not key_path.exists():
                raise FileNotFoundError(f"Server key not found: {key_path}")
            
            ctx.load_cert_chain(str(cert_path), str(key_path))
            
            # Optionally require client certificates (mTLS)
            if self._ns_config.tls_require_client_cert:
                ca_path = Path(self._ns_config.tls_client_ca_path)
                if ca_path.exists():
                    ctx.load_verify_locations(str(ca_path))
                    ctx.verify_mode = ssl.CERT_REQUIRED
                else:
                    logger.warning(f"Client CA not found: {ca_path}")
            
            logger.info(f"SSL context created for notification server")
            return ctx
            
        except Exception as e:
            logger.error(f"Failed to create SSL context: {e}")
            self._status.last_error = f"SSL setup failed: {e}"
            return None


# ============================================
# Global Instance
# ============================================

# Lazy-initialized global manager
_notification_manager: Optional[NotificationServerManager] = None


def get_notification_manager() -> NotificationServerManager:
    """Get or create the global notification manager."""
    global _notification_manager
    if _notification_manager is None:
        from bms_2030_5_client.runtime_config import RuntimeConfig
        try:
            config = RuntimeConfig.from_yaml("config/runtime.yaml")
        except Exception:
            config = RuntimeConfig()
        _notification_manager = NotificationServerManager(config)
    return _notification_manager


def init_notification_manager(config: RuntimeConfig) -> NotificationServerManager:
    """Initialize notification manager with config."""
    global _notification_manager
    _notification_manager = NotificationServerManager(config)
    return _notification_manager
