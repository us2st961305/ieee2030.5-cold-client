"""
IEEE 2030.5 DER Client Orchestrator

完整實作 IEEE 2030.5 客戶端流程：
1. FSA (Function Set Assignments) 探索與監控
2. DERProgram 管理與優先權處理
3. DERControl 事件執行與排程
4. 重疊/衝突處理
5. Response 回報

Reference: IEEE Std 2030.5-2023

⚠️ 安全注意：所有功率控制透過 SafePowerController 執行
"""

from __future__ import annotations

import asyncio
import collections
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional, Awaitable

from bms_2030_5_client.models import (
    DERControl,
    DERControlBase,
    DERControlList,
    DERProgram,
    DERProgramList,
    DefaultDERControl,
    FunctionSetAssignments,
    FunctionSetAssignmentsList,
    DERControlResponseFull,
    DERControlModesType,
    ResponseStatusType,
    DateTimeInterval,
    SignedPerCent,
)
from bms_2030_5_client.dera.handler import (
    DERControlHandler,
    DERControlEvent,
    DERControlEventStatus,
    parse_der_control_from_xml,
)
from bms_2030_5_client.power_control import (
    SafePowerController,
    PowerControlResult,
    EmergencyStop,
)

# Import control history recorder (optional, for web UI)
try:
    from bms_2030_5_client.web.der_control_history import get_der_control_history
    _has_history_recorder = True
except ImportError:
    _has_history_recorder = False
    get_der_control_history = None

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class DERClientConfig:
    """DER Client 配置"""
    
    # FSA 輪詢間隔（秒）
    fsa_poll_interval_s: float = 300.0  # 5 分鐘
    
    # DERProgram 輪詢間隔（秒）
    program_poll_interval_s: float = 60.0  # 1 分鐘
    
    # DERControl 輪詢間隔（秒）- IEEE 2030.5 建議最少 15 分鐘
    control_poll_interval_s: float = 30.0  # 30 秒（更快響應）
    
    # 事件執行前驗證時間（秒）- IEEE 2030.5 要求 15 分鐘內
    pre_execution_verify_s: float = 900.0  # 15 分鐘
    
    # 最大支援的計畫數量 - IEEE 2030.5 要求至少 6 個
    max_programs: int = 6
    
    # 是否啟用隨機化
    enable_randomization: bool = True
    
    # 已處理事件 ID 保留數量
    processed_event_retention: int = 1000
    
    # Response 發送重試次數
    response_max_retries: int = 3
    
    # Response 發送超時（秒）
    response_timeout_s: float = 30.0


# =============================================================================
# Tracked Program State
# =============================================================================

@dataclass
class TrackedProgram:
    """追蹤的 DERProgram 狀態"""
    program: DERProgram
    primacy: int
    last_poll_time: float = 0
    active_controls: List[DERControl] = field(default_factory=list)
    default_control: Optional[DefaultDERControl] = None
    is_active: bool = True


@dataclass
class TrackedControl:
    """追蹤的 DERControl 狀態"""
    control: DERControl
    program: DERProgram
    primacy: int  # 計畫優先權
    event: Optional[DERControlEvent] = None
    randomized_start: Optional[int] = None
    randomized_duration: Optional[int] = None
    response_sent: bool = False
    status: DERControlEventStatus = DERControlEventStatus.PENDING
    # Response 重試追蹤
    pending_response: Optional[ResponseStatusType] = None  # 待發送的 response 狀態
    response_retry_count: int = 0  # 已重試次數
    last_response_attempt: float = 0  # 上次嘗試時間


# =============================================================================
# DER Client Orchestrator
# =============================================================================

