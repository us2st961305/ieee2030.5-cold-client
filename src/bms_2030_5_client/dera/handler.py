"""
DER Control Handler - 處理 IEEE 2030.5 DERControl 功率控制指令

此模組負責：
1. 解析來自 EMS Server 的 DERControl 指令
2. 排程控制事件
3. 透過 SafePowerController 安全地執行功率控制
4. 回報控制結果

⚠️ 安全注意：所有功率控制必須透過 SafePowerController 執行
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Awaitable
from uuid import uuid4

from bms_2030_5_client.models import (
    DERControl,
    DERControlBase,
    DERControlList,
    DERProgram,
    SignedPerCent,
)
from bms_2030_5_client.power_control import (
    SafePowerController,
    PowerControlResult,
    ControlMode,
    EmergencyStop,
)

logger = logging.getLogger(__name__)


class DERControlEventStatus(Enum):
    """DERControl 事件狀態"""
    PENDING = "pending"           # 等待執行
    SCHEDULED = "scheduled"       # 已排程
    ACTIVE = "active"             # 執行中
    COMPLETED = "completed"       # 已完成
    CANCELLED = "cancelled"       # 已取消
    SUPERSEDED = "superseded"     # 被新控制取代
    FAILED = "failed"             # 執行失敗


@dataclass
class DERControlEvent:
    """
    DERControl 事件包裝
    
    包含原始 DERControl 和執行狀態追蹤
    """
    control: DERControl
    status: DERControlEventStatus = DERControlEventStatus.PENDING
    received_time: int = field(default_factory=lambda: int(time.time()))
    executed_time: Optional[int] = None
    result: Optional[PowerControlResult] = None
    error_message: Optional[str] = None
    
    @property
    def event_id(self) -> str:
        """取得事件 ID"""
        return self.control.mRID or str(uuid4())[:8]
    
    @property
    def is_active(self) -> bool:
        """檢查控制是否在有效時間內"""
        return self.control.is_active()
    
    @property
    def power_setpoint_w(self) -> Optional[int]:
        """取得功率設定點（瓦）"""
        return self.control.get_power_setpoint_w()


@dataclass
class DERControlHandlerConfig:
    """DER Control Handler 配置"""
    # 最大同時追蹤的控制事件數
    max_tracked_events: int = 100
    
    # 已完成事件的保留時間（秒）
    completed_event_retention_s: int = 3600
    
    # 控制執行前的最小延遲（秒）- 用於隨機化
    min_execution_delay_s: float = 0.1
    
    # 是否允許立即執行（忽略 randomizeStart）
    allow_immediate_execution: bool = True


class DERControlHandler:
    """
    DER Control Handler - 處理 IEEE 2030.5 功率控制指令
    
    使用方式:
        handler = DERControlHandler(power_controller)
        
        # 處理單個控制
        result = await handler.handle_control(der_control)
        
        # 處理控制列表
        results = await handler.handle_control_list(der_control_list)
        
        # 取得當前活動控制
        active = handler.get_active_control()
    
    ⚠️ 安全注意：
    - 所有功率控制透過 SafePowerController 執行
    - 預設為模擬模式，不會實際控制 PCS
    - 生產模式需要特殊授權
    """
    
    def __init__(
        self,
        power_controller: SafePowerController,
        config: Optional[DERControlHandlerConfig] = None,
    ):
        """
        初始化 DER Control Handler
        
        Args:
            power_controller: 安全功率控制器（必須使用 SafePowerController）
            config: Handler 配置
        """
        self.power_controller = power_controller
        self.config = config or DERControlHandlerConfig()
        
        # 事件追蹤
        self._events: Dict[str, DERControlEvent] = {}
        self._active_event: Optional[DERControlEvent] = None
        self._event_lock = asyncio.Lock()
        
        # 排程任務
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 回調函數
        self._on_control_executed: Optional[
            Callable[[DERControlEvent], Awaitable[None]]
        ] = None
        
        logger.info(
            f"DERControlHandler initialized "
            f"(simulation_mode={power_controller.simulation_mode})"
        )
    
    @property
    def simulation_mode(self) -> bool:
        """是否為模擬模式"""
        return self.power_controller.simulation_mode
    
    @property
    def active_control(self) -> Optional[DERControlEvent]:
        """當前活動的控制事件"""
        return self._active_event
    
    def set_on_control_executed(
        self,
        callback: Callable[[DERControlEvent], Awaitable[None]]
    ) -> None:
        """設定控制執行完成的回調函數"""
        self._on_control_executed = callback
    
    async def handle_control(
        self,
        control: DERControl,
        source: str = "ieee2030.5"
    ) -> DERControlEvent:
        """
        處理單個 DERControl 指令
        
        Args:
            control: DERControl 指令
            source: 控制來源標識
        
        Returns:
            DERControlEvent 包含執行結果
        """
        async with self._event_lock:
            # 創建事件
            event = DERControlEvent(control=control)
            
            logger.info(
                f"Received DERControl: id={event.event_id}, "
                f"power={event.power_setpoint_w}W"
            )
            
            # 檢查是否需要排程
            if control.interval and control.interval.seconds_until_start() > 0:
                # 未來時間，加入排程
                event.status = DERControlEventStatus.SCHEDULED
                self._events[event.event_id] = event
                logger.info(
                    f"DERControl scheduled: id={event.event_id}, "
                    f"starts in {control.interval.seconds_until_start()}s"
                )
                return event
            
            # 立即執行
            await self._execute_control(event, source)
            
            # 追蹤事件
            self._events[event.event_id] = event
            self._cleanup_old_events()
            
            return event
    
    async def handle_control_list(
        self,
        control_list: DERControlList,
        source: str = "ieee2030.5"
    ) -> List[DERControlEvent]:
        """
        處理 DERControl 列表
        
        按優先級（primacy）排序後處理，較高優先級的控制會取代較低優先級
        
        Args:
            control_list: DERControlList
            source: 控制來源標識
        
        Returns:
            處理結果列表
        """
        if not control_list.DERControl:
            return []
        
        # 按 primacy 排序（數值越小優先級越高）
        sorted_controls = sorted(
            control_list.DERControl,
            key=lambda c: c.primacy
        )
        
        results = []
        for control in sorted_controls:
            event = await self.handle_control(control, source)
            results.append(event)
        
        return results
    
    async def _execute_control(
        self,
        event: DERControlEvent,
        source: str
    ) -> None:
        """
        執行控制事件
        
        ⚠️ 透過 SafePowerController 執行，確保安全
        """
        event.status = DERControlEventStatus.ACTIVE
        event.executed_time = int(time.time())
        
        # 檢查緊急停止
        if EmergencyStop.is_stopped():
            event.status = DERControlEventStatus.FAILED
            event.error_message = "Emergency stop is active"
            logger.warning(f"DERControl blocked by emergency stop: {event.event_id}")
            return
        
        # 取得功率設定點
        power_w = event.power_setpoint_w
        
        if power_w is None:
            # 沒有功率設定點，可能是其他類型的控制
            event.status = DERControlEventStatus.COMPLETED
            event.error_message = "No power setpoint specified"
            logger.info(f"DERControl has no power setpoint: {event.event_id}")
            return
        
        # 取代當前活動控制
        if self._active_event and self._active_event.status == DERControlEventStatus.ACTIVE:
            self._active_event.status = DERControlEventStatus.SUPERSEDED
            logger.info(
                f"DERControl superseded: {self._active_event.event_id} -> {event.event_id}"
            )
        
        self._active_event = event
        
        # 透過安全控制器設定功率
        try:
            result = await self.power_controller.set_power_setpoint(
                power_w=power_w,
                source=source
            )
            
            event.result = result
            
            if result.success:
                event.status = DERControlEventStatus.COMPLETED
                if result.simulated:
                    logger.info(
                        f"[SIMULATION] DERControl executed: "
                        f"id={event.event_id}, power={power_w}W"
                    )
                else:
                    logger.info(
                        f"[PRODUCTION] DERControl executed: "
                        f"id={event.event_id}, power={power_w}W"
                    )
            else:
                event.status = DERControlEventStatus.FAILED
                event.error_message = "; ".join(result.errors)
                logger.error(
                    f"DERControl failed: id={event.event_id}, "
                    f"errors={result.errors}"
                )
        
        except Exception as e:
            event.status = DERControlEventStatus.FAILED
            event.error_message = str(e)
            logger.exception(f"DERControl execution error: {event.event_id}")
        
        # 執行回調
        if self._on_control_executed:
            try:
                await self._on_control_executed(event)
            except Exception as e:
                logger.exception(f"Control executed callback error: {e}")
    
    async def cancel_control(self, event_id: str) -> bool:
        """
        取消控制事件
        
        Args:
            event_id: 事件 ID
        
        Returns:
            是否成功取消
        """
        async with self._event_lock:
            event = self._events.get(event_id)
            if not event:
                return False
            
            if event.status in (
                DERControlEventStatus.PENDING,
                DERControlEventStatus.SCHEDULED,
                DERControlEventStatus.ACTIVE
            ):
                event.status = DERControlEventStatus.CANCELLED
                
                # 如果是當前活動控制，設定功率為 0
                if event == self._active_event:
                    await self.power_controller.set_power_setpoint(
                        power_w=0,
                        source="cancel"
                    )
                    self._active_event = None
                
                logger.info(f"DERControl cancelled: {event_id}")
                return True
            
            return False
    
    def get_event(self, event_id: str) -> Optional[DERControlEvent]:
        """取得事件狀態"""
        return self._events.get(event_id)
    
    def get_all_events(self) -> List[DERControlEvent]:
        """取得所有追蹤中的事件"""
        return list(self._events.values())
    
    def get_pending_events(self) -> List[DERControlEvent]:
        """取得待執行的事件"""
        return [
            e for e in self._events.values()
            if e.status in (
                DERControlEventStatus.PENDING,
                DERControlEventStatus.SCHEDULED
            )
        ]
    
    def _cleanup_old_events(self) -> None:
        """清理過舊的已完成事件"""
        now = int(time.time())
        cutoff = now - self.config.completed_event_retention_s
        
        to_remove = [
            event_id for event_id, event in self._events.items()
            if event.status in (
                DERControlEventStatus.COMPLETED,
                DERControlEventStatus.CANCELLED,
                DERControlEventStatus.FAILED,
                DERControlEventStatus.SUPERSEDED,
            ) and event.executed_time and event.executed_time < cutoff
        ]
        
        for event_id in to_remove:
            del self._events[event_id]
        
        # 限制追蹤數量
        if len(self._events) > self.config.max_tracked_events:
            # 移除最舊的已完成事件
            sorted_events = sorted(
                self._events.items(),
                key=lambda x: x[1].received_time
            )
            for event_id, _ in sorted_events[:len(self._events) - self.config.max_tracked_events]:
                del self._events[event_id]
    
    async def start_scheduler(self) -> None:
        """啟動排程器（處理未來時間的控制）"""
        if self._running:
            return
        
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("DERControl scheduler started")
    
    async def stop_scheduler(self) -> None:
        """停止排程器"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("DERControl scheduler stopped")
    
    async def _scheduler_loop(self) -> None:
        """排程器主循環"""
        while self._running:
            try:
                await self._process_scheduled_events()
                await asyncio.sleep(1)  # 每秒檢查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Scheduler error: {e}")
                await asyncio.sleep(5)
    
    async def _process_scheduled_events(self) -> None:
        """處理到期的排程事件"""
        async with self._event_lock:
            now = int(time.time())
            
            for event in list(self._events.values()):
                if event.status != DERControlEventStatus.SCHEDULED:
                    continue
                
                if event.control.interval and event.control.interval.is_active(now):
                    # 時間到，執行控制
                    await self._execute_control(event, "scheduled")


