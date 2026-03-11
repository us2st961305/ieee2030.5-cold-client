"""
Subscription Manager for IEEE 2030.5 Push Notifications.

依據 IEEE Std 2030.5-2023 實作訂閱管理功能：

- 建立訂閱 (POST to SubscriptionList)
- 刪除訂閱 (DELETE Subscription resource)
- 續訂策略 (依 renew_interval_hours 排程)
- enable/disable 控制
- reload 設定檔自動 reconcile
- on_reconnect 斷線恢復處理

IEEE 2030.5 Subscription 規範重點：
- Subscription body 需包含 Notification endpoint (notificationURI)
- subscribedResource 指向要訂閱的資源
- 伺服器回傳的 Location header 包含新建立的 Subscription href
- DELETE 移除訂閱時使用該 href

Reference:
- IEEE 2030.5-2023 Table 6 (Subscription POST/DELETE)
- IEEE 2030.5-2023 Clause 8.9 (Subscription Function Set)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from xml.etree import ElementTree as ET

from bms_2030_5_client.core.sep_client import SepClient, SepClientError, SepResponse
from bms_2030_5_client.runtime_config import (
    RuntimeConfig,
    ProfileConfig,
    SubscriptionConfig,
    NotificationServerConfig,
)

logger = logging.getLogger(__name__)


# ============================================
# Constants
# ============================================

# IEEE 2030.5 encoding types
ENCODING_XML = 0
ENCODING_EXI = 1
ENCODING_APPLICATION_XML = 2

# Minimum renewal interval (IEEE 2030.5 recommends not more than once per hour)
MIN_RENEWAL_INTERVAL_HOURS = 1.0

# Default renewal interval (IEEE 2030.5 recommends 24 hours)
DEFAULT_RENEWAL_INTERVAL_HOURS = 24


# ============================================
# Subscription State
# ============================================

class SubscriptionState(str, Enum):
    """Subscription lifecycle state."""
    DISABLED = "disabled"      # 未啟用
    PENDING = "pending"        # 正在建立
    ACTIVE = "active"          # 已建立
    RENEWING = "renewing"      # 正在續訂
    DELETING = "deleting"      # 正在刪除
    FAILED = "failed"          # 建立/續訂失敗


@dataclass
class TrackedSubscription:
    """
    追蹤的訂閱狀態.
    
    保存 runtime config 中的訂閱設定與伺服器回傳的資訊。
    """
    config: SubscriptionConfig
    state: SubscriptionState = SubscriptionState.DISABLED
    
    # Server-assigned subscription info (from POST response)
    subscription_href: Optional[str] = None  # Location header
    subscription_mrid: Optional[str] = None  # mRID if returned
    
    # Timing
    created_at: Optional[datetime] = None
    last_renewed_at: Optional[datetime] = None
    next_renewal_at: Optional[datetime] = None
    
    # Statistics
    renewal_count: int = 0
    failure_count: int = 0
    last_error: Optional[str] = None
    
    @property
    def is_active(self) -> bool:
        """Check if subscription is active on server."""
        return self.state == SubscriptionState.ACTIVE
    
    @property
    def should_renew(self) -> bool:
        """Check if subscription needs renewal."""
        if not self.is_active or not self.next_renewal_at:
            return False
        return datetime.now(timezone.utc) >= self.next_renewal_at
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API/logging."""
        return {
            "id": self.config.id,
            "name": self.config.name,
            "resource_uri": self.config.resource_uri,
            "state": self.state.value,
            "subscription_href": self.subscription_href,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_renewed_at": self.last_renewed_at.isoformat() if self.last_renewed_at else None,
            "next_renewal_at": self.next_renewal_at.isoformat() if self.next_renewal_at else None,
            "renewal_count": self.renewal_count,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
        }


# ============================================
# Subscription XML Builder
# ============================================

