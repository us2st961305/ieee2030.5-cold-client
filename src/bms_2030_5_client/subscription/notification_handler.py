"""
Notification Handler (通知處理器)

處理來自 IEEE 2030.5 伺服器的各種通知類型：
- DERControl 通知
- DefaultDERControl 通知
- FSA 變更通知
- DERProgram 變更通知

Reference: IEEE Std 2030.5-2023, Clause 8.9

使用方式:
    handler = NotificationHandler(
        subscription_manager=sub_manager,
        control_handler=der_control_handler,
    )
    
    # 設定給通知服務器
    notification_server.set_notification_handler(handler.handle_notification)
"""

from __future__ import annotations

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring as _safe_fromstring
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional, TYPE_CHECKING

from bms_2030_5_client.models import (
    Notification,
    NotificationStatusType,
    DERControl,
    DERControlList,
    DefaultDERControl,
    DERProgram,
    FunctionSetAssignments,
    DERControlResponseFull,
    ResponseStatusType,
    DERControlModesType,
)
from bms_2030_5_client.ieee2030_5.xml_utils import xml_to_dataclass

if TYPE_CHECKING:
    from bms_2030_5_client.subscription.subscription_manager import SubscriptionManager
    from bms_2030_5_client.dera.handler import DERControlHandler
    from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client

logger = logging.getLogger(__name__)


# IEEE 2030.5 XML 命名空間
IEEE2030_5_NS = "urn:ieee:std:2030.5:ns"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


@dataclass
class NotificationHandlerConfig:
    """通知處理器配置"""
    
    # 是否自動發送 DERControlResponse
    auto_send_response: bool = True
    
    # Response 發送超時（秒）
    response_timeout_s: float = 30.0
    
    # 是否記錄所有通知
    log_all_notifications: bool = True


# Type alias for control callback
ControlReceivedCallback = Callable[[DERControl], Awaitable[None]]
DefaultControlCallback = Callable[[DefaultDERControl], Awaitable[None]]