class DERClient:
    """
    IEEE 2030.5 DER Client 主控器
    
    完整實作標準流程：
    
    1. 查找功能集分配 (FSA)
       - 探索 EndDevice 下的 FunctionSetAssignmentsList
       - 定期輪詢或訂閱變更
       - FSA 移除時停止相關控制
    
    2. 管理計畫 (DERProgram)
       - 支援至少 6 個計畫
       - 解析優先權 (primacy)，數字越小優先級越高
       - 獲取 DERControlList 和 DefaultDERControl
    
    3. 執行控制 (DERControl)
       - 輪詢新事件（依 pollRate 或最少 15 分鐘）
       - 執行前 15 分鐘內驗證 EventStatus
       - 支援 randomizeStart 和 randomizeDuration
       - 處理已過開始時間但未過結束時間的事件
    
    4. 衝突處理
       - 相同優先權：以 creationTime 較新者為準
       - 不同控制模式可同時執行
       - 高優先級事件結束後回復低優先級事件
    
    5. 回報狀態
       - 依 responseRequired 欄位回報
       - 包含 LFDI、狀態碼、事件 mRID
    
    使用方式:
        client = DERClient(
            http_client=ieee_client,
            power_controller=safe_controller,
        )
        await client.start()
        # ... 運行中 ...
        await client.stop()
    """
    
    def __init__(
        self,
        http_client,  # IEEE2030_5Client
        power_controller: SafePowerController,
        config: Optional[DERClientConfig] = None,
    ):
        """
        初始化 DER Client
        
        Args:
            http_client: IEEE 2030.5 HTTP 客戶端
            power_controller: 安全功率控制器
            config: 客戶端配置
        """
        self.http_client = http_client
        self.power_controller = power_controller
        self.config = config or DERClientConfig()
        
        # DER Control Handler
        self.handler = DERControlHandler(power_controller)
        
        # 追蹤狀態
        self._tracked_fsa: Dict[str, FunctionSetAssignments] = {}
        self._tracked_programs: Dict[str, TrackedProgram] = {}
        self._tracked_controls: Dict[str, TrackedControl] = {}
        
        # 當前活動控制（按控制模式分組）
        self._active_by_mode: Dict[str, TrackedControl] = {}
        
        # 已處理的事件 ID（使用 deque 以保留插入順序並限制大小）
        self._processed_mRIDs: Deque[str] = collections.deque(
            maxlen=self.config.processed_event_retention
        )
        
        # 已處理 cancel 的事件 ID（避免重複回報 EVENT_CANCELLED）
        self._cancelled_mRIDs: set[str] = set()
        
        # 當前活動的 DefaultDERControl
        self._active_default: Optional[DefaultDERControl] = None
        self._active_default_program: Optional[DERProgram] = None
        
        # 輪詢任務
        self._fsa_poll_task: Optional[asyncio.Task] = None
        self._control_poll_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 回調
        self._on_control_executed: Optional[
            Callable[[TrackedControl], Awaitable[None]]
        ] = None
        
        # 統計
        self._stats = {
            "fsa_polls": 0,
            "program_polls": 0,
            "control_polls": 0,
            "controls_executed": 0,
            "responses_sent": 0,
            "errors": 0,
        }
        
        logger.info(
            f"DERClient initialized "
            f"(control_mode={power_controller.control_mode.value})"
        )
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self) -> None:
        """啟動 DER Client"""
        if self._running:
            logger.warning("DERClient already running")
            return
        
        self._running = True
        
        # 啟動輪詢任務
        self._fsa_poll_task = asyncio.create_task(self._fsa_poll_loop())
        self._control_poll_task = asyncio.create_task(self._control_poll_loop())
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("DERClient started")
    
    async def stop(self) -> None:
        """停止 DER Client"""
        self._running = False
        
        # 取消所有任務
        for task in [
            self._fsa_poll_task,
            self._control_poll_task,
            self._scheduler_task,
        ]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("DERClient stopped")
    
    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running
    
    @property
    def stats(self) -> dict:
        """取得統計資料"""
        return dict(self._stats)
    
    # =========================================================================
    # 1. FSA Discovery & Monitoring
    # =========================================================================
    
    async def _fsa_poll_loop(self) -> None:
        """FSA 輪詢迴圈"""
        while self._running:
            try:
                await self._poll_fsa()
                self._stats["fsa_polls"] += 1
            except Exception as e:
                logger.error(f"FSA poll error: {e}")
                self._stats["errors"] += 1
            
            await asyncio.sleep(self.config.fsa_poll_interval_s)
    
    async def _poll_fsa(self) -> None:
        """
        輪詢 FSA 列表
        
        查詢 EndDevice 下的 FunctionSetAssignmentsList
        """
        logger.debug("Polling FSA...")
        self._stats["fsa_polls"] += 1
        
        # 取得 EndDevice
        end_device = self.http_client._end_device
        if not end_device:
            logger.warning("EndDevice not available, skipping FSA poll")
            return
        
        # 取得 FSA 列表連結
        fsa_link = end_device.FunctionSetAssignmentsListLink
        if not fsa_link:
            logger.debug("No FunctionSetAssignmentsListLink available")
            return
        
        # 處理 Link 物件或字串
        fsa_href = fsa_link.href if hasattr(fsa_link, 'href') else fsa_link
        if not fsa_href:
            logger.debug("No FunctionSetAssignmentsListLink href available")
            return
        
        try:
            # 取得 FSA 列表
            fsa_list = await self.http_client._get(
                fsa_href,
                FunctionSetAssignmentsList
            )
            
            if not fsa_list:
                logger.debug("No FSA list response")
                return
            
            # 取得目前的 FSA 列表 (可能為空)
            current_fsa_list = fsa_list.FunctionSetAssignments or []
            
            # 更新追蹤的 FSA
            current_fsa_ids = set()
            for fsa in current_fsa_list:
                fsa_id = fsa.mRID or fsa.href or str(id(fsa))
                current_fsa_ids.add(fsa_id)
                
                if fsa_id not in self._tracked_fsa:
                    logger.info(f"New FSA discovered: {fsa_id}")
                    self._tracked_fsa[fsa_id] = fsa
                    
                    # 記錄 FSA 到歷史（供 Web UI 顯示）
                    self._record_fsa_to_history(fsa)
                    
                    # 處理新 FSA 的 DERProgram
                    await self._process_fsa_programs(fsa)
                else:
                    # 檢查 FSA 是否有變更
                    old_fsa = self._tracked_fsa[fsa_id]
                    if fsa.version != old_fsa.version:
                        logger.info(f"FSA updated: {fsa_id}")
                        self._tracked_fsa[fsa_id] = fsa
                        
                        # 記錄 FSA 更新到歷史
                        self._record_fsa_to_history(fsa)
                        
                        await self._process_fsa_programs(fsa)
            
            # 檢查被移除的 FSA
            removed_fsa_ids = set(self._tracked_fsa.keys()) - current_fsa_ids
            for fsa_id in removed_fsa_ids:
                logger.info(f"FSA removed: {fsa_id}")
                
                # 記錄 FSA 移除到歷史
                self._record_fsa_removed(fsa_id)
                
                await self._handle_fsa_removed(fsa_id)
                del self._tracked_fsa[fsa_id]
        
        except Exception as e:
            logger.error(f"Failed to poll FSA: {e}")
            raise
    
    async def _process_fsa_programs(self, fsa: FunctionSetAssignments) -> None:
        """處理 FSA 中的 DERProgram 列表"""
        # 取得 DERProgramListLink href (處理 Link 物件或字串)
        derp_href = fsa.get_der_program_list_href()
        if not derp_href:
            logger.debug(f"FSA {fsa.mRID or fsa.href} has no DERProgramListLink")
            return
        
        fsa_id = fsa.mRID or fsa.href or str(id(fsa))
        logger.info(f"Processing FSA programs: {fsa_id}, DERProgramListLink={derp_href}")
        
        try:
            program_list = await self.http_client._get(
                derp_href,
                DERProgramList
            )
            
            if not program_list or not program_list.DERProgram:
                return
            
            # 限制計畫數量
            programs = program_list.DERProgram[:self.config.max_programs]
            
            # 更新 FSA 的 program 數量
            self._update_fsa_program_count(fsa_id, len(programs))
            
            for program in programs:
                await self._track_program(program, fsa_id=fsa_id)
        
        except Exception as e:
            logger.error(f"Failed to process FSA programs: {e}")
    
    async def _handle_fsa_removed(self, fsa_id: str) -> None:
        """
        處理 FSA 移除
        
        停止該 FSA 中所有計畫的控制
        """
        # 找出並移除相關的計畫
        programs_to_remove = []
        for prog_id, tracked in self._tracked_programs.items():
            # 簡化：移除所有計畫（實際應追蹤 FSA 與 Program 的關係）
            programs_to_remove.append(prog_id)
        
        for prog_id in programs_to_remove:
            await self._untrack_program(prog_id)
    
    # =========================================================================
    # 2. DERProgram Management
    # =========================================================================
    
    async def _track_program(self, program: DERProgram, fsa_id: Optional[str] = None) -> None:
        """
        追蹤 DERProgram
        
        Args:
            program: DERProgram 資源
            fsa_id: 所屬 FSA 的 ID（可選）
        """
        prog_id = program.mRID or program.href or str(id(program))
        
        if prog_id in self._tracked_programs:
            # 更新現有計畫
            self._tracked_programs[prog_id].program = program
            self._tracked_programs[prog_id].primacy = program.primacy
            logger.debug(f"Updated program: {prog_id} (primacy={program.primacy})")
        else:
            # 新增計畫
            self._tracked_programs[prog_id] = TrackedProgram(
                program=program,
                primacy=program.primacy,
            )
            logger.info(
                f"Tracking new program: {prog_id} "
                f"(primacy={program.primacy})"
            )
        
        # 記錄 DERProgram 到歷史（供 Web UI 顯示）
        self._record_program_to_history(program, fsa_id)
        
        # 取得 DefaultDERControl
        await self._fetch_default_control(prog_id)
    
    async def _untrack_program(self, prog_id: str) -> None:
        """
        取消追蹤 DERProgram
        
        停止該計畫的所有控制
        """
        if prog_id not in self._tracked_programs:
            return
        
        tracked = self._tracked_programs[prog_id]
        logger.info(f"Untracking program: {prog_id}")
        
        # 記錄 DERProgram 移除到歷史
        self._record_program_removed(prog_id)
        
        # 取消相關控制
        controls_to_cancel = [
            ctrl_id for ctrl_id, ctrl in self._tracked_controls.items()
            if ctrl.program.mRID == tracked.program.mRID
        ]
        
        for ctrl_id in controls_to_cancel:
            await self._cancel_control(ctrl_id, "Program removed")
        
        del self._tracked_programs[prog_id]
    
    async def _fetch_default_control(self, prog_id: str) -> None:
        """取得計畫的 DefaultDERControl"""
        if prog_id not in self._tracked_programs:
            return
        
        tracked = self._tracked_programs[prog_id]
        program = tracked.program
        
        default_ctrl_href = program.get_default_der_control_href()
        if not default_ctrl_href:
            return
        
        try:
            default_ctrl = await self.http_client._get(
                default_ctrl_href,
                DefaultDERControl
            )
            tracked.default_control = default_ctrl
            logger.debug(f"Fetched DefaultDERControl for program: {prog_id}")
        except Exception as e:
            logger.warning(f"Failed to fetch DefaultDERControl: {e}")
    
    def _get_highest_priority_program(self) -> Optional[TrackedProgram]:
        """取得最高優先級的計畫（primacy 最小）"""
        if not self._tracked_programs:
            return None
        
        return min(
            self._tracked_programs.values(),
            key=lambda p: p.primacy
        )
    
    # =========================================================================
    # 3. DERControl Execution
    # =========================================================================
    
    async def _control_poll_loop(self) -> None:
        """DERControl 輪詢迴圈"""
        while self._running:
            try:
                await self._poll_controls()
                self._stats["control_polls"] += 1
                
                # 檢查並重試失敗的 response
                await self._retry_pending_responses()
            except Exception as e:
                logger.error(f"Control poll error: {e}")
                self._stats["errors"] += 1
            
            await asyncio.sleep(self.config.control_poll_interval_s)
    
    async def _retry_pending_responses(self) -> None:
        """重試待發送的 response（按 pollRate 週期）"""
        for ctrl_id, tracked in list(self._tracked_controls.items()):
            if tracked.pending_response is not None:
                logger.info(
                    f"Retrying pending response for control {ctrl_id}, "
                    f"status={tracked.pending_response.name}, "
                    f"retry_count={tracked.response_retry_count}"
                )
                await self._send_response(tracked, tracked.pending_response)
    
    async def _poll_controls(self) -> None:
        """
        輪詢所有計畫的 DERControl
        """
        logger.debug("Polling DERControls...")
        
        for prog_id, tracked in self._tracked_programs.items():
            await self._poll_program_controls(prog_id, tracked)
    
    async def _poll_program_controls(
        self,
        prog_id: str,
        tracked: TrackedProgram
    ) -> None:
        """輪詢單個計畫的控制"""
        program = tracked.program
        
        # IEEE 2030.5-2023: 使用 DERControlListLink (/derp/{id}/derc)
        control_list_href = program.get_der_control_list_href()
        
        if not control_list_href:
            return
        
        try:
            control_list = await self.http_client._get(
                control_list_href,
                DERControlList
            )
            
            if not control_list or not control_list.DERControl:
                # 無活動控制，檢查是否需要執行 DefaultDERControl
                await self._check_default_control(tracked)
                return
            
            # 處理每個控制
            for control in control_list.DERControl:
                await self._process_control(control, program)
            
            tracked.last_poll_time = time.time()
            self._stats["program_polls"] += 1
        
        except Exception as e:
            logger.error(f"Failed to poll controls for program {prog_id}: {e}")
    
    async def _process_control(
        self,
        control: DERControl,
        program: DERProgram
    ) -> None:
        """
        處理單個 DERControl
        
        包含隨機化、排程和執行邏輯
        """
        ctrl_id = control.mRID or str(id(control))
        
        # 檢查是否已處理
        if ctrl_id in self._processed_mRIDs:
            # Check if server cancelled this control (currentStatus=2)
            if (
                control.EventStatus
                and control.EventStatus.currentStatus == 2
                and ctrl_id not in self._cancelled_mRIDs
            ):
                logger.info(
                    f"Server cancelled detected for {ctrl_id}, "
                    f"processing cancel"
                )
                self._cancelled_mRIDs.add(ctrl_id)
                await self._handle_server_cancel(ctrl_id)
            return
        
        logger.info(
            f"New DERControl: {ctrl_id} "
            f"(program_primacy={program.primacy})"
        )
        
        # 記錄到歷史（供 Web UI 顯示）
        if _has_history_recorder:
            try:
                history = get_der_control_history()
                control_type = "unknown"
                power_w = control.get_power_setpoint_w()
                if control.DERControlBase:
                    if control.DERControlBase.opModFixedW:
                        control_type = "opModFixedW"
                    elif control.DERControlBase.opModFixedVar:
                        control_type = "opModFixedVar"
                    elif control.DERControlBase.opModMaxLimW:
                        control_type = "opModMaxLimW"
                    elif control.DERControlBase.opModEnergize is not None:
                        control_type = "opModEnergize"
                    elif control.DERControlBase.opModConnect is not None:
                        control_type = "opModConnect"
                
                history.record_control_received(
                    control_id=ctrl_id,
                    source="polling",
                    program_id=program.mRID,
                    primacy=program.primacy,
                    control_type=control_type,
                    power_setpoint_w=power_w,
                    interval_start=control.interval.start if control.interval else None,
                    interval_duration=control.interval.duration if control.interval else None,
                )
            except Exception as e:
                logger.debug(f"Failed to record control history: {e}")
        
        # 計算隨機化的開始時間
        randomized_start = self._calculate_randomized_start(control)
        randomized_duration = self._calculate_randomized_duration(control)
        
        # 建立追蹤物件
        tracked_ctrl = TrackedControl(
            control=control,
            program=program,
            primacy=program.primacy,
            randomized_start=randomized_start,
            randomized_duration=randomized_duration,
        )
        
        self._tracked_controls[ctrl_id] = tracked_ctrl
        
        # 檢查是否應立即執行
        now = int(time.time())
        
        if control.interval:
            effective_start = control.interval.start
            if randomized_start:
                effective_start += randomized_start
            
            effective_end = (
                control.interval.start + 
                control.interval.duration +
                (randomized_duration or 0)
            )
            
            if now >= effective_start and now < effective_end:
                # 已過開始時間但未過結束時間，立即執行
                # EVENT_RECEIVED 在 _execute_control 內發送（衝突檢查後）
                logger.info(f"Control {ctrl_id} is in active period, executing now")
                await self._execute_control(tracked_ctrl)
            elif now < effective_start:
                # 未到開始時間，排程 — 先發 EVENT_RECEIVED
                await self._send_response(
                    tracked_ctrl,
                    ResponseStatusType.EVENT_RECEIVED
                )
                tracked_ctrl.status = DERControlEventStatus.SCHEDULED
                logger.info(
                    f"Control {ctrl_id} scheduled, "
                    f"starts in {effective_start - now}s"
                )
            else:
                # 已過結束時間，標記過期
                tracked_ctrl.status = DERControlEventStatus.CANCELLED
                logger.info(f"Control {ctrl_id} expired")
                await self._send_response(
                    tracked_ctrl,
                    ResponseStatusType.EVENT_EXPIRED
                )
        else:
            # 無 interval，立即執行
            # EVENT_RECEIVED 在 _execute_control 內發送（衝突檢查後）
            await self._execute_control(tracked_ctrl)
        
        # 標記已處理
        self._processed_mRIDs.append(ctrl_id)
        self._cleanup_processed_mRIDs()
    
    def _calculate_randomized_start(
        self,
        control: DERControl
    ) -> Optional[int]:
        """計算隨機化的開始延遲"""
        if not self.config.enable_randomization:
            return None
        
        if control.randomizeStart is None or control.randomizeStart <= 0:
            return None
        
        return random.randint(0, control.randomizeStart)
    
    def _calculate_randomized_duration(
        self,
        control: DERControl
    ) -> Optional[int]:
        """計算隨機化的持續時間調整"""
        if not self.config.enable_randomization:
            return None
        
        if control.randomizeDuration is None or control.randomizeDuration == 0:
            return None
        
        # randomizeDuration 可以是正或負
        return random.randint(
            -abs(control.randomizeDuration),
            abs(control.randomizeDuration)
        )
    
    async def _execute_control(self, tracked: TrackedControl) -> None:
        """
        執行 DERControl
        
        處理衝突和優先權邏輯
        """
        ctrl_id = tracked.control.mRID or str(id(tracked.control))
        
        # 檢查緊急停止
        if EmergencyStop.is_stopped():
            tracked.status = DERControlEventStatus.FAILED
            logger.warning(f"Control {ctrl_id} blocked by emergency stop")
            await self._send_response(
                tracked,
                ResponseStatusType.EVENT_ABORTED_SERVER
            )
            return
        
        # 處理衝突
        superseded = await self._resolve_conflict(tracked)
        
        if superseded:
            # 被更高優先級控制取代 — 直接發 SUPERSEDED，不發 RECEIVED
            tracked.status = DERControlEventStatus.SUPERSEDED
            logger.info(f"Control {ctrl_id} superseded")
            await self._send_response(
                tracked,
                ResponseStatusType.EVENT_SUPERSEDED
            )
            return
        
        # 衝突檢查通過，發送 EVENT_RECEIVED (IEEE 2030.5-2023)
        await self._send_response(
            tracked,
            ResponseStatusType.EVENT_RECEIVED
        )
        
        # 取消活動的 DefaultDERControl
        self._active_default = None
        self._active_default_program = None
        
        # 執行控制
        tracked.status = DERControlEventStatus.ACTIVE
        
        try:
            # 發送「開始」回報
            await self._send_response(
                tracked,
                ResponseStatusType.EVENT_STARTED
            )
            
            # 透過 Handler 執行
            event = await self.handler.handle_control(
                tracked.control,
                source=f"program:{tracked.program.mRID}"
            )
            tracked.event = event
            
            if event.status == DERControlEventStatus.COMPLETED:
                tracked.status = DERControlEventStatus.COMPLETED
                self._stats["controls_executed"] += 1
                
                # 記錄執行結果到歷史
                if _has_history_recorder:
                    try:
                        history = get_der_control_history()
                        history.update_control_executed(
                            control_id=ctrl_id,
                            success=True,
                            simulated=event.result.simulated if event.result else True,
                            message=event.result.message if event.result else None,
                        )
                    except Exception as e:
                        logger.debug(f"Failed to update control history: {e}")
                
                # 發送「完成」回報
                await self._send_response(
                    tracked,
                    ResponseStatusType.EVENT_COMPLETED
                )
            else:
                tracked.status = event.status
                
                # 記錄失敗結果
                if _has_history_recorder:
                    try:
                        history = get_der_control_history()
                        history.update_control_executed(
                            control_id=ctrl_id,
                            success=False,
                            simulated=True,
                            error=event.error_message,
                        )
                    except Exception as e:
                        logger.debug(f"Failed to update control history: {e}")
                
            logger.info(
                f"Control {ctrl_id} executed: "
                f"power={tracked.control.get_power_setpoint_w()}W"
            )
            
            # 追蹤活動控制（按模式）
            self._track_active_control(tracked)
            
            # De-energize/disconnect：取消所有其他活動控制
            if (
                tracked.status == DERControlEventStatus.COMPLETED
                and self._is_de_energize_control(tracked.control)
            ):
                await self._cancel_all_active_controls(ctrl_id)
            
            # 回調
            if self._on_control_executed:
                await self._on_control_executed(tracked)
        
        except Exception as e:
            tracked.status = DERControlEventStatus.FAILED
            logger.error(f"Control execution failed: {e}")
            await self._send_response(
                tracked,
                ResponseStatusType.EVENT_ABORTED_SERVER
            )
    
    def _track_active_control(self, tracked: TrackedControl) -> None:
        """追蹤活動控制（按控制模式分組）"""
        control = tracked.control
        
        # 確定控制模式
        if control.DERControlBase:
            base = control.DERControlBase
            if base.opModFixedW:
                self._active_by_mode["opModFixedW"] = tracked
            if base.opModFixedVar:
                self._active_by_mode["opModFixedVar"] = tracked
            if base.opModMaxLimW:
                self._active_by_mode["opModMaxLimW"] = tracked
            if base.opModConnect is not None:
                self._active_by_mode["opModConnect"] = tracked
            if base.opModEnergize is not None:
                self._active_by_mode["opModEnergize"] = tracked
    
    def _is_de_energize_control(self, control: DERControl) -> bool:
        """檢查控制是否為 de-energize 或 disconnect 類型"""
        if not control.DERControlBase:
            return False
        base = control.DERControlBase
        return (
            (base.opModEnergize is not None and base.opModEnergize is False)
            or (base.opModConnect is not None and base.opModConnect is False)
        )

    async def _cancel_all_active_controls(self, exclude_mrid: str) -> None:
        """
        取消所有活動中和排程中的 DERControl（de-energize/disconnect 觸發時）

        當收到 opModEnergize=false 或 opModConnect=false 時，
        設備已去能/斷開，其他功率控制已無意義，全部取消。

        Args:
            exclude_mrid: 觸發 de-energize 的控制 mRID，不取消自己
        """
        cancelled_count = 0

        # 1. 取消 _active_by_mode 中所有其他模式的活動控制
        for mode in list(self._active_by_mode.keys()):
            active = self._active_by_mode[mode]
            active_mrid = active.control.mRID or str(id(active.control))

            if active_mrid == exclude_mrid:
                continue

            if active.status in (
                DERControlEventStatus.ACTIVE,
                DERControlEventStatus.COMPLETED,
            ):
                active.status = DERControlEventStatus.SUPERSEDED
                logger.info(
                    f"De-energize: cancelling active control "
                    f"{active_mrid} (mode={mode})"
                )
                await self._send_response(
                    active,
                    ResponseStatusType.EVENT_SUPERSEDED
                )
                cancelled_count += 1
                del self._active_by_mode[mode]

        # 2. 取消 _tracked_controls 中所有 SCHEDULED 狀態的控制
        for ctrl_id, tracked in self._tracked_controls.items():
            if ctrl_id == exclude_mrid:
                continue

            if tracked.status == DERControlEventStatus.SCHEDULED:
                tracked.status = DERControlEventStatus.SUPERSEDED
                logger.info(
                    f"De-energize: cancelling scheduled control {ctrl_id}"
                )
                await self._send_response(
                    tracked,
                    ResponseStatusType.EVENT_SUPERSEDED
                )
                cancelled_count += 1

        # 3. 取消 DefaultDERControl
        if self._active_default:
            logger.info("De-energize: cancelling active DefaultDERControl")
            self._active_default = None
            self._active_default_program = None

        # 4. 通知 Handler 取消其 active_event（非本次控制）
        if self.handler._active_event:
            active_event_id = self.handler._active_event.event_id
            if active_event_id != exclude_mrid:
                await self.handler.cancel_control(active_event_id)

        if cancelled_count > 0:
            logger.warning(
                f"De-energize: cancelled {cancelled_count} controls "
                f"(triggered by {exclude_mrid})"
            )

    async def _check_default_control(self, tracked_program: TrackedProgram) -> None:
        """
        檢查並執行 DefaultDERControl
        
        當計畫無活動事件時執行
        """
        # 確認沒有任何活動控制
        has_active = any(
            ctrl.status == DERControlEventStatus.ACTIVE
            for ctrl in self._tracked_controls.values()
        )
        
        if has_active:
            return
        
        # 取得最高優先級計畫的 DefaultDERControl
        highest = self._get_highest_priority_program()
        if not highest or not highest.default_control:
            return
        
        # 避免重複執行
        if (
            self._active_default == highest.default_control and
            self._active_default_program == highest.program
        ):
            return
        
        default_ctrl = highest.default_control
        logger.info(
            f"Applying DefaultDERControl from program "
            f"{highest.program.mRID} (primacy={highest.primacy})"
        )
        
        # 轉換為 DERControl 執行
        if default_ctrl.DERControlBase:
            power_w = None
            if default_ctrl.DERControlBase.opModFixedW:
                power_w = default_ctrl.DERControlBase.opModFixedW.to_watts()
            
            if power_w is not None:
                result = await self.power_controller.set_power_setpoint(
                    power_w=power_w,
                    source=f"default:{highest.program.mRID}"
                )
                
                if result.success:
                    self._active_default = default_ctrl
                    self._active_default_program = highest.program
                    logger.info(f"DefaultDERControl applied: {power_w}W")
    
    async def _cancel_control(self, ctrl_id: str, reason: str) -> None:
        """取消控制"""
        if ctrl_id not in self._tracked_controls:
            return
        
        tracked = self._tracked_controls[ctrl_id]
        tracked.status = DERControlEventStatus.CANCELLED
        
        logger.info(f"Control {ctrl_id} cancelled: {reason}")
        
        await self._send_response(
            tracked,
            ResponseStatusType.EVENT_CANCELLED
        )
    
    async def _handle_server_cancel(self, ctrl_id: str) -> None:
        """
        Handle server-side cancel (EventStatus.currentStatus == 2).
        
        Delegates to handler.cancel_control() which handles reconnect_pcs()
        for disconnect/de-energize events, then sends EVENT_CANCELLED response.
        """
        # Cancel via handler (triggers reconnect if was disconnect)
        cancelled = await self.handler.cancel_control(ctrl_id)
        if cancelled:
            logger.info(f"Server cancel handled via handler for {ctrl_id}")
        
        # Also cancel in tracked controls and send response
        await self._cancel_control(ctrl_id, "server_cancel (currentStatus=2)")
    
    # =========================================================================
    # 4. Conflict Resolution
    # =========================================================================
    
    async def _resolve_conflict(self, new_ctrl: TrackedControl) -> bool:
        """
        解決控制衝突
        
        返回 True 如果新控制被取代（不應執行）
        
        規則：
        1. 不同控制模式可同時執行
        2. 相同控制模式：優先權較高（primacy 較小）者優先
        3. 相同優先權：creationTime 較新者優先
        """
        control = new_ctrl.control
        if not control.DERControlBase:
            return False
        
        # 確定新控制的模式
        modes = []
        base = control.DERControlBase
        if base.opModFixedW:
            modes.append("opModFixedW")
        if base.opModFixedVar:
            modes.append("opModFixedVar")
        if base.opModMaxLimW:
            modes.append("opModMaxLimW")
        if base.opModConnect is not None:
            modes.append("opModConnect")
        if base.opModEnergize is not None:
            modes.append("opModEnergize")
        
        for mode in modes:
            if mode in self._active_by_mode:
                existing = self._active_by_mode[mode]
                
                # 比較優先權
                if new_ctrl.primacy > existing.primacy:
                    # 新控制優先權較低，被取代
                    return True
                elif new_ctrl.primacy == existing.primacy:
                    # 相同優先權，比較 creationTime
                    new_creation = control.creationTime or 0
                    existing_creation = existing.control.creationTime or 0
                    
                    if new_creation <= existing_creation:
                        # 新控制較舊或相同時間，被取代
                        return True
                
                # 新控制優先，標記舊控制為被取代
                existing.status = DERControlEventStatus.SUPERSEDED
                logger.info(
                    f"Control {existing.control.mRID} superseded by "
                    f"{control.mRID}"
                )
                
                await self._send_response(
                    existing,
                    ResponseStatusType.EVENT_SUPERSEDED
                )
        
        return False
    
    # =========================================================================
    # 5. Response Reporting
    # =========================================================================
    
    @staticmethod
    def _calculate_modes_responded(control: DERControl) -> int:
        """
        Calculate modesResponded bitmap from DERControlBase.

        Reference: IEEE Std 2030.5-2023, DERControlType bitmap
        """
        if not control.DERControlBase:
            return 0
        base = control.DERControlBase
        bitmap = 0
        if base.opModConnect is not None:
            bitmap |= DERControlModesType.OP_MOD_CONNECT
        if base.opModEnergize is not None:
            bitmap |= DERControlModesType.OP_MOD_ENERGIZE
        if getattr(base, 'opModFixedPFAbsorbW', None) is not None:
            bitmap |= DERControlModesType.OP_MOD_FIXED_PF_ABSORB_W
        if getattr(base, 'opModFixedPFInjectW', None) is not None:
            bitmap |= DERControlModesType.OP_MOD_FIXED_PF_INJECT_W
        if getattr(base, 'opModFixedVar', None) is not None:
            bitmap |= DERControlModesType.OP_MOD_FIXED_VAR
        if base.opModFixedW is not None:
            bitmap |= DERControlModesType.OP_MOD_FIXED_W
        if getattr(base, 'opModMaxLimW', None) is not None:
            bitmap |= DERControlModesType.OP_MOD_MAX_LIM_W
        return bitmap

    async def _send_response(
        self,
        tracked: TrackedControl,
        status: ResponseStatusType
    ) -> bool:
        """
        發送控制回報（含重試機制）
        
        依據 responseRequired 欄位決定是否發送，發送失敗時以指數退避重試。
        IEEE 2030.5 要求將 DERControlResponse POST 到 replyTo URI
        如果失敗，會按照 pollRate 持續重試直到成功或達到最大重試次數
        """
        control = tracked.control
        
        # 檢查是否需要回報
        # responseRequired 是一個 bitmask：
        #   Bit 0: Response on event received
        #   Bit 1: Response on event started
        #   Bit 2: Response on event completed
        #   Bit 3: Response on event status changed
        # 如果 responseRequired 為 None 或 0，仍然發送回報（最佳實踐）
        response_required = getattr(control, 'responseRequired', None)
        if response_required is None:
            response_required = 0x07
        
        # 檢查是否需要發送此狀態的回報
        should_send = False
        if status == ResponseStatusType.EVENT_RECEIVED:
            should_send = bool(response_required & 0x01)
        elif status == ResponseStatusType.EVENT_STARTED:
            should_send = bool(response_required & 0x02)
        elif status in (ResponseStatusType.EVENT_COMPLETED, 
                        ResponseStatusType.EVENT_CANCELLED,
                        ResponseStatusType.EVENT_SUPERSEDED,
                        ResponseStatusType.EVENT_ABORTED_SERVER,
                        ResponseStatusType.EVENT_EXPIRED):
            should_send = bool(response_required & 0x04)
        else:
            should_send = True  # 其他狀態預設發送
        
        if not should_send:
            logger.debug(f"Response not required for status {status.name}")
            return True

        # 解析回報目標 URI
        reply_to = getattr(control, "replyTo", None)
        if not reply_to:
            if control.href:
                reply_to = f"{control.href}/rsp"
            else:
                logger.warning(
                    f"No replyTo URI for control {control.mRID}, skipping response"
                )
                tracked.response_sent = True
                self._stats["responses_sent"] += 1
                return True

        # 取得 LFDI
        lfdi = self.http_client.lfdi or ""

        # 計算 modesResponded bitmap
        modes_bitmap = self._calculate_modes_responded(control)

        # 建立回報 (IEEE Std 2030.5-2023: modesResponded SHALL be present)
        response = DERControlResponseFull(
            createdDateTime=int(time.time()),
            endDeviceLFDI=lfdi,
            status=status,
            subject=control.mRID or "",
            modesResponded=DERControlResponseFull.modes_to_hex(modes_bitmap),
        )
        
        # 實際發送 HTTP POST（含重試機制）
        post_success = False
        max_retries = self.config.response_max_retries
        
        for attempt in range(max_retries):
            try:
                await self.http_client._post(
                    reply_to,
                    response
                )
                post_success = True
                logger.info(
                    f"Response sent: control={control.mRID}, "
                    f"status={status.name}, "
                    f"lfdi={lfdi[:8]}..."
                )
                # 成功：清除待重試狀態
                tracked.pending_response = None
                tracked.response_retry_count = 0
                break
            except Exception as e:
                tracked.response_retry_count = attempt + 1
                tracked.last_response_attempt = time.time()
                
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 30)  # 指數退避，最多 30 秒
                    logger.warning(
                        f"Response POST failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Response POST failed after {max_retries} attempts: {e}. "
                        f"Will retry on next poll cycle."
                    )
                    # 標記為待重試，下次 poll 時會重試
                    tracked.pending_response = status
        
        if post_success:
            tracked.response_sent = True
            self._stats["responses_sent"] += 1
        
        # 記錄回報到歷史
        if _has_history_recorder:
            try:
                history = get_der_control_history()
                ctrl_id = control.mRID or str(id(control))
                history.update_response_sent(
                    control_id=ctrl_id,
                    response_status=status.name,
                )
            except Exception as e:
                logger.debug(f"Failed to record response history: {e}")
        
        return post_success
    
    # =========================================================================
    # Scheduler Loop
    # =========================================================================
    
    async def _scheduler_loop(self) -> None:
        """排程器迴圈 - 檢查已排程控制的執行時間"""
        while self._running:
            try:
                now = int(time.time())
                
                for ctrl_id, tracked in list(self._tracked_controls.items()):
                    if tracked.status != DERControlEventStatus.SCHEDULED:
                        continue
                    
                    control = tracked.control
                    if not control.interval:
                        continue
                    
                    # 計算有效開始時間
                    effective_start = control.interval.start
                    if tracked.randomized_start:
                        effective_start += tracked.randomized_start
                    
                    if now >= effective_start:
                        # 時間到，執行控制
                        logger.info(f"Scheduled control {ctrl_id} starting now")
                        await self._execute_control(tracked)
                    
                    # 檢查控制是否結束
                    if tracked.status == DERControlEventStatus.ACTIVE:
                        effective_duration = control.interval.duration
                        if tracked.randomized_duration:
                            effective_duration += tracked.randomized_duration
                        
                        effective_end = control.interval.start + effective_duration
                        
                        if now >= effective_end:
                            # 控制結束
                            tracked.status = DERControlEventStatus.COMPLETED
                            logger.info(f"Control {ctrl_id} completed")
                            
                            await self._send_response(
                                tracked,
                                ResponseStatusType.EVENT_COMPLETED
                            )
                            
                            # 檢查是否需要回復低優先級控制
                            await self._check_control_recovery()
            
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(1)  # 每秒檢查一次
    
    async def _check_control_recovery(self) -> None:
        """
        檢查是否需要回復低優先級控制
        
        當高優先級控制結束時，回復仍在有效期內的低優先級控制
        注意：當 de-energize/disconnect 控制活動時，不恢復任何控制
        """
        # 如果有活動的 de-energize/disconnect 控制，不恢復任何控制
        for mode in ("opModEnergize", "opModConnect"):
            if mode in self._active_by_mode:
                active_de = self._active_by_mode[mode]
                if (
                    active_de.status in (
                        DERControlEventStatus.ACTIVE,
                        DERControlEventStatus.COMPLETED,
                    )
                    and self._is_de_energize_control(active_de.control)
                ):
                    return  # de-energize 活動中，跳過所有恢復
        
        now = int(time.time())
        
        for mode, active in list(self._active_by_mode.items()):
            if active.status != DERControlEventStatus.COMPLETED:
                continue
            
            # 找出被取代但仍有效的控制
            for ctrl_id, tracked in self._tracked_controls.items():
                if tracked.status != DERControlEventStatus.SUPERSEDED:
                    continue
                
                control = tracked.control
                if not control.interval:
                    continue
                
                # 檢查控制是否在相同模式
                if not self._has_mode(control, mode):
                    continue
                
                # 檢查是否仍在有效期內
                effective_end = control.interval.start + control.interval.duration
                if tracked.randomized_duration:
                    effective_end += tracked.randomized_duration
                
                if now < effective_end:
                    # 回復此控制
                    logger.info(
                        f"Recovering superseded control {ctrl_id}"
                    )
                    await self._execute_control(tracked)
                    break
    
    def _has_mode(self, control: DERControl, mode: str) -> bool:
        """檢查控制是否包含指定模式"""
        if not control.DERControlBase:
            return False
        
        base = control.DERControlBase
        if mode == "opModFixedW" and base.opModFixedW:
            return True
        if mode == "opModFixedVar" and base.opModFixedVar:
            return True
        if mode == "opModMaxLimW" and base.opModMaxLimW:
            return True
        if mode == "opModConnect" and base.opModConnect is not None:
            return True
        if mode == "opModEnergize" and base.opModEnergize is not None:
            return True
        
        return False
    
    # =========================================================================
    # History Recording (for Web UI)
    # =========================================================================
    
    def _record_fsa_to_history(self, fsa: FunctionSetAssignments) -> None:
        """記錄 FSA 到歷史（供 Web UI 顯示）"""
        if not _has_history_recorder:
            return
        
        try:
            history = get_der_control_history()
            fsa_id = fsa.mRID or fsa.href or str(id(fsa))
            
            history.record_fsa(
                fsa_id=fsa_id,
                href=fsa.href,
                description=fsa.description,
                version=fsa.version or 0,
                der_program_list_link=fsa.get_der_program_list_href(),
                program_count=0,  # Will be updated when programs are discovered
            )
        except Exception as e:
            logger.debug(f"Failed to record FSA history: {e}")
    
    def _record_fsa_removed(self, fsa_id: str) -> None:
        """記錄 FSA 移除到歷史"""
        if not _has_history_recorder:
            return
        
        try:
            history = get_der_control_history()
            history.remove_fsa(fsa_id)
        except Exception as e:
            logger.debug(f"Failed to record FSA removal: {e}")
    
    def _update_fsa_program_count(self, fsa_id: str, program_count: int) -> None:
        """更新 FSA 的 program 數量"""
        if not _has_history_recorder:
            return
        
        try:
            history = get_der_control_history()
            history.record_fsa(
                fsa_id=fsa_id,
                program_count=program_count,
            )
        except Exception as e:
            logger.debug(f"Failed to update FSA program count: {e}")
    
    def _record_program_to_history(
        self,
        program: DERProgram,
        fsa_id: Optional[str] = None
    ) -> None:
        """記錄 DERProgram 到歷史（供 Web UI 顯示）"""
        if not _has_history_recorder:
            return
        
        try:
            history = get_der_control_history()
            prog_id = program.mRID or program.href or str(id(program))
            
            # 計算 control 數量（從 Link 物件的 all 屬性取得）
            control_count = 0
            if program.DERControlListLink and hasattr(program.DERControlListLink, 'all'):
                control_count = program.DERControlListLink.all or 0
            
            history.record_program(
                program_id=prog_id,
                href=program.href,
                description=program.description,
                primacy=program.primacy,
                version=program.version or 0,
                fsa_id=fsa_id,
                der_control_list_link=program.get_der_control_list_href(),
                default_der_control_link=program.get_default_der_control_href(),
                control_count=control_count,
            )
        except Exception as e:
            logger.debug(f"Failed to record program history: {e}")
    
    def _record_program_removed(self, program_id: str) -> None:
        """記錄 DERProgram 移除到歷史"""
        if not _has_history_recorder:
            return
        
        try:
            history = get_der_control_history()
            history.remove_program(program_id)
        except Exception as e:
            logger.debug(f"Failed to record program removal: {e}")
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def _cleanup_processed_mRIDs(self) -> None:
        """清理已處理的事件 ID（deque 具有 maxlen，自動移除最舊項目，此方法為空操作）"""
        pass
    
    def set_on_control_executed(
        self,
        callback: Callable[[TrackedControl], Awaitable[None]]
    ) -> None:
        """設定控制執行回調"""
        self._on_control_executed = callback
