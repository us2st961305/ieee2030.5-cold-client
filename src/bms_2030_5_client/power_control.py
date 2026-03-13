"""
Power Control Safety Module (功率控制安全模組)

此模組提供安全的功率控制介面，確保開發和測試時不會意外向 PCS 發送指令。

使用方式:
    from bms_2030_5_client.power_control import (
        SafePowerController,
        ControlMode,
        PowerLimits,
        PowerValidator,
    )
    
    controller = SafePowerController(config)
    result = await controller.set_power_setpoint(50000)  # 50kW (模擬模式)
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

# 專用的功率控制審計日誌
power_audit_logger = logging.getLogger("power_control.audit")

# Regex to strip control characters and ANSI escape codes for log injection prevention
# ANSI escape pattern must come first to match full sequence before char class consumes \x1b
_LOG_SANITIZE_RE = re.compile(r"\x1b\[[0-9;]*m|[\x00-\x08\x0a-\x1f\x7f]")
power_audit_logger.setLevel(logging.INFO)

logger = logging.getLogger(__name__)


class ControlMode(Enum):
    """功率控制模式"""
    SIMULATION = "simulation"   # 模擬模式：只記錄，不執行任何實際控制
    DRY_RUN = "dry_run"         # 乾跑模式：完整驗證流程但不執行
    PRODUCTION = "production"   # 生產模式：需要特殊授權才能啟用


class PowerControlError(Exception):
    """功率控制錯誤基類"""
    pass


class SafetyError(PowerControlError):
    """安全檢查錯誤"""
    pass


class PowerLimitExceeded(PowerControlError):
    """功率超出限制"""
    pass


class SimulationModeRequired(SafetyError):
    """需要模擬模式"""
    pass


class AuthorizationRequired(SafetyError):
    """需要授權"""
    pass


@dataclass
class PowerLimits:
    """功率限制配置"""
    max_charge_w: int = 100_000       # 最大充電功率 (W)，負值表示充電
    max_discharge_w: int = 100_000    # 最大放電功率 (W)，正值表示放電
    max_ramp_rate_w_per_s: int = 10_000  # 最大功率變化速率 (W/s)
    min_soc_percent: float = 10.0     # 最低 SOC 限制 (%)
    max_soc_percent: float = 90.0     # 最高 SOC 限制 (%)
    
    def __post_init__(self):
        """驗證限制值的合理性"""
        if self.max_charge_w < 0:
            raise ValueError("max_charge_w must be positive")
        if self.max_discharge_w < 0:
            raise ValueError("max_discharge_w must be positive")
        if not (0 <= self.min_soc_percent < self.max_soc_percent <= 100):
            raise ValueError("Invalid SOC limits")


@dataclass
class PowerControlConfig:
    """功率控制配置"""
    simulation_mode: bool = True  # 預設必須為 True
    limits: PowerLimits = field(default_factory=PowerLimits)
    require_confirmation: bool = True
    log_all_requests: bool = True
    
    @classmethod
    def from_env(cls) -> "PowerControlConfig":
        """從環境變數創建配置"""
        simulation_mode = os.getenv(
            "POWER_CONTROL_SIMULATION", "true"
        ).lower() == "true"
        
        return cls(
            simulation_mode=simulation_mode,
            limits=PowerLimits(
                max_charge_w=int(os.getenv("MAX_CHARGE_POWER_W", "100000")),
                max_discharge_w=int(os.getenv("MAX_DISCHARGE_POWER_W", "100000")),
            )
        )


@dataclass
class PowerControlResult:
    """功率控制結果"""
    request_id: str
    mode: ControlMode
    requested_power_w: int
    executed: bool
    simulated: bool
    timestamp: datetime
    errors: list[str] = field(default_factory=list)
    message: str = ""
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class PowerValidator:
    """功率驗證器"""
    
    def __init__(self, limits: PowerLimits):
        self.limits = limits
    
    def validate(
        self,
        requested_power_w: int,
        current_soc: Optional[float] = None
    ) -> list[str]:
        """
        驗證功率請求是否在安全範圍內
        
        Args:
            requested_power_w: 請求的功率 (W)
                              正值 = 放電, 負值 = 充電
            current_soc: 當前 SOC (%), 如果提供則進行 SOC 檢查
        
        Returns:
            錯誤列表，空列表表示驗證通過
        """
        errors = []
        
        # 充電功率檢查（負值表示充電）
        if requested_power_w < 0:
            if abs(requested_power_w) > self.limits.max_charge_w:
                errors.append(
                    f"Charge power {abs(requested_power_w)}W exceeds limit "
                    f"{self.limits.max_charge_w}W"
                )
            if current_soc is not None and current_soc >= self.limits.max_soc_percent:
                errors.append(
                    f"Cannot charge: SOC {current_soc}% at or above max limit "
                    f"{self.limits.max_soc_percent}%"
                )
        
        # 放電功率檢查（正值表示放電）
        if requested_power_w > 0:
            if requested_power_w > self.limits.max_discharge_w:
                errors.append(
                    f"Discharge power {requested_power_w}W exceeds limit "
                    f"{self.limits.max_discharge_w}W"
                )
            if current_soc is not None and current_soc <= self.limits.min_soc_percent:
                errors.append(
                    f"Cannot discharge: SOC {current_soc}% at or below min limit "
                    f"{self.limits.min_soc_percent}%"
                )
        
        return errors
    
    def validate_ramp_rate(
        self,
        current_power_w: int,
        target_power_w: int,
        time_interval_s: float
    ) -> list[str]:
        """驗證功率變化速率"""
        errors = []
        
        power_change = abs(target_power_w - current_power_w)
        ramp_rate = power_change / time_interval_s if time_interval_s > 0 else float('inf')
        
        if ramp_rate > self.limits.max_ramp_rate_w_per_s:
            errors.append(
                f"Ramp rate {ramp_rate:.0f}W/s exceeds limit "
                f"{self.limits.max_ramp_rate_w_per_s}W/s"
            )
        
        return errors


class EmergencyStop:
    """緊急停止單例（thread-safe）"""
    
    _lock = threading.Lock()
    _stopped: bool = False
    _reason: Optional[str] = None
    _timestamp: Optional[datetime] = None
    
    @classmethod
    def trigger(cls, reason: str) -> None:
        """觸發緊急停止"""
        with cls._lock:
            cls._stopped = True
            cls._reason = reason
            cls._timestamp = datetime.now(timezone.utc)
            safe_reason = _LOG_SANITIZE_RE.sub("", reason)[:200]
            power_audit_logger.critical(
                f"EMERGENCY_STOP | reason={safe_reason} | timestamp={cls._timestamp.isoformat()}"
            )
    
    @classmethod
    def is_stopped(cls) -> bool:
        """檢查是否已觸發緊急停止"""
        with cls._lock:
            return cls._stopped
    
    @classmethod
    def get_status(cls) -> dict:
        """獲取緊急停止狀態"""
        with cls._lock:
            return {
                "stopped": cls._stopped,
                "reason": cls._reason,
                "timestamp": cls._timestamp.isoformat() if cls._timestamp else None
            }
    
    @classmethod
    def reset(cls, authorization_token: str) -> bool:
        """
        重置緊急停止狀態
        
        需要有效的授權 token
        """
        expected_token = os.getenv("POWER_CONTROL_SAFETY_TOKEN")
        if not expected_token or not hmac.compare_digest(
            authorization_token.encode(), expected_token.encode()
        ):
            power_audit_logger.warning("Failed emergency stop reset: invalid token")
            return False
        
        with cls._lock:
            safe_reason = _LOG_SANITIZE_RE.sub("", cls._reason or "")[:200]
            power_audit_logger.warning(
                f"EMERGENCY_STOP_RESET | previous_reason={safe_reason}"
            )
            cls._stopped = False
            cls._reason = None
            cls._timestamp = None
        return True


class SafePowerController:
    """
    安全的功率控制器
    
    此類別提供安全的功率控制介面，確保：
    1. 預設為模擬模式
    2. 所有請求都經過驗證
    3. 所有操作都記錄到審計日誌
    4. 生產模式需要特殊授權
    
    使用範例:
        config = PowerControlConfig(simulation_mode=True)
        controller = SafePowerController(config)
        
        # 設定功率（模擬模式下只會記錄）
        result = await controller.set_power_setpoint(50000)
        
        if result.simulated:
            print("Power setpoint was simulated, not actually sent to PCS")
    """
    
    def __init__(
        self,
        config: Optional[PowerControlConfig] = None,
        pcs_writer=None,
    ):
        """
        初始化安全功率控制器
        
        Args:
            config: 功率控制配置
            pcs_writer: ModbusPowerWriter 實例（生產/DRY_RUN 模式使用）
        """
        self.config = config or PowerControlConfig()
        self.validator = PowerValidator(self.config.limits)
        self._current_power_w: int = 0
        self._current_soc: Optional[float] = None
        self._pcs_writer = pcs_writer  # ModbusPowerWriter (可選)
        self._control_mode = self._resolve_control_mode()
        
        # 安全檢查：生產模式需要額外驗證
        if self._control_mode == ControlMode.PRODUCTION:
            self._verify_production_authorization()
        elif self._control_mode == ControlMode.DRY_RUN:
            logger.warning("SafePowerController initialized in DRY_RUN mode")
        else:
            logger.info("SafePowerController initialized in SIMULATION mode")
    
    def _resolve_control_mode(self) -> ControlMode:
        """根據配置解析控制模式"""
        # 支援 runtime_config 的 mode 字串
        mode_str = getattr(self.config, '_runtime_mode', None)
        if mode_str == "dry_run":
            return ControlMode.DRY_RUN
        elif mode_str == "production":
            return ControlMode.PRODUCTION
        elif mode_str == "simulation":
            return ControlMode.SIMULATION
        # 向後相容: 使用舊的 simulation_mode 布林值
        if self.config.simulation_mode:
            return ControlMode.SIMULATION
        return ControlMode.PRODUCTION
    
    def _verify_production_authorization(self) -> None:
        """驗證生產模式授權"""
        safety_token = os.getenv("POWER_CONTROL_SAFETY_TOKEN")
        if not safety_token:
            raise AuthorizationRequired(
                "Production mode requires POWER_CONTROL_SAFETY_TOKEN environment variable"
            )
        
        confirm = os.getenv("POWER_CONTROL_CONFIRM_PRODUCTION")
        if confirm != "I_UNDERSTAND_THE_RISKS":
            raise AuthorizationRequired(
                "Production mode requires POWER_CONTROL_CONFIRM_PRODUCTION="
                "'I_UNDERSTAND_THE_RISKS'"
            )
        
        logger.warning("SafePowerController initialized in PRODUCTION mode")
    
    def set_pcs_writer(self, writer) -> None:
        """注入 PCS writer (延遲注入用)"""
        self._pcs_writer = writer
    
    @property
    def simulation_mode(self) -> bool:
        """是否為模擬模式"""
        return self._control_mode == ControlMode.SIMULATION
    
    @property
    def control_mode(self) -> ControlMode:
        """當前控制模式"""
        return self._control_mode
    
    def update_current_state(
        self,
        current_power_w: int,
        current_soc: Optional[float] = None
    ) -> None:
        """更新當前狀態（用於驗證）"""
        self._current_power_w = current_power_w
        self._current_soc = current_soc
    
    async def set_power_setpoint(
        self,
        power_w: int,
        source: str = "manual"
    ) -> PowerControlResult:
        """
        設定功率設定點
        
        Args:
            power_w: 功率設定點 (W)
                    正值 = 放電, 負值 = 充電
            source: 請求來源 (如 "ieee2030.5", "manual", "scheduler")
        
        Returns:
            PowerControlResult 包含操作結果
        """
        request_id = str(uuid4())[:8]
        timestamp = datetime.now(timezone.utc)
        
        # 1. 檢查緊急停止
        if EmergencyStop.is_stopped():
            return PowerControlResult(
                request_id=request_id,
                mode=self.control_mode,
                requested_power_w=power_w,
                executed=False,
                simulated=False,
                timestamp=timestamp,
                errors=["Emergency stop is active"],
                message="Operation blocked by emergency stop"
            )
        
        # 2. 驗證功率
        errors = self.validator.validate(power_w, self._current_soc)
        
        if errors:
            self._log_request(request_id, power_w, source, "rejected", errors)
            return PowerControlResult(
                request_id=request_id,
                mode=self.control_mode,
                requested_power_w=power_w,
                executed=False,
                simulated=False,
                timestamp=timestamp,
                errors=errors,
                message="Validation failed"
            )
        
        # 3. 模擬模式處理
        if self.config.simulation_mode:
            self._log_request(request_id, power_w, source, "simulated", [])
            logger.info(
                f"[SIMULATION] Power setpoint: {power_w}W "
                f"({'charge' if power_w < 0 else 'discharge'})"
            )
            return PowerControlResult(
                request_id=request_id,
                mode=ControlMode.SIMULATION,
                requested_power_w=power_w,
                executed=False,
                simulated=True,
                timestamp=timestamp,
                message=f"Simulated power setpoint: {power_w}W"
            )
        
        # 4. DRY_RUN 模式：完整驗證 + 計算暫存器值，但不實際寫入
        if self._control_mode == ControlMode.DRY_RUN:
            self._log_request(request_id, power_w, source, "dry_run", [])
            dry_run_msg = f"[DRY_RUN] Would set power to {power_w}W"
            if self._pcs_writer:
                register_value = self._pcs_writer._power_to_register_value(power_w)
                dry_run_msg += (
                    f" (register {self._pcs_writer.config.power_setpoint_address}, "
                    f"raw_value={register_value})"
                )
            logger.info(dry_run_msg)
            return PowerControlResult(
                request_id=request_id,
                mode=ControlMode.DRY_RUN,
                requested_power_w=power_w,
                executed=False,
                simulated=False,
                timestamp=timestamp,
                message=dry_run_msg
            )
        
        # 5. 生產模式：透過 ModbusPowerWriter 實際寫入 PCS
        if self._pcs_writer:
            self._log_request(request_id, power_w, source, "executing", [])
            try:
                write_result = await self._pcs_writer.set_power(
                    power_w=power_w, source=source
                )
                executed = write_result.success
                msg = (
                    f"[PRODUCTION] Power setpoint {power_w}W "
                    f"{'written successfully' if executed else 'WRITE FAILED'}"
                )
                if write_result.error_message:
                    msg += f" - {write_result.error_message}"
                
                self._log_request(
                    request_id, power_w, source,
                    "executed" if executed else "write_failed",
                    [write_result.error_message] if write_result.error_message else []
                )
                
                return PowerControlResult(
                    request_id=request_id,
                    mode=ControlMode.PRODUCTION,
                    requested_power_w=power_w,
                    executed=executed,
                    simulated=False,
                    timestamp=timestamp,
                    errors=[write_result.error_message] if (write_result.error_message and not executed) else [],
                    message=msg
                )
            except Exception as e:
                logger.exception(f"PCS write error: {e}")
                self._log_request(request_id, power_w, source, "error", [str(e)])
                return PowerControlResult(
                    request_id=request_id,
                    mode=ControlMode.PRODUCTION,
                    requested_power_w=power_w,
                    executed=False,
                    simulated=False,
                    timestamp=timestamp,
                    errors=[str(e)],
                    message=f"PCS write error: {e}"
                )
        else:
            # 生產模式但沒有 writer — 記錄警告
            self._log_request(request_id, power_w, source, "no_writer", [])
            logger.warning(
                f"[PRODUCTION] No PCS writer configured, power setpoint {power_w}W not sent"
            )
            return PowerControlResult(
                request_id=request_id,
                mode=ControlMode.PRODUCTION,
                requested_power_w=power_w,
                executed=False,
                simulated=False,
                timestamp=timestamp,
                message="Production mode: No PCS writer configured"
            )
    
    def _log_request(
        self,
        request_id: str,
        power_w: int,
        source: str,
        status: str,
        errors: list[str]
    ) -> None:
        """記錄功率控制請求到審計日誌"""
        if not self.config.log_all_requests:
            return
        
        power_audit_logger.info(
            f"POWER_CONTROL | "
            f"id={request_id} | "
            f"mode={self.control_mode.value} | "
            f"power={power_w}W | "
            f"source={source} | "
            f"status={status} | "
            f"errors={errors if errors else 'none'} | "
            f"timestamp={datetime.now(timezone.utc).isoformat()}"
        )


def check_safety_environment() -> bool:
    """
    檢查安全環境變數
    
    在應用程式啟動時調用此函數以確保安全配置正確
    
    Returns:
        True 如果是模擬模式, False 如果是生產模式
    """
    simulation_mode = os.getenv("POWER_CONTROL_SIMULATION", "true").lower()
    
    if simulation_mode != "true":
        # 非模擬模式需要額外的安全確認
        safety_token = os.getenv("POWER_CONTROL_SAFETY_TOKEN")
        if not safety_token:
            logger.error(
                "Production mode requires POWER_CONTROL_SAFETY_TOKEN"
            )
            sys.exit(1)
        
        confirm = os.getenv("POWER_CONTROL_CONFIRM_PRODUCTION")
        if confirm != "I_UNDERSTAND_THE_RISKS":
            logger.error(
                "Production mode requires explicit confirmation. "
                "Set POWER_CONTROL_CONFIRM_PRODUCTION='I_UNDERSTAND_THE_RISKS'"
            )
            sys.exit(1)
        
        logger.warning("Running in PRODUCTION mode - PCS control is ENABLED")
        return False
    
    logger.info("Running in SIMULATION mode - PCS control is DISABLED")
    return True


def create_power_controller_from_runtime(runtime_power_config) -> SafePowerController:
    """
    從 RuntimeConfig.power_control 創建 SafePowerController
    
    Args:
        runtime_power_config: PowerControlConfig from runtime_config module
        
    Returns:
        SafePowerController instance
    """
    from bms_2030_5_client.runtime_config import PowerControlMode as RTPowerControlMode
    
    mode = runtime_power_config.mode
    limits = runtime_power_config.limits
    
    # 構建 PowerLimits
    power_limits = PowerLimits(
        max_charge_w=limits.max_charge_w,
        max_discharge_w=limits.max_discharge_w,
        max_ramp_rate_w_per_s=limits.ramp_rate_w_per_s,
        min_soc_percent=limits.min_soc_percent,
        max_soc_percent=limits.max_soc_percent,
    )
    
    # 決定 simulation_mode (向後相容)
    is_simulation = (mode == RTPowerControlMode.SIMULATION.value)
    
    # 如果是 production 模式，設定環境變數以通過授權檢查
    if mode == RTPowerControlMode.PRODUCTION.value:
        auth = runtime_power_config.production_auth
        if auth.safety_token:
            os.environ.setdefault("POWER_CONTROL_SAFETY_TOKEN", auth.safety_token)
        if auth.confirm_production:
            os.environ.setdefault("POWER_CONTROL_CONFIRM_PRODUCTION", "I_UNDERSTAND_THE_RISKS")
    
    # 構建 PowerControlConfig
    config = PowerControlConfig(
        simulation_mode=is_simulation,
        limits=power_limits,
    )
    # 附加 runtime mode 字串供 _resolve_control_mode 使用
    config._runtime_mode = mode
    
    controller = SafePowerController(config=config)
    
    logger.info(
        f"Power controller created from runtime config: mode={mode}, "
        f"limits=[charge={limits.max_charge_w}W, discharge={limits.max_discharge_w}W]"
    )
    
    return controller


# 導出的公開介面
__all__ = [
    "ControlMode",
    "PowerControlError",
    "SafetyError",
    "PowerLimitExceeded",
    "SimulationModeRequired",
    "AuthorizationRequired",
    "PowerLimits",
    "PowerControlConfig",
    "PowerControlResult",
    "PowerValidator",
    "EmergencyStop",
    "SafePowerController",
    "check_safety_environment",
    "create_power_controller_from_runtime",
]
