"""
DER Control Polling Client - 輪詢 IEEE 2030.5 Server 的 DERControl 指令

此模組負責：
1. 定期輪詢 EMS Server 取得 DERControl 指令
2. 解析並轉發給 DERControlHandler 處理
3. 追蹤已處理的控制以避免重複執行

⚠️ 安全注意：所有功率控制透過 DERControlHandler -> SafePowerController 執行
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set, Awaitable

from bms_2030_5_client.models import (
    DERControl,
    DERControlList,
    DERProgram,
    DERProgramList,
)
from bms_2030_5_client.dera.handler import (
    DERControlHandler,
    DERControlEvent,
    parse_der_control_from_xml,
    parse_der_control_list_from_xml,
)

logger = logging.getLogger(__name__)


@dataclass
class DERControlPollerConfig:
    """DER Control Poller 配置"""
    # 輪詢間隔（秒）
    poll_interval_s: float = 30.0
    
    # 最小輪詢間隔（秒）
    min_poll_interval_s: float = 5.0
    
    # 最大輪詢間隔（秒）
    max_poll_interval_s: float = 300.0
    
    # 連線錯誤時的重試間隔（秒）
    error_retry_interval_s: float = 60.0
    
    # 已處理控制 ID 的保留數量
    processed_control_retention: int = 1000
    
    # 是否在啟動時立即輪詢
    poll_on_start: bool = True


class DERControlPoller:
    """
    DER Control 輪詢器
    
    定期從 IEEE 2030.5 Server 取得 DERControl 指令並交給 Handler 處理
    
    使用方式:
        poller = DERControlPoller(
            http_client=ieee_client,
            handler=der_control_handler,
        )
        
        await poller.start()
        # ... 運行中 ...
        await poller.stop()
    """
    
    def __init__(
        self,
        http_client,  # IEEE2030_5Client
        handler: DERControlHandler,
        config: Optional[DERControlPollerConfig] = None,
    ):
        """
        初始化 DER Control Poller
        
        Args:
            http_client: IEEE 2030.5 HTTP 客戶端
            handler: DER Control Handler
            config: Poller 配置
        """
        self.http_client = http_client
        self.handler = handler
        self.config = config or DERControlPollerConfig()
        
        # 已處理的控制 ID（避免重複處理）
        self._processed_mRIDs: Set[str] = set()
        
        # 輪詢任務
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 當前 DER Program
        self._current_program: Optional[DERProgram] = None
        self._active_control_list_href: Optional[str] = None
        
        # 統計
        self._poll_count = 0
        self._last_poll_time: Optional[float] = None
        self._last_control_received_time: Optional[float] = None
        
        # 回調
        self._on_new_control: Optional[
            Callable[[DERControl], Awaitable[None]]
        ] = None
        
        logger.info(
            f"DERControlPoller initialized "
            f"(poll_interval={self.config.poll_interval_s}s)"
        )
    
    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running
    
    @property
    def poll_count(self) -> int:
        """輪詢次數"""
        return self._poll_count
    
    def set_on_new_control(
        self,
        callback: Callable[[DERControl], Awaitable[None]]
    ) -> None:
        """設定收到新控制時的回調函數"""
        self._on_new_control = callback
    
    async def start(self) -> None:
        """啟動輪詢器"""
        if self._running:
            logger.warning("DERControlPoller already running")
            return
        
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("DERControlPoller started")
    
    async def stop(self) -> None:
        """停止輪詢器"""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("DERControlPoller stopped")
    
    async def poll_once(self) -> list[DERControlEvent]:
        """
        執行一次輪詢
        
        Returns:
            處理的 DERControlEvent 列表
        """
        results = []
        
        try:
            # 1. 取得 Active DER Control List
            controls = await self._fetch_active_controls()
            
            if not controls:
                logger.debug("No active DER controls found")
                return results
            
            # 2. 過濾已處理的控制
            new_controls = [
                c for c in controls
                if c.mRID and c.mRID not in self._processed_mRIDs
            ]
            
            if not new_controls:
                logger.debug("No new DER controls to process")
                return results
            
            logger.info(f"Found {len(new_controls)} new DER control(s)")
            
            # 3. 處理每個新控制
            for control in new_controls:
                try:
                    event = await self.handler.handle_control(
                        control,
                        source="ieee2030.5_poll"
                    )
                    results.append(event)
                    
                    # 標記為已處理
                    if control.mRID:
                        self._processed_mRIDs.add(control.mRID)
                    
                    # 執行回調
                    if self._on_new_control:
                        await self._on_new_control(control)
                    
                    self._last_control_received_time = time.time()
                    
                except Exception as e:
                    logger.exception(f"Error handling DER control: {e}")
            
            # 4. 清理過舊的已處理 ID
            self._cleanup_processed_ids()
            
        except Exception as e:
            logger.exception(f"Error polling DER controls: {e}")
        
        return results
    
    async def _poll_loop(self) -> None:
        """輪詢主循環"""
        # 啟動時立即輪詢一次
        if self.config.poll_on_start:
            await self.poll_once()
            self._poll_count += 1
            self._last_poll_time = time.time()
        
        while self._running:
            try:
                await asyncio.sleep(self.config.poll_interval_s)
                
                if not self._running:
                    break
                
                await self.poll_once()
                self._poll_count += 1
                self._last_poll_time = time.time()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Poll loop error: {e}")
                # 錯誤時使用較長的重試間隔
                await asyncio.sleep(self.config.error_retry_interval_s)
    
    async def _fetch_active_controls(self) -> list[DERControl]:
        """
        從 Server 取得 Active DER Controls
        
        Returns:
            DERControl 列表
        """
        controls = []
        
        try:
            # 嘗試取得 Active DER Control List
            # 路徑通常是: /edev/{id}/derp/0/actderc
            # 或從 DERProgram 取得 ActiveDERControlListLink
            
            # 方法 1: 直接取得 Active Control
            active_controls = await self._get_active_der_controls()
            if active_controls:
                controls.extend(active_controls)
            
            # 方法 2: 透過 DER Program 取得
            if not controls and self._current_program:
                program_controls = await self._get_program_controls()
                controls.extend(program_controls)
            
        except Exception as e:
            logger.exception(f"Error fetching active controls: {e}")
        
        return controls
    
    async def _get_active_der_controls(self) -> list[DERControl]:
        """直接取得 Active DER Controls"""
        controls = []
        
        try:
            # 取得 End Device
            end_device = getattr(self.http_client, '_end_device', None)
            if not end_device:
                return controls
            
            # 構建 Active Control URI
            # 典型路徑: /edev/{id}/derp/actderc
            edev_href = end_device.href or ""
            
            # 嘗試幾個常見的路徑模式
            possible_paths = [
                f"{edev_href}/derp/actderc",
                f"{edev_href}/der/actderc",
                f"/derp/actderc",
            ]
            
            for path in possible_paths:
                try:
                    response = await self.http_client.get(path)
                    if response:
                        # 解析 DERControlList
                        control_list = parse_der_control_list_from_xml(response)
                        controls.extend(control_list.DERControl)
                        break
                except Exception as e:
                    logger.debug(f"Path {path} failed: {e}")
                    continue
            
        except Exception as e:
            logger.debug(f"Get active DER controls failed: {e}")
        
        return controls
    
    async def _get_program_controls(self) -> list[DERControl]:
        """從 DER Program 取得 Controls"""
        controls = []
        
        if not self._current_program:
            return controls
        
        try:
            # 取得 Active Control List Link
            link = self._current_program.ActiveDERControlListLink
            if not link:
                return controls
            
            response = await self.http_client.get(link)
            if response:
                control_list = parse_der_control_list_from_xml(response)
                controls.extend(control_list.DERControl)
        
        except Exception as e:
            logger.debug(f"Get program controls failed: {e}")
        
        return controls
    
    def _cleanup_processed_ids(self) -> None:
        """清理過多的已處理 ID"""
        if len(self._processed_mRIDs) > self.config.processed_control_retention:
            # 保留最近的一半
            to_keep = self.config.processed_control_retention // 2
            self._processed_mRIDs = set(
                list(self._processed_mRIDs)[-to_keep:]
            )
    
    def update_poll_interval(self, interval_s: float) -> None:
        """
        更新輪詢間隔
        
        可根據 Server 回應的 pollRate 調整
        """
        interval_s = max(
            self.config.min_poll_interval_s,
            min(self.config.max_poll_interval_s, interval_s)
        )
        self.config.poll_interval_s = interval_s
        logger.info(f"Poll interval updated to {interval_s}s")
    
    def get_stats(self) -> dict:
        """取得統計資訊"""
        return {
            "is_running": self._running,
            "poll_count": self._poll_count,
            "poll_interval_s": self.config.poll_interval_s,
            "last_poll_time": self._last_poll_time,
            "last_control_received_time": self._last_control_received_time,
            "processed_control_count": len(self._processed_mRIDs),
            "handler_simulation_mode": self.handler.simulation_mode,
        }


class DERControlIntegration:
    """
    DER Control 整合類別
    
    整合 Poller 和 Handler，提供完整的 DER Control 處理功能
    
    使用方式:
        integration = DERControlIntegration(
            http_client=ieee_client,
            power_controller=safe_power_controller,
        )
        
        await integration.start()
        # ... 運行中 ...
        await integration.stop()
    """
    
    def __init__(
        self,
        http_client,  # IEEE2030_5Client
        power_controller,  # SafePowerController
        poller_config: Optional[DERControlPollerConfig] = None,
    ):
        """
        初始化 DER Control Integration
        
        Args:
            http_client: IEEE 2030.5 HTTP 客戶端
            power_controller: 安全功率控制器
            poller_config: Poller 配置
        """
        self.handler = DERControlHandler(power_controller)
        self.poller = DERControlPoller(
            http_client=http_client,
            handler=self.handler,
            config=poller_config,
        )
        
        logger.info(
            f"DERControlIntegration initialized "
            f"(simulation_mode={power_controller.simulation_mode})"
        )
    
    async def start(self) -> None:
        """啟動整合服務"""
        await self.handler.start_scheduler()
        await self.poller.start()
        logger.info("DERControlIntegration started")
    
    async def stop(self) -> None:
        """停止整合服務"""
        await self.poller.stop()
        await self.handler.stop_scheduler()
        logger.info("DERControlIntegration stopped")
    
    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self.poller.is_running
    
    @property
    def active_control(self) -> Optional[DERControlEvent]:
        """當前活動的控制"""
        return self.handler.active_control
    
    def get_stats(self) -> dict:
        """取得統計資訊"""
        return {
            "poller": self.poller.get_stats(),
            "handler": {
                "active_control": (
                    self.handler.active_control.event_id
                    if self.handler.active_control else None
                ),
                "pending_events": len(self.handler.get_pending_events()),
                "total_events": len(self.handler.get_all_events()),
            },
        }
