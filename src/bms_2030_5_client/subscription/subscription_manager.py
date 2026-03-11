"""
Subscription Manager (訂閱管理器)

管理 IEEE 2030.5 訂閱的生命週期：
- 建立完整訂閱鏈 (FSA → DERProgram → DERControl)
- 追蹤活動訂閱
- 處理 FSA 變更時的重新訂閱
- 定期續訂訂閱 (每 24 小時)

Reference: IEEE Std 2030.5-2023, Clause 8.9

使用方式:
    manager = SubscriptionManager(
        http_client=ieee_client,
        notification_uri="https://client:8443/notify",
    )
    await manager.setup_subscriptions()
    # ... 運行中 ...
    await manager.cleanup()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Set, Awaitable, TYPE_CHECKING

from bms_2030_5_client.models import (
    Subscription,
    SubscriptionList,
    SubscriptionEncodingType,
    FunctionSetAssignments,
    FunctionSetAssignmentsList,
    DERProgram,
    DERProgramList,
    Notification,
    NotificationStatusType,
)

if TYPE_CHECKING:
    from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client

logger = logging.getLogger(__name__)


class SubscriptionType(Enum):
    """訂閱類型"""
    FSA = "fsa"               # FunctionSetAssignments 清單
    DERP = "derp"             # DERProgram 清單
    DERC = "derc"             # DERControl 清單
    DDERC = "dderc"           # DefaultDERControl


@dataclass
class TrackedSubscription:
    """追蹤的訂閱"""
    resource_path: str                          # 訂閱的資源路徑
    subscription_href: Optional[str] = None     # 伺服器回傳的訂閱 href
    subscription_type: SubscriptionType = SubscriptionType.DERC
    created_time: float = field(default_factory=time.time)
    last_renewed_time: float = field(default_factory=time.time)
    is_active: bool = True
    
    @property
    def age_hours(self) -> float:
        """訂閱已存在的時間（小時）"""
        return (time.time() - self.created_time) / 3600
    
    @property
    def hours_since_renewal(self) -> float:
        """距離上次續訂的時間（小時）"""
        return (time.time() - self.last_renewed_time) / 3600


@dataclass
class SubscriptionManagerConfig:
    """訂閱管理器配置"""
    
    # 續訂間隔（小時）- IEEE 2030.5 建議 24 小時
    renewal_interval_hours: float = 24.0
    
    # 最小續訂間隔（小時）- IEEE 2030.5 規定不超過每小時
    min_renewal_interval_hours: float = 1.0
    
    # 訂閱編碼格式
    encoding: int = SubscriptionEncodingType.XML
    
    # Schema 擴展層級
    level: str = "+S2"
    
    # 每次通知的最大資源數
    limit: int = 10
    
    # 重試次數
    max_retries: int = 3
    
    # 是否自動重新訂閱失敗的訂閱
    auto_resubscribe: bool = True


class SubscriptionManager:
    """
    IEEE 2030.5 訂閱管理器
    
    管理完整訂閱鏈：
    
    1. `/edev/{id}/fsa` - FSA 清單（偵測設備重新分配）
    2. `/fsa/{id}/derp` - DERProgram 清單（偵測程式變更）
    3. `/derp/{id}/derc` - DERControl 清單（主要：功率控制通知）
    4. `/derp/{id}/dderc` - DefaultDERControl（預設控制變更）
    
    使用方式:
        manager = SubscriptionManager(
            http_client=ieee_client,
            notification_uri="https://client:8443/notify",
        )
        
        # 設定處理回調
        manager.set_on_fsa_changed(handle_fsa_change)
        manager.set_on_control_received(handle_control)
        
        # 建立訂閱鏈
        await manager.setup_subscriptions()
        
        # 啟動續訂迴圈
        await manager.start_renewal_loop()
    """
    
    def __init__(
        self,
        http_client: "IEEE2030_5Client",
        notification_uri: str,
        config: Optional[SubscriptionManagerConfig] = None,
    ):
        """
        初始化訂閱管理器
        
        Args:
            http_client: IEEE 2030.5 HTTP 客戶端
            notification_uri: 接收通知的 URI (例如 https://client:8443/notify)
            config: 管理器配置
        """
        self.http_client = http_client
        self.notification_uri = notification_uri
        self.config = config or SubscriptionManagerConfig()
        
        # 追蹤的訂閱
        self._subscriptions: Dict[str, TrackedSubscription] = {}
        
        # 追蹤的 FSA 和 Program
        self._tracked_fsa: Dict[str, FunctionSetAssignments] = {}
        self._tracked_programs: Dict[str, DERProgram] = {}
        
        # 續訂任務
        self._renewal_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 回調
        self._on_fsa_changed: Optional[Callable[[List[FunctionSetAssignments]], Awaitable[None]]] = None
        self._on_program_changed: Optional[Callable[[List[DERProgram]], Awaitable[None]]] = None
        
        # 統計
        self._stats = {
            "subscriptions_created": 0,
            "subscriptions_renewed": 0,
            "subscriptions_failed": 0,
            "resubscriptions": 0,
        }
        
        logger.info(f"SubscriptionManager initialized, notification_uri={notification_uri}")
    
    @property
    def subscriptions(self) -> Dict[str, TrackedSubscription]:
        """取得所有追蹤的訂閱"""
        return dict(self._subscriptions)
    
    @property
    def stats(self) -> dict:
        """取得統計資料"""
        return dict(self._stats)
    
    def set_on_fsa_changed(
        self,
        callback: Callable[[List[FunctionSetAssignments]], Awaitable[None]]
    ) -> None:
        """設定 FSA 變更回調"""
        self._on_fsa_changed = callback
    
    def set_on_program_changed(
        self,
        callback: Callable[[List[DERProgram]], Awaitable[None]]
    ) -> None:
        """設定 DERProgram 變更回調"""
        self._on_program_changed = callback
    
    # =========================================================================
    # Subscription Setup (訂閱設定)
    # =========================================================================
    
    async def setup_subscriptions(self) -> bool:
        """
        建立完整訂閱鏈
        
        流程:
        1. 取得 EndDevice
        2. 訂閱 FSA 清單
        3. 取得 FSA 並訂閱各 DERProgram 清單
        4. 取得 DERProgram 並訂閱 DERControl/DefaultDERControl
        
        Returns:
            是否成功建立至少一個訂閱
        """
        logger.info("Setting up subscription chain...")
        
        # 取得 EndDevice
        end_device = self.http_client._end_device
        if not end_device:
            logger.error("EndDevice not available, cannot setup subscriptions")
            return False
        
        edev_href = end_device.href
        if not edev_href:
            logger.error("EndDevice href not available")
            return False
        
        # 1. 訂閱 FSA 清單
        fsa_list_link = end_device.FunctionSetAssignmentsListLink
        if fsa_list_link:
            fsa_href = fsa_list_link.href if hasattr(fsa_list_link, 'href') else fsa_list_link
            if fsa_href:
                await self._subscribe(
                    resource_path=fsa_href,
                    subscription_type=SubscriptionType.FSA,
                    edev_href=edev_href
                )
        
        # 2. 取得 FSA 並設定 DERProgram 訂閱
        await self._setup_program_subscriptions(edev_href)
        
        subscription_count = len(self._subscriptions)
        logger.info(f"Subscription chain setup complete: {subscription_count} subscriptions")
        
        return subscription_count > 0
    
    async def _setup_program_subscriptions(self, edev_href: str) -> None:
        """設定 DERProgram 相關訂閱"""
        # 取得 FSA 清單
        fsa_list = await self._get_fsa_list()
        if not fsa_list:
            logger.warning("No FSA available")
            return
        
        for fsa in fsa_list:
            fsa_id = fsa.mRID or fsa.href or str(id(fsa))
            self._tracked_fsa[fsa_id] = fsa
            
            # 訂閱 DERProgram 清單
            derp_href = fsa.get_der_program_list_href()
            if derp_href:
                await self._subscribe(
                    resource_path=derp_href,
                    subscription_type=SubscriptionType.DERP,
                    edev_href=edev_href
                )
            
            # 取得 DERProgram 並訂閱控制
            await self._setup_control_subscriptions(fsa, edev_href)
    
    async def _setup_control_subscriptions(
        self,
        fsa: FunctionSetAssignments,
        edev_href: str
    ) -> None:
        """設定 DERControl 相關訂閱"""
        derp_href = fsa.get_der_program_list_href()
        if not derp_href:
            return
        
        try:
            program_list = await self.http_client._get(
                derp_href,
                DERProgramList
            )
            
            if not program_list or not program_list.DERProgram:
                return
            
            for program in program_list.DERProgram:
                prog_id = program.mRID or program.href or str(id(program))
                self._tracked_programs[prog_id] = program
                
                # 訂閱 DERControlList（非 ActiveDERControlListLink - 已棄用）
                derc_href = program.get_der_control_list_href()
                if derc_href:
                    await self._subscribe(
                        resource_path=derc_href,
                        subscription_type=SubscriptionType.DERC,
                        edev_href=edev_href
                    )
                
                # 訂閱 DefaultDERControl
                dderc_href = program.get_default_der_control_href()
                if dderc_href:
                    await self._subscribe(
                        resource_path=dderc_href,
                        subscription_type=SubscriptionType.DDERC,
                        edev_href=edev_href
                    )
        
        except Exception as e:
            logger.error(f"Failed to setup control subscriptions: {e}")
    
    async def _get_fsa_list(self) -> List[FunctionSetAssignments]:
        """取得 FSA 清單"""
        end_device = self.http_client._end_device
        if not end_device:
            return []
        
        fsa_link = end_device.FunctionSetAssignmentsListLink
        if not fsa_link:
            return []
        
        fsa_href = fsa_link.href if hasattr(fsa_link, 'href') else fsa_link
        if not fsa_href:
            return []
        
        try:
            fsa_list = await self.http_client._get(
                fsa_href,
                FunctionSetAssignmentsList
            )
            return fsa_list.FunctionSetAssignments if fsa_list else []
        except Exception as e:
            logger.error(f"Failed to get FSA list: {e}")
            return []
    
    # =========================================================================
    # Subscription Operations (訂閱操作)
    # =========================================================================
    
    async def _subscribe(
        self,
        resource_path: str,
        subscription_type: SubscriptionType,
        edev_href: str
    ) -> Optional[TrackedSubscription]:
        """
        建立訂閱
        
        Args:
            resource_path: 要訂閱的資源路徑
            subscription_type: 訂閱類型
            edev_href: EndDevice href (用於 POST 訂閱)
        
        Returns:
            TrackedSubscription 或 None
        """
        # 檢查是否已訂閱
        if resource_path in self._subscriptions:
            existing = self._subscriptions[resource_path]
            if existing.is_active:
                logger.debug(f"Already subscribed to {resource_path}")
                return existing
        
        logger.info(f"Subscribing to {resource_path} ({subscription_type.value})")
        
        # 建立訂閱請求
        subscription = Subscription(
            subscribedResource=resource_path,
            notificationURI=self.notification_uri,
            encoding=self.config.encoding,
            level=self.config.level,
            limit=self.config.limit,
        )
        
        # 發送訂閱請求 (POST to /edev/{id}/sub)
        sub_list_path = f"{edev_href}/sub"
        
        try:
            _, location = await self.http_client._post(
                sub_list_path,
                subscription
            )
            
            if location:
                tracked = TrackedSubscription(
                    resource_path=resource_path,
                    subscription_href=location,
                    subscription_type=subscription_type,
                )
                self._subscriptions[resource_path] = tracked
                self._stats["subscriptions_created"] += 1
                
                logger.info(f"Subscribed to {resource_path} -> {location}")
                return tracked
            else:
                logger.warning(f"Subscription created but no location returned: {resource_path}")
                # 仍然追蹤，但沒有 href
                tracked = TrackedSubscription(
                    resource_path=resource_path,
                    subscription_type=subscription_type,
                )
                self._subscriptions[resource_path] = tracked
                self._stats["subscriptions_created"] += 1
                return tracked
        
        except Exception as e:
            logger.error(f"Failed to subscribe to {resource_path}: {e}")
            self._stats["subscriptions_failed"] += 1
            return None
    
    async def _unsubscribe(self, resource_path: str) -> bool:
        """
        取消訂閱
        
        Args:
            resource_path: 資源路徑
        
        Returns:
            是否成功
        """
        if resource_path not in self._subscriptions:
            return False
        
        tracked = self._subscriptions[resource_path]
        
        if tracked.subscription_href:
            try:
                # DELETE 訂閱
                response = await self.http_client._client.delete(
                    tracked.subscription_href
                )
                if response.status_code in (200, 204, 404):
                    logger.info(f"Unsubscribed from {resource_path}")
            except Exception as e:
                logger.warning(f"Failed to delete subscription: {e}")
        
        del self._subscriptions[resource_path]
        return True
    
    async def _renew_subscription(self, tracked: TrackedSubscription) -> bool:
        """
        續訂訂閱
        
        Args:
            tracked: 追蹤的訂閱
        
        Returns:
            是否成功
        """
        if not tracked.subscription_href:
            logger.warning(f"Cannot renew subscription without href: {tracked.resource_path}")
            return False
        
        try:
            # GET 訂閱以續訂
            response = await self.http_client._client.get(tracked.subscription_href)
            
            if response.status_code == 200:
                tracked.last_renewed_time = time.time()
                self._stats["subscriptions_renewed"] += 1
                logger.debug(f"Renewed subscription: {tracked.resource_path}")
                return True
            elif response.status_code == 404:
                # 訂閱已過期，需要重新訂閱
                logger.warning(f"Subscription expired: {tracked.resource_path}")
                tracked.is_active = False
                
                if self.config.auto_resubscribe:
                    # 重新訂閱
                    end_device = self.http_client._end_device
                    if end_device and end_device.href:
                        new_tracked = await self._subscribe(
                            resource_path=tracked.resource_path,
                            subscription_type=tracked.subscription_type,
                            edev_href=end_device.href
                        )
                        if new_tracked:
                            self._stats["resubscriptions"] += 1
                            return True
                
                return False
            else:
                logger.error(f"Renewal failed with status {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Failed to renew subscription: {e}")
            return False
    
    # =========================================================================
    # FSA Change Handling (FSA 變更處理)
    # =========================================================================
    
    async def handle_fsa_change(self, notification: Notification) -> None:
        """
        處理 FSA 變更通知
        
        當設備被重新分配到不同站點時，需要重新訂閱新的 DERProgram。
        
        Args:
            notification: FSA 變更通知
        """
        logger.info("FSA changed, re-discovering programs...")
        
        # 取得新的 FSA 清單
        new_fsa_list = await self._get_fsa_list()
        
        if not new_fsa_list:
            logger.warning("No FSA after change")
            return
        
        # 找出新舊 FSA 的差異
        old_fsa_ids = set(self._tracked_fsa.keys())
        new_fsa_ids = set(
            fsa.mRID or fsa.href or str(id(fsa))
            for fsa in new_fsa_list
        )
        
        # 取消訂閱已移除的 FSA
        removed_fsa_ids = old_fsa_ids - new_fsa_ids
        for fsa_id in removed_fsa_ids:
            await self._handle_fsa_removed(fsa_id)
        
        # 訂閱新的 FSA
        added_fsa_ids = new_fsa_ids - old_fsa_ids
        if added_fsa_ids:
            end_device = self.http_client._end_device
            if end_device and end_device.href:
                for fsa in new_fsa_list:
                    fsa_id = fsa.mRID or fsa.href or str(id(fsa))
                    if fsa_id in added_fsa_ids:
                        self._tracked_fsa[fsa_id] = fsa
                        await self._setup_control_subscriptions(fsa, end_device.href)
        
        # 更新追蹤
        self._tracked_fsa = {
            fsa.mRID or fsa.href or str(id(fsa)): fsa
            for fsa in new_fsa_list
        }
        
        # 回調
        if self._on_fsa_changed:
            await self._on_fsa_changed(new_fsa_list)
        
        logger.info(f"FSA change handled: removed={len(removed_fsa_ids)}, added={len(added_fsa_ids)}")
    
    async def _handle_fsa_removed(self, fsa_id: str) -> None:
        """處理 FSA 移除"""
        if fsa_id not in self._tracked_fsa:
            return
        
        fsa = self._tracked_fsa[fsa_id]
        
        # 取消訂閱相關的 DERProgram
        derp_href = fsa.get_der_program_list_href()
        if derp_href:
            await self._unsubscribe(derp_href)
        
        # 移除追蹤的程式
        programs_to_remove = []
        for prog_id, program in self._tracked_programs.items():
            # 簡化：移除所有相關訂閱
            derc_href = program.get_der_control_list_href()
            if derc_href:
                await self._unsubscribe(derc_href)
            dderc_href = program.get_default_der_control_href()
            if dderc_href:
                await self._unsubscribe(dderc_href)
            programs_to_remove.append(prog_id)
        
        for prog_id in programs_to_remove:
            if prog_id in self._tracked_programs:
                del self._tracked_programs[prog_id]
        
        del self._tracked_fsa[fsa_id]
    
    # =========================================================================
    # Notification Status Handling (通知狀態處理)
    # =========================================================================
    
    async def handle_notification_status(self, notification: Notification) -> None:
        """
        處理通知狀態
        
        當 status != 0 時，表示訂閱出現問題。
        
        Args:
            notification: 通知
        """
        if notification.status == NotificationStatusType.DEFAULT:
            return
        
        resource_path = notification.subscribedResource
        
        logger.warning(
            f"Subscription status error: "
            f"resource={resource_path}, status={notification.status}"
        )
        
        # 移除失敗的訂閱
        if resource_path in self._subscriptions:
            tracked = self._subscriptions[resource_path]
            tracked.is_active = False
            del self._subscriptions[resource_path]
        
        # 自動重新訂閱
        if self.config.auto_resubscribe:
            end_device = self.http_client._end_device
            if end_device and end_device.href:
                # 需要確定訂閱類型
                sub_type = self._determine_subscription_type(resource_path)
                await self._subscribe(
                    resource_path=resource_path,
                    subscription_type=sub_type,
                    edev_href=end_device.href
                )
                self._stats["resubscriptions"] += 1
    
    def _determine_subscription_type(self, resource_path: str) -> SubscriptionType:
        """根據路徑確定訂閱類型"""
        if "/fsa" in resource_path:
            return SubscriptionType.FSA
        elif "/derp" in resource_path and "/derc" not in resource_path:
            return SubscriptionType.DERP
        elif "/dderc" in resource_path:
            return SubscriptionType.DDERC
        else:
            return SubscriptionType.DERC
    
    # =========================================================================
    # Renewal Loop (續訂迴圈)
    # =========================================================================
    
    async def start_renewal_loop(self) -> None:
        """啟動訂閱續訂迴圈"""
        if self._running:
            return
        
        self._running = True
        self._renewal_task = asyncio.create_task(self._renewal_loop())
        logger.info("Subscription renewal loop started")
    
    async def stop_renewal_loop(self) -> None:
        """停止續訂迴圈"""
        self._running = False
        
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Subscription renewal loop stopped")
    
    async def _renewal_loop(self) -> None:
        """訂閱續訂迴圈"""
        # 計算檢查間隔（每小時檢查一次）
        check_interval_s = 3600  # 1 hour
        
        while self._running:
            try:
                await self._check_renewals()
            except Exception as e:
                logger.error(f"Renewal loop error: {e}")
            
            await asyncio.sleep(check_interval_s)
    
    async def _check_renewals(self) -> None:
        """檢查需要續訂的訂閱"""
        renewal_threshold_hours = self.config.renewal_interval_hours
        
        for resource_path, tracked in list(self._subscriptions.items()):
            if not tracked.is_active:
                continue
            
            if tracked.hours_since_renewal >= renewal_threshold_hours:
                logger.info(f"Renewing subscription: {resource_path}")
                await self._renew_subscription(tracked)
    
    # =========================================================================
    # Cleanup (清理)
    # =========================================================================
    
    async def cleanup(self) -> None:
        """清理所有訂閱"""
        logger.info("Cleaning up subscriptions...")
        
        await self.stop_renewal_loop()
        
        # 取消所有訂閱
        for resource_path in list(self._subscriptions.keys()):
            await self._unsubscribe(resource_path)
        
        self._tracked_fsa.clear()
        self._tracked_programs.clear()
        
        logger.info("Subscription cleanup complete")