# XML 解析輔助函數
def parse_der_control_from_xml(xml_content: str) -> DERControl:
    """
    從 XML 解析 DERControl
    
    Args:
        xml_content: XML 字串
    
    Returns:
        DERControl 物件
    """
    import xml.etree.ElementTree as ET
    
    # 定義命名空間
    ns = {"sep": "urn:ieee:std:2030.5:ns"}
    
    root = ET.fromstring(xml_content)
    
    # 處理命名空間
    if root.tag.startswith("{"):
        # 有命名空間前綴
        pass
    
    control = DERControl()
    
    # 解析基本屬性
    href = root.get("href")
    if href:
        control.href = href
    
    # mRID
    mrid_elem = root.find(".//mRID", ns) or root.find("mRID")
    if mrid_elem is not None and mrid_elem.text:
        control.mRID = mrid_elem.text
    
    # description
    desc_elem = root.find(".//description", ns) or root.find("description")
    if desc_elem is not None and desc_elem.text:
        control.description = desc_elem.text
    
    # interval
    interval_elem = root.find(".//interval", ns) or root.find("interval")
    if interval_elem is not None:
        from bms_2030_5_client.models import DateTimeInterval
        interval = DateTimeInterval()
        
        start_elem = interval_elem.find("start")
        if start_elem is not None and start_elem.text:
            interval.start = int(start_elem.text)
        
        duration_elem = interval_elem.find("duration")
        if duration_elem is not None and duration_elem.text:
            interval.duration = int(duration_elem.text)
        
        control.interval = interval
    
    # DERControlBase
    base_elem = root.find(".//DERControlBase", ns) or root.find("DERControlBase")
    if base_elem is not None:
        control_base = DERControlBase()
        
        # opModFixedW
        fixed_w_elem = base_elem.find("opModFixedW")
        if fixed_w_elem is not None:
            value_elem = fixed_w_elem.find("value")
            mult_elem = fixed_w_elem.find("multiplier")
            
            control_base.opModFixedW = SignedPerCent(
                value=int(value_elem.text) if value_elem is not None and value_elem.text else 0,
                multiplier=int(mult_elem.text) if mult_elem is not None and mult_elem.text else 0
            )
        
        # opModFixedVar
        fixed_var_elem = base_elem.find("opModFixedVar")
        if fixed_var_elem is not None:
            value_elem = fixed_var_elem.find("value")
            mult_elem = fixed_var_elem.find("multiplier")
            
            control_base.opModFixedVar = SignedPerCent(
                value=int(value_elem.text) if value_elem is not None and value_elem.text else 0,
                multiplier=int(mult_elem.text) if mult_elem is not None and mult_elem.text else 0
            )
        
        # opModConnect
        connect_elem = base_elem.find("opModConnect")
        if connect_elem is not None and connect_elem.text:
            control_base.opModConnect = connect_elem.text.lower() == "true"
        
        control.DERControlBase = control_base
    
    # primacy
    primacy_elem = root.find(".//primacy", ns) or root.find("primacy")
    if primacy_elem is not None and primacy_elem.text:
        control.primacy = int(primacy_elem.text)
    
    return control


def parse_der_control_list_from_xml(xml_content: str) -> DERControlList:
    """
    從 XML 解析 DERControlList
    
    Args:
        xml_content: XML 字串
    
    Returns:
        DERControlList 物件
    """
    import xml.etree.ElementTree as ET
    
    root = ET.fromstring(xml_content)
    
    control_list = DERControlList()
    
    # 解析屬性
    href = root.get("href")
    if href:
        control_list.href = href
    
    all_attr = root.get("all")
    if all_attr:
        control_list.all = int(all_attr)
    
    results_attr = root.get("results")
    if results_attr:
        control_list.results = int(results_attr)
    
    # 解析每個 DERControl
    for control_elem in root.findall(".//DERControl") or root.findall("DERControl"):
        control_xml = ET.tostring(control_elem, encoding="unicode")
        control = parse_der_control_from_xml(control_xml)
        control_list.DERControl.append(control)
    
    return control_list