class SubscriptionXMLBuilder:
    """
    Build IEEE 2030.5 Subscription XML.
    
    IEEE 2030.5 Subscription 結構：
    - subscribedResource: 要訂閱的資源 URI
    - notificationURI: 通知端點 URI (client-side notification server)
    - encoding: 編碼類型 (0=XML, 1=EXI, 2=Application/XML)
    - level: Schema 擴展層級 (e.g., "+S2")
    - limit: 每次通知的最大資源數
    """
    
    SEP_NAMESPACE = "urn:ieee:std:2030.5:ns"
    
    @classmethod
    def build(
        cls,
        subscribed_resource: str,
        notification_uri: str,
        encoding: int = ENCODING_XML,
        level: str = "+S2",
        limit: int = 10,
        condition: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build Subscription XML for POST request.
        
        Args:
            subscribed_resource: URI of resource to subscribe to
            notification_uri: URI where server should send notifications
            encoding: Encoding type (0=XML recommended)
            level: Schema level ("+S2" for DER support)
            limit: Maximum resources per notification
            condition: Optional condition (lowerThreshold, upperThreshold, attributeIdentifier)
            
        Returns:
            XML string for Subscription resource
        """
        # Build XML without namespace prefix for cleaner output
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<Subscription xmlns="{cls.SEP_NAMESPACE}">',
            f'  <encoding>{encoding}</encoding>',
            f'  <level>{level}</level>',
            f'  <limit>{limit}</limit>',
            f'  <notificationURI>{notification_uri}</notificationURI>',
            f'  <subscribedResource>{subscribed_resource}</subscribedResource>',
        ]
        
        # Add Condition if specified
        if condition:
            lines.append('  <Condition>')
            if condition.get('attribute_identifier'):
                lines.append(f'    <attributeIdentifier>{condition["attribute_identifier"]}</attributeIdentifier>')
            if condition.get('lower_threshold') is not None:
                lines.append(f'    <lowerThreshold>{condition["lower_threshold"]}</lowerThreshold>')
            if condition.get('upper_threshold') is not None:
                lines.append(f'    <upperThreshold>{condition["upper_threshold"]}</upperThreshold>')
            lines.append('  </Condition>')
        
        lines.append('</Subscription>')
        
        return '\n'.join(lines)


# ============================================
# Subscription Manager
# ============================================

class SubscriptionManager:
    """
    IEEE 2030.5 訂閱管理器.
    
    管理訂閱的完整生命週期：
    - enable(subscription): 若尚未建立，POST 建立並保存 href
    - disable(subscription): DELETE 移除並清除本地記錄
    - reload(config): 依 enabled 清單自動 reconcile
    - on_reconnect(): 斷線恢復時的處理
    
    使用方式:
        manager = SubscriptionManager(config)
        await manager.start()
        
        # 手動啟用/停用
        await manager.enable("subscription_id")
        await manager.disable("subscription_id")
        
        # 重載設定
        await manager.reload(new_config)
        
        await manager.stop()
    """
    
    def __init__(
        self,
        config: RuntimeConfig,
        sep_client: Optional[SepClient] = None,
        simulation_mode: bool = True,
    ):
        """
        初始化訂閱管理器.
        
        Args:
            config: Runtime configuration
            sep_client: Optional SepClient instance (created if not provided)
            simulation_mode: If True, don't actually send HTTP requests
        """
        self._config = config
        self._sep_client = sep_client
        self._simulation_mode = simulation_mode
        
        # Tracked subscriptions: id -> TrackedSubscription
        self._subscriptions: Dict[str, TrackedSubscription] = {}
        
        # Profile cache: profile_name -> SepClient
        self._clients: Dict[str, SepClient] = {}
        
        # State
        self._running = False
        self._renewal_task: Optional[asyncio.Task] = None
        
        # Callbacks
        self._on_reconnect_callbacks: List[Callable[[], None]] = []
        
        # Statistics
        self._stats = {
            "subscriptions_created": 0,
            "subscriptions_deleted": 0,
            "subscriptions_renewed": 0,
            "subscriptions_failed": 0,
            "reconnects": 0,
        }
        
        # Initialize subscriptions from config
        self._init_from_config()
        
        logger.info(
            f"SubscriptionManager initialized: "
            f"{len(self._subscriptions)} subscriptions, "
            f"simulation_mode={simulation_mode}"
        )
    
    def _init_from_config(self) -> None:
        """Initialize tracked subscriptions from config."""
        for sub_config in self._config.subscriptions:
            self._subscriptions[sub_config.id] = TrackedSubscription(
                config=sub_config,
                state=SubscriptionState.DISABLED,
            )
    
    def _get_client(self, profile_name: str) -> Optional[SepClient]:
        """Get or create SepClient for profile."""
        if profile_name in self._clients:
            return self._clients[profile_name]
        
        profile = self._config.get_profile(profile_name)
        if not profile:
            logger.error(f"Profile not found: {profile_name}")
            return None
        
        client = SepClient(profile)
        self._clients[profile_name] = client
        return client
    
    def _get_notification_uri(self, sub_config: SubscriptionConfig) -> str:
        """Get notification URI for subscription."""
        # Use subscription-specific endpoint if set
        if sub_config.notification_endpoint:
            return sub_config.notification_endpoint
        
        # Otherwise use notification server config
        ns = self._config.notification_server
        if ns.public_uri:
            return f"{ns.public_uri}{ns.endpoint_path}"
        
        # Fallback to listen address
        return f"https://{ns.listen_host}:{ns.listen_port}{ns.endpoint_path}"
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    @property
    def subscriptions(self) -> Dict[str, TrackedSubscription]:
        """Get all tracked subscriptions."""
        return dict(self._subscriptions)
    
    @property
    def active_subscriptions(self) -> List[TrackedSubscription]:
        """Get all active subscriptions."""
        return [s for s in self._subscriptions.values() if s.is_active]
    
    @property
    def stats(self) -> dict:
        """Get statistics."""
        return {
            **self._stats,
            "total_subscriptions": len(self._subscriptions),
            "active_subscriptions": len(self.active_subscriptions),
        }
    
    async def start(self) -> None:
        """
        Start the subscription manager.
        
        自動啟用 config 中 enabled=True 的訂閱，
        並啟動續訂排程。
        """
        if self._running:
            logger.warning("SubscriptionManager already running")
            return
        
        logger.info("Starting SubscriptionManager...")
        self._running = True
        
        # Enable all configured subscriptions
        enabled_subs = self._config.get_enabled_subscriptions()
        for sub_config in enabled_subs:
            await self.enable(sub_config.id)
        
        # Start renewal loop
        self._renewal_task = asyncio.create_task(self._renewal_loop())
        
        logger.info(f"SubscriptionManager started: {len(self.active_subscriptions)} active")
    
    async def stop(self) -> None:
        """
        Stop the subscription manager.
        
        停止續訂排程，但不會刪除現有訂閱。
        若需要刪除訂閱，請呼叫 disable_all()。
        """
        if not self._running:
            return
        
        logger.info("Stopping SubscriptionManager...")
        self._running = False
        
        # Cancel renewal task
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass
            self._renewal_task = None
        
        # Close clients
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
        
        logger.info("SubscriptionManager stopped")
    
    async def enable(self, subscription_id: str) -> bool:
        """
        啟用訂閱.
        
        若訂閱尚未在伺服器建立，POST 到 SubscriptionList 建立。
        
        Args:
            subscription_id: 訂閱 ID
            
        Returns:
            是否成功啟用
        """
        tracked = self._subscriptions.get(subscription_id)
        if not tracked:
            logger.error(f"Subscription not found: {subscription_id}")
            return False
        
        # Already active
        if tracked.is_active:
            logger.debug(f"Subscription already active: {subscription_id}")
            return True
        
        # Create subscription on server
        tracked.state = SubscriptionState.PENDING
        
        try:
            success = await self._create_subscription(tracked)
            if success:
                tracked.state = SubscriptionState.ACTIVE
                tracked.created_at = datetime.now(timezone.utc)
                tracked.last_renewed_at = datetime.now(timezone.utc)
                tracked.failure_count = 0
                self._update_next_renewal(tracked)
                self._stats["subscriptions_created"] += 1
                logger.info(f"Subscription enabled: {subscription_id}")
                return True
            else:
                tracked.state = SubscriptionState.FAILED
                tracked.failure_count += 1
                self._stats["subscriptions_failed"] += 1
                return False
                
        except Exception as e:
            tracked.state = SubscriptionState.FAILED
            tracked.failure_count += 1
            tracked.last_error = str(e)
            self._stats["subscriptions_failed"] += 1
            logger.error(f"Failed to enable subscription {subscription_id}: {e}")
            return False
    
    async def disable(self, subscription_id: str) -> bool:
        """
        停用訂閱.
        
        DELETE 伺服器上的 Subscription 資源，並清除本地記錄。
        
        Args:
            subscription_id: 訂閱 ID
            
        Returns:
            是否成功停用
        """
        tracked = self._subscriptions.get(subscription_id)
        if not tracked:
            logger.error(f"Subscription not found: {subscription_id}")
            return False
        
        # Already disabled
        if tracked.state == SubscriptionState.DISABLED:
            logger.debug(f"Subscription already disabled: {subscription_id}")
            return True
        
        # Delete from server if we have a href
        if tracked.subscription_href:
            tracked.state = SubscriptionState.DELETING
            
            try:
                success = await self._delete_subscription(tracked)
                if not success:
                    logger.warning(f"Failed to delete subscription from server: {subscription_id}")
                    # Continue anyway to clear local state
            except Exception as e:
                logger.error(f"Error deleting subscription: {e}")
        
        # Clear local state
        tracked.state = SubscriptionState.DISABLED
        tracked.subscription_href = None
        tracked.subscription_mrid = None
        tracked.created_at = None
        tracked.last_renewed_at = None
        tracked.next_renewal_at = None
        
        self._stats["subscriptions_deleted"] += 1
        logger.info(f"Subscription disabled: {subscription_id}")
        return True
    
    async def disable_all(self) -> int:
        """
        停用所有訂閱.
        
        Returns:
            成功停用的數量
        """
        count = 0
        for sub_id in list(self._subscriptions.keys()):
            if await self.disable(sub_id):
                count += 1
        return count
    
    async def reload(self, new_config: RuntimeConfig) -> None:
        """
        重載設定並自動 reconcile.
        
        比較新舊設定：
        - 新設定中 enabled 但未啟用 -> 啟用
        - 新設定中 disabled 但已啟用 -> 停用
        - 新設定中不存在 -> 停用並移除
        - 新增的訂閱 -> 加入追蹤
        
        Args:
            new_config: 新的 RuntimeConfig
        """
        logger.info("Reloading subscription configuration...")
        
        old_ids = set(self._subscriptions.keys())
        new_ids = {s.id for s in new_config.subscriptions}
        
        # Find subscriptions to remove
        to_remove = old_ids - new_ids
        for sub_id in to_remove:
            await self.disable(sub_id)
            del self._subscriptions[sub_id]
            logger.info(f"Removed subscription: {sub_id}")
        
        # Update config reference
        self._config = new_config
        
        # Add new subscriptions
        for sub_config in new_config.subscriptions:
            if sub_config.id not in self._subscriptions:
                self._subscriptions[sub_config.id] = TrackedSubscription(
                    config=sub_config,
                    state=SubscriptionState.DISABLED,
                )
                logger.info(f"Added subscription: {sub_config.id}")
            else:
                # Update config for existing subscription
                self._subscriptions[sub_config.id].config = sub_config
        
        # Reconcile enabled state
        for sub_config in new_config.subscriptions:
            tracked = self._subscriptions[sub_config.id]
            
            if sub_config.enabled and not tracked.is_active:
                await self.enable(sub_config.id)
            elif not sub_config.enabled and tracked.is_active:
                await self.disable(sub_config.id)
        
        logger.info(
            f"Reload complete: {len(self.active_subscriptions)} active subscriptions"
        )
    
    def on_reconnect(self) -> None:
        """
        斷線恢復時的處理.
        
        IEEE 2030.5 規範建議：恢復連線後應重新 poll 關注資源。
        此方法觸發已註冊的回調函數。
        """
        logger.info("Connection restored - triggering on_reconnect handlers")
        self._stats["reconnects"] += 1
        
        for callback in self._on_reconnect_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in on_reconnect callback: {e}")
        
        # Mark all active subscriptions for renewal
        for tracked in self._subscriptions.values():
            if tracked.is_active:
                # Force renewal on next check
                tracked.next_renewal_at = datetime.now(timezone.utc)
    
    def register_on_reconnect(self, callback: Callable[[], None]) -> None:
        """
        註冊斷線恢復回調.
        
        Args:
            callback: 斷線恢復時呼叫的函數
        """
        self._on_reconnect_callbacks.append(callback)
    
    # =========================================================================
    # Internal Operations
    # =========================================================================
    
    async def _create_subscription(self, tracked: TrackedSubscription) -> bool:
        """
        Create subscription on server via POST.
        
        POST /edev/{id}/sub
        Content-Type: application/sep+xml
        Body: <Subscription>...</Subscription>
        
        Success: 201 Created with Location header
        """
        config = tracked.config
        
        # Simulation mode
        if self._simulation_mode:
            logger.info(
                f"[SIMULATION] POST subscription: "
                f"resource={config.resource_uri}, "
                f"notification={self._get_notification_uri(config)}"
            )
            # Simulate server response
            tracked.subscription_href = f"/sub/sim-{config.id}"
            return True
        
        # Get client
        client = self._get_client(config.profile_name)
        if not client:
            tracked.last_error = f"Profile not found: {config.profile_name}"
            return False
        
        # Build subscription XML
        condition = None
        if config.conditions:
            condition = {
                "lower_threshold": config.conditions.lower_threshold,
                "upper_threshold": config.conditions.upper_threshold,
                "attribute_identifier": config.conditions.attribute_identifier,
            }
        
        xml_body = SubscriptionXMLBuilder.build(
            subscribed_resource=config.resource_uri,
            notification_uri=self._get_notification_uri(config),
            encoding=ENCODING_XML,
            level="+S2",
            limit=10,
            condition=condition,
        )
        
        # Determine subscription list URI
        # Convention: resource_uri + "/sub" for subscription list
        # e.g., /edev/1/der -> /edev/1/sub
        sub_list_uri = self._get_subscription_list_uri(config.resource_uri)
        
        try:
            response = await client.post(sub_list_uri, xml_body)
            
            if response.is_created:
                # Extract subscription href from Location header
                location = response.headers.get("location") or response.headers.get("Location")
                if location:
                    tracked.subscription_href = location
                    logger.info(
                        f"Subscription created: {config.id} -> {location}"
                    )
                else:
                    # Try to extract from response body
                    tracked.subscription_href = self._extract_href_from_response(response.body)
                    logger.warning(
                        f"Subscription created but no Location header: {config.id}"
                    )
                return True
            else:
                tracked.last_error = f"HTTP {response.status_code}: {response.body[:200]}"
                logger.error(
                    f"Failed to create subscription: {tracked.last_error}"
                )
                return False
                
        except SepClientError as e:
            tracked.last_error = str(e)
            logger.error(f"Error creating subscription: {e}")
            return False
    
    async def _delete_subscription(self, tracked: TrackedSubscription) -> bool:
        """
        Delete subscription from server via DELETE.
        
        DELETE /edev/{id}/sub/{sub_id}
        
        Success: 204 No Content
        """
        if not tracked.subscription_href:
            return True  # Nothing to delete
        
        config = tracked.config
        
        # Simulation mode
        if self._simulation_mode:
            logger.info(
                f"[SIMULATION] DELETE subscription: {tracked.subscription_href}"
            )
            return True
        
        # Get client
        client = self._get_client(config.profile_name)
        if not client:
            tracked.last_error = f"Profile not found: {config.profile_name}"
            return False
        
        try:
            response = await client.delete(tracked.subscription_href)
            
            if response.status_code in (200, 204):
                logger.info(f"Subscription deleted: {tracked.subscription_href}")
                return True
            elif response.is_not_found:
                # Already deleted
                logger.debug(f"Subscription already gone: {tracked.subscription_href}")
                return True
            else:
                tracked.last_error = f"HTTP {response.status_code}"
                logger.error(
                    f"Failed to delete subscription: {tracked.last_error}"
                )
                return False
                
        except SepClientError as e:
            tracked.last_error = str(e)
            logger.error(f"Error deleting subscription: {e}")
            return False
    
    async def _renew_subscription(self, tracked: TrackedSubscription) -> bool:
        """
        Renew subscription by re-POSTing.
        
        IEEE 2030.5 doesn't have explicit renewal - we delete and recreate.
        Alternatively, some servers support updating the subscription.
        """
        config = tracked.config
        
        # Simulation mode
        if self._simulation_mode:
            logger.info(f"[SIMULATION] Renew subscription: {config.id}")
            tracked.last_renewed_at = datetime.now(timezone.utc)
            tracked.renewal_count += 1
            self._update_next_renewal(tracked)
            self._stats["subscriptions_renewed"] += 1
            return True
        
        # Strategy: Delete and recreate
        # This ensures server has fresh subscription
        old_state = tracked.state
        tracked.state = SubscriptionState.RENEWING
        
        try:
            # Delete existing
            if tracked.subscription_href:
                await self._delete_subscription(tracked)
            
            # Create new
            success = await self._create_subscription(tracked)
            
            if success:
                tracked.state = SubscriptionState.ACTIVE
                tracked.last_renewed_at = datetime.now(timezone.utc)
                tracked.renewal_count += 1
                self._update_next_renewal(tracked)
                self._stats["subscriptions_renewed"] += 1
                logger.info(f"Subscription renewed: {config.id}")
                return True
            else:
                tracked.state = SubscriptionState.FAILED
                self._stats["subscriptions_failed"] += 1
                return False
                
        except Exception as e:
            tracked.state = SubscriptionState.FAILED
            tracked.last_error = str(e)
            self._stats["subscriptions_failed"] += 1
            logger.error(f"Failed to renew subscription {config.id}: {e}")
            return False
    
    def _update_next_renewal(self, tracked: TrackedSubscription) -> None:
        """Calculate and set next renewal time."""
        # Get renewal interval, enforce minimum
        interval_hours = max(
            tracked.config.renew_interval_hours,
            MIN_RENEWAL_INTERVAL_HOURS,
        )
        
        # Calculate next renewal
        from datetime import timedelta
        tracked.next_renewal_at = datetime.now(timezone.utc) + timedelta(hours=interval_hours)
    
    def _get_subscription_list_uri(self, resource_uri: str) -> str:
        """
        Get subscription list URI from resource URI.
        
        Convention varies by server, common patterns:
        - /edev/{id}/sub (EndDevice subscriptions)
        - Resource URI parent + /sub
        """
        # Simple heuristic: go up one level and append /sub
        parts = resource_uri.rstrip('/').rsplit('/', 1)
        if len(parts) > 1:
            return f"{parts[0]}/sub"
        return "/sub"
    
    def _extract_href_from_response(self, body: str) -> Optional[str]:
        """Extract href from Subscription response XML."""
        try:
            # Strip namespaces for easier parsing
            import re
            clean_body = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', body)
            clean_body = re.sub(r'<(\/?)\w+:', r'<\1', clean_body)
            
            root = ET.fromstring(clean_body)
            href = root.get('href')
            if href:
                return href
            
            # Try finding href element
            href_elem = root.find('.//href')
            if href_elem is not None and href_elem.text:
                return href_elem.text
                
        except Exception as e:
            logger.debug(f"Could not extract href from response: {e}")
        
        return None
    
    async def _renewal_loop(self) -> None:
        """Background loop to check and renew subscriptions."""
        logger.info("Subscription renewal loop started")
        
        while self._running:
            try:
                # Check each subscription
                for tracked in self._subscriptions.values():
                    if tracked.should_renew:
                        logger.info(f"Renewing subscription: {tracked.config.id}")
                        await self._renew_subscription(tracked)
                
                # Check every minute
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in renewal loop: {e}")
                await asyncio.sleep(60)
        
        logger.info("Subscription renewal loop stopped")


# ============================================
# Factory Function
# ============================================

def create_subscription_manager(
    config: RuntimeConfig,
    simulation_mode: bool = True,
) -> SubscriptionManager:
    """
    Create a SubscriptionManager instance.
    
    Args:
        config: Runtime configuration
        simulation_mode: If True, don't send actual HTTP requests
        
    Returns:
        Configured SubscriptionManager
    """
    return SubscriptionManager(
        config=config,
        simulation_mode=simulation_mode,
    )
