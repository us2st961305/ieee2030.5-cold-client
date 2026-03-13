"""
External Integration API (外部整合介面)

此模組提供 IEEE 2030.5 Client 與外部程式整合的 API 介面。
外部程式（如 Modbus、CAN、REST API、gRPC 等）可以透過此 API：
1. 取得 DER 控制命令 (功率設定點、控制模式)
2. 回報 BMS 狀態資料
3. 接收功率控制指令
4. 查詢系統狀態

使用方式:
    from bms_2030_5_client.external_api import ExternalIntegrationAPI
    
    api = ExternalIntegrationAPI(client)
    
    # 取得控制命令
    command = await api.get_power_command()
    
    # 回報 BMS 狀態
    await api.report_bms_status(system_data, racks_data)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import IntEnum
from typing import Callable, Optional, List, Dict, Any, Union
from queue import Queue

from bms_2030_5_client.models import (
    BMSSnapshot,
    SystemData,
    RackData,
    RackStatus,
)
from bms_2030_5_client.power_control import (
    SafePowerController,
    PowerControlConfig,
    PowerControlResult,
    PowerLimits,
    ControlMode,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Types for API
# =============================================================================

class PowerCommandType(IntEnum):
    """功率命令類型"""
    NONE = 0              # 無命令
    SET_POWER = 1         # 設定功率
    SET_CHARGE = 2        # 設定充電功率
    SET_DISCHARGE = 3     # 設定放電功率
    LIMIT_POWER = 4       # 限制功率
    EMERGENCY_STOP = 5    # 緊急停止


class ControlSource(IntEnum):
    """控制來源"""
    MANUAL = 0            # 手動
    IEEE2030_5 = 1        # IEEE 2030.5 DER Control
    SCHEDULE = 2          # 排程
    DRLC = 3              # Demand Response Load Control
    PRICING = 4           # 價格信號
    LOCAL = 5             # 本地控制


@dataclass
class PowerCommand:
    """
    功率控制命令
    
    外部程式應定期查詢此命令，並根據命令執行功率控制。
    
    Attributes:
        command_type: 命令類型 (PowerCommandType)
        power_w: 功率設定點 (W)，正值=放電，負值=充電
        duration_s: 命令持續時間 (秒)，0 表示直到下一個命令
        start_time: 命令開始時間 (Unix timestamp)
        end_time: 命令結束時間 (Unix timestamp)，0 表示無限
        source: 控制來源 (ControlSource)
        priority: 優先級 (0-255，0 最高)
        control_id: 控制 ID (IEEE 2030.5 DERControl mRID)
        randomize_start_s: 開始時間隨機化 (秒)
        randomize_duration_s: 持續時間隨機化 (秒)
        ramp_rate_w_per_s: 功率爬坡速率 (W/s)，0 表示不限制
        is_active: 命令是否有效
        sequence_number: 命令序號 (遞增)
        created_at: 命令創建時間
    """
    command_type: PowerCommandType = PowerCommandType.NONE
    power_w: int = 0
    duration_s: int = 0
    start_time: int = 0
    end_time: int = 0
    source: ControlSource = ControlSource.MANUAL
    priority: int = 128
    control_id: str = ""
    randomize_start_s: int = 0
    randomize_duration_s: int = 0
    ramp_rate_w_per_s: int = 0
    is_active: bool = False
    sequence_number: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "command_type": self.command_type.value,
            "command_type_name": self.command_type.name,
            "power_w": self.power_w,
            "duration_s": self.duration_s,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "source": self.source.value,
            "source_name": self.source.name,
            "priority": self.priority,
            "control_id": self.control_id,
            "randomize_start_s": self.randomize_start_s,
            "randomize_duration_s": self.randomize_duration_s,
            "ramp_rate_w_per_s": self.ramp_rate_w_per_s,
            "is_active": self.is_active,
            "sequence_number": self.sequence_number,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BMSStatusReport:
    """
    BMS 狀態回報資料結構
    
    Modbus 外部程式應定期將此資料回報給 API。
    
    Attributes:
        timestamp: 資料時間戳
        system_voltage: 系統電壓 (V)
        system_current: 系統電流 (A)，正值=充電，負值=放電
        system_soc: 系統 SOC (%)
        system_power: 系統功率 (W)
        charge_energy_kwh: 今日充電能量 (kWh)
        discharge_energy_kwh: 今日放電能量 (kWh)
        max_temperature: 最高溫度 (°C)
        min_temperature: 最低溫度 (°C)
        avg_temperature: 平均溫度 (°C)
        active_rack_count: 活動電池架數量
        total_rack_count: 總電池架數量
        alarm_status: 告警狀態 (bitfield)
        system_status: 系統狀態 (0=離線, 1=線上)
        allowed_charge_power_w: 允許充電功率 (W)
        allowed_discharge_power_w: 允許放電功率 (W)
        remaining_capacity_ah: 剩餘容量 (Ah)
        full_charge_capacity_ah: 滿充容量 (Ah)
        soh: 健康狀態 (%)
        cycle_count: 循環次數
        rack_data: 各電池架詳細資料 (可選)
    """
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    system_voltage: float = 0.0
    system_current: float = 0.0
    system_soc: float = 0.0
    system_power: float = 0.0
    charge_energy_kwh: float = 0.0
    discharge_energy_kwh: float = 0.0
    max_temperature: float = 0.0
    min_temperature: float = 0.0
    avg_temperature: float = 0.0
    active_rack_count: int = 0
    total_rack_count: int = 0
    alarm_status: int = 0
    system_status: int = 0
    allowed_charge_power_w: float = 0.0
    allowed_discharge_power_w: float = 0.0
    remaining_capacity_ah: float = 0.0
    full_charge_capacity_ah: float = 0.0
    soh: float = 100.0
    cycle_count: int = 0
    rack_data: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "system_voltage": self.system_voltage,
            "system_current": self.system_current,
            "system_soc": self.system_soc,
            "system_power": self.system_power,
            "charge_energy_kwh": self.charge_energy_kwh,
            "discharge_energy_kwh": self.discharge_energy_kwh,
            "max_temperature": self.max_temperature,
            "min_temperature": self.min_temperature,
            "avg_temperature": self.avg_temperature,
            "active_rack_count": self.active_rack_count,
            "total_rack_count": self.total_rack_count,
            "alarm_status": self.alarm_status,
            "system_status": self.system_status,
            "allowed_charge_power_w": self.allowed_charge_power_w,
            "allowed_discharge_power_w": self.allowed_discharge_power_w,
            "remaining_capacity_ah": self.remaining_capacity_ah,
            "full_charge_capacity_ah": self.full_charge_capacity_ah,
            "soh": self.soh,
            "cycle_count": self.cycle_count,
            "rack_data": self.rack_data,
        }


@dataclass 
class RackStatusReport:
    """
    電池架狀態回報資料
    
    Attributes:
        rack_id: 電池架 ID (0-23)
        voltage: 電池架電壓 (V)
        current: 電池架電流 (A)
        soc: 電池架 SOC (%)
        soh: 電池架 SOH (%)
        cell_max_voltage: 最高電芯電壓 (V)
        cell_min_voltage: 最低電芯電壓 (V)
        cell_max_temp: 最高電芯溫度 (°C)
        cell_min_temp: 最低電芯溫度 (°C)
        status: 狀態 (0=離線, 1=待機, 2=充電, 3=放電, 4=故障)
        alarm_status: 告警狀態 (bitfield)
    """
    rack_id: int = 0
    voltage: float = 0.0
    current: float = 0.0
    soc: float = 0.0
    soh: float = 100.0
    cell_max_voltage: float = 0.0
    cell_min_voltage: float = 0.0
    cell_max_temp: float = 0.0
    cell_min_temp: float = 0.0
    status: int = 0
    alarm_status: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return asdict(self)


@dataclass
class CommandAcknowledgment:
    """
    命令確認回應
    
    Modbus 程式執行命令後應回報此確認。
    
    Attributes:
        sequence_number: 命令序號 (對應 PowerCommand.sequence_number)
        success: 是否成功執行
        actual_power_w: 實際設定的功率 (W)
        error_code: 錯誤碼 (0=無錯誤)
        error_message: 錯誤訊息
        executed_at: 執行時間
    """
    sequence_number: int = 0
    success: bool = True
    actual_power_w: int = 0
    error_code: int = 0
    error_message: str = ""
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class APIStatus:
    """API 狀態資訊"""
    is_connected: bool = False
    ieee2030_5_connected: bool = False
    last_command_time: Optional[datetime] = None
    last_status_time: Optional[datetime] = None
    pending_commands: int = 0
    total_commands_sent: int = 0
    total_commands_acked: int = 0
    simulation_mode: bool = True
    control_mode: str = "dry_run"
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "is_connected": self.is_connected,
            "ieee2030_5_connected": self.ieee2030_5_connected,
            "last_command_time": self.last_command_time.isoformat() if self.last_command_time else None,
            "last_status_time": self.last_status_time.isoformat() if self.last_status_time else None,
            "pending_commands": self.pending_commands,
            "total_commands_sent": self.total_commands_sent,
            "total_commands_acked": self.total_commands_acked,
            "simulation_mode": self.simulation_mode,
            "control_mode": self.control_mode,
        }


# =============================================================================
# External Integration API
# =============================================================================

class ExternalIntegrationAPI:
    """
    外部整合 API
    
    此類別提供 IEEE 2030.5 Client 與外部程式之間的橋樑。
    支援各種通訊協定（Modbus、CAN、REST API、gRPC 等）的外部程式整合。
    
    架構:
        ┌─────────────────┐     ┌──────────────────────────┐     ┌──────────────┐
        │  IEEE 2030.5    │────▶│  ExternalIntegrationAPI  │◀────│   外部程式    │
        │     Server      │     │                          │     │ (任意協定)   │
        └─────────────────┘     └──────────────────────────┘     └──────────────┘
               ▲                         │                              │
               │                         ▼                              ▼
               │                  ┌────────────┐                 ┌────────────┐
               │                  │ PowerCommand│                 │   PCS      │
               │                  └────────────┘                 │   BMS      │
               │                                                 └────────────┘
               │                         ▲
               └─────────────────────────┘
                    BMS 狀態回報
    
    使用範例:
        # 初始化
        api = ExternalIntegrationAPI()
        
        # 外部程式定期查詢命令
        command = await api.get_power_command()
        if command.is_active:
            # 執行功率控制
            pcs.set_power(command.power_w)
            # 回報確認
            await api.acknowledge_command(command.sequence_number, success=True)
        
        # 外部程式定期回報狀態
        status = BMSStatusReport(
            system_voltage=750.0,
            system_current=100.0,
            system_soc=75.0,
            # ...
        )
        await api.report_bms_status(status)
    """
    
    def __init__(
        self,
        bms_client: Optional[Any] = None,
        power_controller: Optional[SafePowerController] = None,
        max_command_queue: int = 100,
    ):
        """
        初始化外部整合 API
        
        Args:
            bms_client: BMSClient 實例 (可選，稍後透過 set_client 設定)
            power_controller: 功率控制器 (可選)
            max_command_queue: 命令佇列最大長度
        """
        self._client = bms_client
        self._power_controller = power_controller
        
        # 命令管理
        self._current_command: Optional[PowerCommand] = None
        self._command_sequence: int = 0
        self._command_history: List[PowerCommand] = []
        self._max_history = 100
        
        # 狀態追蹤
        self._last_status: Optional[BMSStatusReport] = None
        self._last_status_time: Optional[datetime] = None
        self._last_command_time: Optional[datetime] = None
        
        # 統計
        self._total_commands_sent: int = 0
        self._total_commands_acked: int = 0
        
        # 回調函數
        self._status_callbacks: List[Callable[[BMSStatusReport], None]] = []
        self._command_callbacks: List[Callable[[PowerCommand], None]] = []
        
        # 命令接收回調 (供 DER Control 模組使用)
        self._der_control_callback: Optional[Callable[[PowerCommand], None]] = None
        
        logger.info("ExternalIntegrationAPI initialized")
    
    def set_client(self, client: Any) -> None:
        """設定 BMSClient 實例"""
        self._client = client
        logger.info("BMSClient connected to ExternalIntegrationAPI")
    
    def set_power_controller(self, controller: SafePowerController) -> None:
        """設定功率控制器"""
        self._power_controller = controller
        logger.info("PowerController connected to ExternalIntegrationAPI")
    
    def set_der_control_callback(
        self, 
        callback: Callable[[PowerCommand], None]
    ) -> None:
        """
        設定 DER Control 命令回調
        
        當收到 IEEE 2030.5 DER Control 命令時會調用此回調。
        
        Args:
            callback: 回調函數，接收 PowerCommand 參數
        """
        self._der_control_callback = callback
        logger.info("DER Control callback registered")
    
    # =========================================================================
    # 命令相關 API
    # =========================================================================
    
    async def get_power_command(self) -> PowerCommand:
        """
        取得當前功率控制命令
        
        Modbus 程式應定期呼叫此方法取得最新的功率控制命令。
        
        Returns:
            PowerCommand: 當前有效的功率命令
        """
        if self._current_command is None:
            return PowerCommand(command_type=PowerCommandType.NONE)
        
        # 檢查命令是否已過期
        now = int(time.time())
        if self._current_command.end_time > 0 and now > self._current_command.end_time:
            logger.info(f"Command expired: seq={self._current_command.sequence_number}")
            self._current_command.is_active = False
        
        return self._current_command
    
    async def get_power_command_dict(self) -> Dict[str, Any]:
        """
        取得當前功率控制命令 (字典格式)
        
        Returns:
            dict: 命令資料的字典格式
        """
        command = await self.get_power_command()
        return command.to_dict()
    
    async def set_power_command(
        self,
        power_w: int,
        command_type: PowerCommandType = PowerCommandType.SET_POWER,
        source: ControlSource = ControlSource.IEEE2030_5,
        duration_s: int = 0,
        priority: int = 128,
        control_id: str = "",
        ramp_rate_w_per_s: int = 0,
    ) -> PowerCommand:
        """
        設定功率控制命令
        
        此方法由 IEEE 2030.5 DER Control 模組呼叫，設定新的功率命令。
        
        Args:
            power_w: 功率設定點 (W)，正值=放電，負值=充電
            command_type: 命令類型
            source: 控制來源
            duration_s: 持續時間 (秒)，0=無限
            priority: 優先級 (0-255，0 最高)
            control_id: IEEE 2030.5 DERControl mRID
            ramp_rate_w_per_s: 爬坡速率 (W/s)
        
        Returns:
            PowerCommand: 新創建的命令
        """
        self._command_sequence += 1
        now = int(time.time())
        
        command = PowerCommand(
            command_type=command_type,
            power_w=power_w,
            duration_s=duration_s,
            start_time=now,
            end_time=now + duration_s if duration_s > 0 else 0,
            source=source,
            priority=priority,
            control_id=control_id,
            ramp_rate_w_per_s=ramp_rate_w_per_s,
            is_active=True,
            sequence_number=self._command_sequence,
            created_at=datetime.now(timezone.utc),
        )
        
        # 更新當前命令
        self._current_command = command
        self._last_command_time = datetime.now(timezone.utc)
        self._total_commands_sent += 1
        
        # 儲存歷史
        self._command_history.append(command)
        if len(self._command_history) > self._max_history:
            self._command_history.pop(0)
        
        logger.info(
            f"Power command set: seq={command.sequence_number}, "
            f"power={power_w}W, type={command_type.name}, source={source.name}"
        )
        
        # 調用回調
        for callback in self._command_callbacks:
            try:
                callback(command)
            except Exception as e:
                logger.error(f"Command callback error: {e}")
        
        return command
    
    async def acknowledge_command(
        self,
        sequence_number: int,
        success: bool,
        actual_power_w: int = 0,
        error_code: int = 0,
        error_message: str = "",
    ) -> bool:
        """
        確認命令執行結果
        
        Modbus 程式執行完命令後應呼叫此方法回報結果。
        
        Args:
            sequence_number: 命令序號
            success: 是否成功
            actual_power_w: 實際設定的功率 (W)
            error_code: 錯誤碼
            error_message: 錯誤訊息
        
        Returns:
            bool: 確認是否被接受
        """
        if self._current_command is None:
            logger.warning(f"No current command to acknowledge (seq={sequence_number})")
            return False
        
        if self._current_command.sequence_number != sequence_number:
            logger.warning(
                f"Sequence mismatch: expected {self._current_command.sequence_number}, "
                f"got {sequence_number}"
            )
            return False
        
        self._total_commands_acked += 1
        
        ack = CommandAcknowledgment(
            sequence_number=sequence_number,
            success=success,
            actual_power_w=actual_power_w,
            error_code=error_code,
            error_message=error_message,
            executed_at=datetime.now(timezone.utc),
        )
        
        if success:
            logger.info(
                f"Command acknowledged: seq={sequence_number}, "
                f"actual_power={actual_power_w}W"
            )
        else:
            logger.warning(
                f"Command failed: seq={sequence_number}, "
                f"error={error_code}: {error_message}"
            )
        
        return True
    
    async def cancel_command(self, sequence_number: Optional[int] = None) -> bool:
        """
        取消命令
        
        Args:
            sequence_number: 要取消的命令序號 (None=取消當前命令)
        
        Returns:
            bool: 是否成功取消
        """
        if self._current_command is None:
            return False
        
        if sequence_number is not None:
            if self._current_command.sequence_number != sequence_number:
                return False
        
        self._current_command.is_active = False
        logger.info(f"Command cancelled: seq={self._current_command.sequence_number}")
        return True
    
    async def emergency_stop(self, reason: str = "Manual trigger") -> bool:
        """
        緊急停止
        
        Args:
            reason: 停止原因
        
        Returns:
            bool: 是否成功觸發
        """
        from bms_2030_5_client.power_control import EmergencyStop
        
        EmergencyStop.trigger(reason)
        
        # 設定緊急停止命令
        await self.set_power_command(
            power_w=0,
            command_type=PowerCommandType.EMERGENCY_STOP,
            source=ControlSource.MANUAL,
            priority=0,  # 最高優先級
        )
        
        logger.critical(f"Emergency stop triggered: {reason}")
        return True
    
    async def get_command_history(
        self,
        limit: int = 20,
        source: Optional[ControlSource] = None,
    ) -> List[Dict[str, Any]]:
        """
        取得命令歷史
        
        Args:
            limit: 最大回傳數量
            source: 過濾特定來源
        
        Returns:
            List[dict]: 命令歷史列表
        """
        history = self._command_history[-limit:]
        
        if source is not None:
            history = [c for c in history if c.source == source]
        
        return [c.to_dict() for c in history]
    
    # =========================================================================
    # 狀態回報 API
    # =========================================================================
    
    async def report_bms_status(self, status: BMSStatusReport) -> bool:
        """
        回報 BMS 狀態
        
        Modbus 程式應定期呼叫此方法回報 BMS 狀態。
        
        Args:
            status: BMS 狀態資料
        
        Returns:
            bool: 是否成功接收
        """
        self._last_status = status
        self._last_status_time = datetime.now(timezone.utc)
        
        logger.debug(
            f"BMS status received: SOC={status.system_soc:.1f}%, "
            f"Power={status.system_power:.1f}W, "
            f"Racks={status.active_rack_count}/{status.total_rack_count}"
        )
        
        # 更新功率控制器狀態
        if self._power_controller:
            self._power_controller.update_current_state(
                current_power_w=int(status.system_power),
                current_soc=status.system_soc,
            )
        
        # 調用回調
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception as e:
                logger.error(f"Status callback error: {e}")
        
        return True
    
    async def report_bms_status_dict(self, status_dict: Dict[str, Any]) -> bool:
        """
        回報 BMS 狀態 (字典格式)
        
        Args:
            status_dict: BMS 狀態字典
        
        Returns:
            bool: 是否成功接收
        """
        # 處理 timestamp
        timestamp = status_dict.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        status = BMSStatusReport(
            timestamp=timestamp,
            system_voltage=status_dict.get("system_voltage", 0.0),
            system_current=status_dict.get("system_current", 0.0),
            system_soc=status_dict.get("system_soc", 0.0),
            system_power=status_dict.get("system_power", 0.0),
            charge_energy_kwh=status_dict.get("charge_energy_kwh", 0.0),
            discharge_energy_kwh=status_dict.get("discharge_energy_kwh", 0.0),
            max_temperature=status_dict.get("max_temperature", 0.0),
            min_temperature=status_dict.get("min_temperature", 0.0),
            avg_temperature=status_dict.get("avg_temperature", 0.0),
            active_rack_count=status_dict.get("active_rack_count", 0),
            total_rack_count=status_dict.get("total_rack_count", 0),
            alarm_status=status_dict.get("alarm_status", 0),
            system_status=status_dict.get("system_status", 0),
            allowed_charge_power_w=status_dict.get("allowed_charge_power_w", 0.0),
            allowed_discharge_power_w=status_dict.get("allowed_discharge_power_w", 0.0),
            remaining_capacity_ah=status_dict.get("remaining_capacity_ah", 0.0),
            full_charge_capacity_ah=status_dict.get("full_charge_capacity_ah", 0.0),
            soh=status_dict.get("soh", 100.0),
            cycle_count=status_dict.get("cycle_count", 0),
            rack_data=status_dict.get("rack_data", []),
        )
        
        return await self.report_bms_status(status)
    
    async def get_last_bms_status(self) -> Optional[Dict[str, Any]]:
        """
        取得最後回報的 BMS 狀態
        
        Returns:
            dict: BMS 狀態字典，若無則回傳 None
        """
        if self._last_status is None:
            return None
        return self._last_status.to_dict()
    
    # =========================================================================
    # 系統狀態 API
    # =========================================================================
    
    async def get_api_status(self) -> APIStatus:
        """
        取得 API 狀態
        
        Returns:
            APIStatus: API 狀態資訊
        """
        ieee_connected = False
        if self._client:
            ieee_connected = (
                hasattr(self._client, 'ieee2030_5_client') and
                self._client.ieee2030_5_client.connected
            )
        
        simulation_mode = True
        control_mode = "dry_run"
        if self._power_controller:
            simulation_mode = self._power_controller.simulation_mode
            control_mode = self._power_controller.control_mode.value
        
        pending = 0
        if self._current_command and self._current_command.is_active:
            pending = 1
        
        return APIStatus(
            is_connected=self._client is not None,
            ieee2030_5_connected=ieee_connected,
            last_command_time=self._last_command_time,
            last_status_time=self._last_status_time,
            pending_commands=pending,
            total_commands_sent=self._total_commands_sent,
            total_commands_acked=self._total_commands_acked,
            simulation_mode=simulation_mode,
            control_mode=control_mode,
        )
    
    async def get_api_status_dict(self) -> Dict[str, Any]:
        """
        取得 API 狀態 (字典格式)
        
        Returns:
            dict: API 狀態字典
        """
        status = await self.get_api_status()
        return status.to_dict()
    
    async def get_power_limits(self) -> Dict[str, Any]:
        """
        取得功率限制
        
        Returns:
            dict: 功率限制資訊
        """
        if self._power_controller is None:
            return {
                "max_charge_w": 100000,
                "max_discharge_w": 100000,
                "max_ramp_rate_w_per_s": 10000,
                "min_soc_percent": 10.0,
                "max_soc_percent": 90.0,
            }
        
        limits = self._power_controller.config.limits
        return {
            "max_charge_w": limits.max_charge_w,
            "max_discharge_w": limits.max_discharge_w,
            "max_ramp_rate_w_per_s": limits.max_ramp_rate_w_per_s,
            "min_soc_percent": limits.min_soc_percent,
            "max_soc_percent": limits.max_soc_percent,
        }
    
    # =========================================================================
    # 回調註冊
    # =========================================================================
    
    def add_status_callback(
        self,
        callback: Callable[[BMSStatusReport], None]
    ) -> None:
        """
        註冊 BMS 狀態回調
        
        Args:
            callback: 狀態更新時調用的函數
        """
        self._status_callbacks.append(callback)
    
    def add_command_callback(
        self,
        callback: Callable[[PowerCommand], None]
    ) -> None:
        """
        註冊命令回調
        
        Args:
            callback: 新命令發出時調用的函數
        """
        self._command_callbacks.append(callback)
    
    def remove_status_callback(
        self,
        callback: Callable[[BMSStatusReport], None]
    ) -> None:
        """移除狀態回調"""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    def remove_command_callback(
        self,
        callback: Callable[[PowerCommand], None]
    ) -> None:
        """移除命令回調"""
        if callback in self._command_callbacks:
            self._command_callbacks.remove(callback)


# =============================================================================
# 全域 API 實例
# =============================================================================

_external_api_instance: Optional[ExternalIntegrationAPI] = None


def get_external_api() -> ExternalIntegrationAPI:
    """
    取得全域外部整合 API 實例
    
    Returns:
        ExternalIntegrationAPI: 單例實例
    """
    global _external_api_instance
    if _external_api_instance is None:
        _external_api_instance = ExternalIntegrationAPI()
    return _external_api_instance


def init_external_api(
    bms_client: Optional[Any] = None,
    power_controller: Optional[SafePowerController] = None,
) -> ExternalIntegrationAPI:
    """
    初始化全域外部整合 API 實例
    
    Args:
        bms_client: BMSClient 實例
        power_controller: 功率控制器
    
    Returns:
        ExternalIntegrationAPI: 初始化的實例
    """
    global _external_api_instance
    _external_api_instance = ExternalIntegrationAPI(
        bms_client=bms_client,
        power_controller=power_controller,
    )
    return _external_api_instance


# =============================================================================
# 向後相容別名 (Backward Compatibility Aliases)
# =============================================================================

# 保留舊名稱以維持向後相容
ModbusIntegrationAPI = ExternalIntegrationAPI
get_modbus_api = get_external_api
init_modbus_api = init_external_api


# =============================================================================
# 導出
# =============================================================================

__all__ = [
    # Enums
    "PowerCommandType",
    "ControlSource",
    # Data classes
    "PowerCommand",
    "BMSStatusReport",
    "RackStatusReport",
    "CommandAcknowledgment",
    "APIStatus",
    # Main API
    "ExternalIntegrationAPI",
    # Factory functions
    "get_external_api",
    "init_external_api",
    # Backward compatibility aliases
    "ModbusIntegrationAPI",
    "get_modbus_api",
    "init_modbus_api",
]