class NotificationHandler:
    """
    IEEE 2030.5 通知處理器
    
    根據 subscribedResource 路徑分派通知到適當的處理函數。
    
    處理流程:
    1. 檢查通知狀態 (status != 0 表示訂閱問題)
    2. 根據路徑類型路由通知
    3. 解析嵌入的 Resource XML
    4. 執行控制或更新狀態
    5. 發送 DERControlResponse (如需要)
    
    使用方式:
        handler = NotificationHandler(
            http_client=ieee_client,
            subscription_manager=sub_manager,
        )
        
        # 設定控制回調
        handler.set_on_control_received(my_control_handler)
        
        # 處理通知
        await handler.handle_notification(notification, raw_xml)
    """
    
    def __init__(
        self,
        http_client: "IEEE2030_5Client",
        subscription_manager: Optional["SubscriptionManager"] = None,
        control_handler: Optional["DERControlHandler"] = None,
        config: Optional[NotificationHandlerConfig] = None,
    ):
        """
        初始化通知處理器
        
        Args:
            http_client: IEEE 2030.5 HTTP 客戶端
            subscription_manager: 訂閱管理器 (用於 FSA 變更處理)
            control_handler: DER 控制處理器 (用於執行控制)
            config: 處理器配置
        """
        self.http_client = http_client
        self.subscription_manager = subscription_manager
        self.control_handler = control_handler
        self.config = config or NotificationHandlerConfig()
        
        # 回調
        self._on_control_received: Optional[ControlReceivedCallback] = None
        self._on_default_control: Optional[DefaultControlCallback] = None
        
        # 統計
        self._stats = {
            "notifications_handled": 0,
            "controls_received": 0,
            "responses_sent": 0,
            "errors": 0,
        }
        
        logger.info("NotificationHandler initialized")
    
    @property
    def stats(self) -> dict:
        """取得統計資料"""
        return dict(self._stats)
    
    def set_on_control_received(self, callback: ControlReceivedCallback) -> None:
        """設定 DERControl 接收回調"""
        self._on_control_received = callback
    
    def set_on_default_control(self, callback: DefaultControlCallback) -> None:
        """設定 DefaultDERControl 接收回調"""
        self._on_default_control = callback
    
    # =========================================================================
    # Main Handler (主處理函數)
    # =========================================================================
    
    async def handle_notification(
        self,
        notification: Notification,
        raw_xml: str
    ) -> None:
        """
        處理通知
        
        Args:
            notification: 解析後的通知物件
            raw_xml: 原始 XML 字串 (用於提取嵌入資源)
        """
        self._stats["notifications_handled"] += 1
        
        if self.config.log_all_notifications:
            logger.info(
                f"Handling notification: "
                f"resource={notification.subscribedResource}, "
                f"status={notification.status}, "
                f"newURI={notification.newResourceURI}"
            )
        
        # 1. 檢查通知狀態
        if notification.status != NotificationStatusType.DEFAULT:
            await self._handle_subscription_error(notification)
            return
        
        # 2. 根據路徑類型路由
        resource_path = notification.subscribedResource
        
        if "/derc" in resource_path and "/dderc" not in resource_path:
            # DERControl 通知
            await self._handle_der_control_notification(notification, raw_xml)
        
        elif "/dderc" in resource_path:
            # DefaultDERControl 通知
            await self._handle_default_control_notification(notification, raw_xml)
        
        elif "/fsa" in resource_path:
            # FSA 變更通知
            await self._handle_fsa_notification(notification, raw_xml)
        
        elif "/derp" in resource_path:
            # DERProgram 變更通知
            await self._handle_program_notification(notification, raw_xml)
        
        else:
            logger.warning(f"Unknown notification type: {resource_path}")
    
    # =========================================================================
    # DERControl Handling (DERControl 處理)
    # =========================================================================
    
    async def _handle_der_control_notification(
        self,
        notification: Notification,
        raw_xml: str
    ) -> None:
        """處理 DERControl 通知"""
        logger.info(f"Received DERControl notification: {notification.newResourceURI}")
        
        # 解析嵌入的 DERControl
        control = self._extract_der_control(raw_xml)
        
        if not control:
            logger.error("Failed to extract DERControl from notification")
            self._stats["errors"] += 1
            return
        
        self._stats["controls_received"] += 1
        
        logger.info(
            f"DERControl received: "
            f"mRID={control.mRID}, "
            f"power={control.get_power_setpoint_w()}W"
        )
        
        # 檢查控制是否有效
        now = int(time.time())
        if control.interval:
            start = control.interval.start
            end = start + control.interval.duration
            
            if now < start:
                logger.info(f"Control scheduled for future: starts in {start - now}s")
            elif now >= end:
                logger.info(f"Control already expired, ignoring")
                return
        
        # 發送 "Event Received" 回應
        if self.config.auto_send_response:
            await self._send_control_response(
                control,
                ResponseStatusType.EVENT_RECEIVED
            )
        
        # 執行控制
        if self.control_handler:
            await self.control_handler.handle_control(control, source="notification")
            
            # 發送 "Event Started" 回應
            if self.config.auto_send_response:
                await self._send_control_response(
                    control,
                    ResponseStatusType.EVENT_STARTED
                )
        
        # 回調
        if self._on_control_received:
            try:
                await self._on_control_received(control)
            except Exception as e:
                logger.exception(f"Control callback error: {e}")
    
    def _extract_der_control(self, raw_xml: str) -> Optional[DERControl]:
        """從通知 XML 中提取 DERControl"""
        try:
            root = _safe_fromstring(raw_xml)
            
            # 尋找 Resource 元素
            for child in root:
                tag = self._strip_ns(child.tag)
                if tag == "Resource":
                    # 檢查 xsi:type
                    xsi_type = child.get(f"{{{XSI_NS}}}type", "")
                    
                    if "DERControl" in xsi_type or self._looks_like_der_control(child):
                        return self._parse_der_control(child)
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to extract DERControl: {e}")
            return None
    
    def _looks_like_der_control(self, element: ET.Element) -> bool:
        """檢查元素是否像 DERControl"""
        child_tags = {self._strip_ns(c.tag) for c in element}
        return "DERControlBase" in child_tags or "interval" in child_tags
    
    def _parse_der_control(self, element: ET.Element) -> DERControl:
        """解析 DERControl 元素"""
        from bms_2030_5_client.models import (
            DERControlBase,
            DateTimeInterval,
            SignedPerCent,
            PerCent,
        )
        
        control = DERControl()
        
        for child in element:
            tag = self._strip_ns(child.tag)
            
            if tag == "mRID":
                control.mRID = child.text
            elif tag == "description":
                control.description = child.text
            elif tag == "version":
                control.version = int(child.text or "0")
            elif tag == "creationTime":
                control.creationTime = int(child.text or "0")
            elif tag == "primacy":
                control.primacy = int(child.text or "0")
            elif tag == "interval":
                interval = DateTimeInterval()
                for ic in child:
                    ic_tag = self._strip_ns(ic.tag)
                    if ic_tag == "duration":
                        interval.duration = int(ic.text or "0")
                    elif ic_tag == "start":
                        interval.start = int(ic.text or "0")
                control.interval = interval
            elif tag == "randomizeStart":
                control.randomizeStart = int(child.text or "0")
            elif tag == "randomizeDuration":
                control.randomizeDuration = int(child.text or "0")
            elif tag == "DERControlBase":
                base = DERControlBase()
                for bc in child:
                    bc_tag = self._strip_ns(bc.tag)
                    if bc_tag == "opModFixedW":
                        base.opModFixedW = self._parse_signed_percent(bc)
                    elif bc_tag == "opModFixedVar":
                        base.opModFixedVar = self._parse_signed_percent(bc)
                    elif bc_tag == "opModMaxLimW":
                        base.opModMaxLimW = self._parse_percent(bc)
                    elif bc_tag == "opModConnect":
                        base.opModConnect = bc.text.lower() in ("true", "1")
                    elif bc_tag == "opModEnergize":
                        base.opModEnergize = bc.text.lower() in ("true", "1")
                    elif bc_tag == "rampTms":
                        base.rampTms = int(bc.text or "0")
                control.DERControlBase = base
        
        return control
    
    def _parse_signed_percent(self, element: ET.Element):
        """解析 SignedPerCent"""
        from bms_2030_5_client.models import SignedPerCent
        
        sp = SignedPerCent()
        for child in element:
            tag = self._strip_ns(child.tag)
            if tag == "value":
                sp.value = int(child.text or "0")
            elif tag == "multiplier":
                sp.multiplier = int(child.text or "0")
        return sp
    
    def _parse_percent(self, element: ET.Element):
        """解析 PerCent"""
        from bms_2030_5_client.models import PerCent
        
        p = PerCent()
        for child in element:
            tag = self._strip_ns(child.tag)
            if tag == "value":
                p.value = int(child.text or "0")
        return p
    
    @staticmethod
    def _strip_ns(tag: str) -> str:
        """移除命名空間前綴"""
        if "}" in tag:
            return tag.split("}")[1]
        return tag
    
    # =========================================================================
    # DERControlResponse (控制回應)
    # =========================================================================
    
    async def _send_control_response(
        self,
        control: DERControl,
        status: ResponseStatusType
    ) -> bool:
        """
        發送 DERControlResponse
        
        Args:
            control: DERControl
            status: 回應狀態
        
        Returns:
            是否成功
        """
        # 取得 LFDI
        lfdi = self.http_client.lfdi or ""
        
        # 計算 modesResponded
        modes = 0
        if control.DERControlBase:
            base = control.DERControlBase
            if base.opModConnect is not None:
                modes |= DERControlModesType.OP_MOD_CONNECT
            if base.opModEnergize is not None:
                modes |= DERControlModesType.OP_MOD_ENERGIZE
            if base.opModFixedW:
                modes |= DERControlModesType.OP_MOD_FIXED_W
            if base.opModFixedVar:
                modes |= DERControlModesType.OP_MOD_FIXED_VAR
            if base.opModMaxLimW:
                modes |= DERControlModesType.OP_MOD_MAX_LIM_W
        
        # 建立回應
        response = DERControlResponseFull(
            createdDateTime=int(time.time()),
            endDeviceLFDI=lfdi,
            status=status,
            subject=control.mRID or "",
            modesResponded=DERControlResponseFull.modes_to_hex(modes),
        )
        
        # 取得 replyTo URI (從 control 或使用預設)
        # 注意: IEEE 2030.5 DERControl 可能有 replyTo 欄位
        reply_to = getattr(control, "replyTo", None)
        
        if not reply_to:
            # 嘗試建構回應路徑
            if control.href:
                reply_to = f"{control.href}/rsp"
            else:
                logger.warning("No replyTo URI available for response")
                return False
        
        try:
            await self.http_client._post(reply_to, response)
            self._stats["responses_sent"] += 1
            
            logger.info(
                f"Sent DERControlResponse: "
                f"mRID={control.mRID}, status={status.name}"
            )
            return True
        
        except Exception as e:
            logger.error(f"Failed to send DERControlResponse: {e}")
            self._stats["errors"] += 1
            return False
    
    # =========================================================================
    # DefaultDERControl Handling
    # =========================================================================
    
    async def _handle_default_control_notification(
        self,
        notification: Notification,
        raw_xml: str
    ) -> None:
        """處理 DefaultDERControl 通知"""
        logger.info(f"Received DefaultDERControl notification")
        
        # 解析 DefaultDERControl
        default_control = self._extract_default_control(raw_xml)
        
        if not default_control:
            logger.warning("Failed to extract DefaultDERControl")
            return
        
        logger.info(f"DefaultDERControl updated: {default_control.mRID}")
        
        # 回調
        if self._on_default_control:
            try:
                await self._on_default_control(default_control)
            except Exception as e:
                logger.exception(f"Default control callback error: {e}")
    
    def _extract_default_control(self, raw_xml: str) -> Optional[DefaultDERControl]:
        """從通知 XML 中提取 DefaultDERControl"""
        try:
            root = _safe_fromstring(raw_xml)
            
            for child in root:
                tag = self._strip_ns(child.tag)
                if tag == "Resource":
                    return xml_to_dataclass(
                        ET.tostring(child, encoding="unicode"),
                        DefaultDERControl
                    )
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to extract DefaultDERControl: {e}")
            return None
    
    # =========================================================================
    # FSA / Program Handling
    # =========================================================================
    
    async def _handle_fsa_notification(
        self,
        notification: Notification,
        raw_xml: str
    ) -> None:
        """處理 FSA 變更通知"""
        logger.info("Received FSA change notification")
        
        if self.subscription_manager:
            await self.subscription_manager.handle_fsa_change(notification)
        else:
            logger.warning("No subscription manager configured for FSA handling")
    
    async def _handle_program_notification(
        self,
        notification: Notification,
        raw_xml: str
    ) -> None:
        """處理 DERProgram 變更通知"""
        logger.info(f"Received DERProgram change notification")
        
        # 程式變更可能需要重新訂閱控制
        if self.subscription_manager:
            # 觸發重新探索程式
            end_device = self.http_client._end_device
            if end_device and end_device.href:
                fsa_list = await self.subscription_manager._get_fsa_list()
                for fsa in fsa_list:
                    await self.subscription_manager._setup_control_subscriptions(
                        fsa, end_device.href
                    )
    
    # =========================================================================
    # Subscription Error Handling
    # =========================================================================
    
    async def _handle_subscription_error(self, notification: Notification) -> None:
        """處理訂閱錯誤"""
        logger.warning(
            f"Subscription error: "
            f"resource={notification.subscribedResource}, "
            f"status={notification.status}"
        )
        
        if self.subscription_manager:
            await self.subscription_manager.handle_notification_status(notification)
        
        self._stats["errors"] += 1
