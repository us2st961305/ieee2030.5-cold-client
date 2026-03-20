"""
Modbus Power Writer - PCS 功率設定點寫入介面

此模組負責：
1. 透過 Modbus 將功率設定點寫入 PCS
2. 支援重試機制和寫入後驗證
3. 安全檢查由 SafePowerController 負責

⚗️ 安全注意：
- 功率驗證和模式控制由 SafePowerController 執行
- 此模組僅負責 Modbus I/O
- 所有寫入操作都會記錄到審計日誌
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional, Awaitable

from bms_2030_5_client.power_control import (
    EmergencyStop,
)

logger = logging.getLogger(__name__)
power_audit_logger = logging.getLogger("power_control.audit")


# =============================================================================
# PCS Register Addresses (PCS 暫存器位址)
# =============================================================================

class PCSRegisterAddress:
    """
    PCS Modbus 暫存器位址定義 — CUBE 電池組暫存器通訊表 V1.0.3

    Reference: CUBE V1.0.3 §7848–7865 (Sys Power LW)
    Addresses are actual Modbus addresses (document addresses, already offset).
    """
    # --- PCS 控制暫存器 (R/W) ---
    PCS_ON = 7850                   # Pulse write 1 = 開機
    PCS_OFF = 7851                  # Pulse write 1 = 關機
    POWER_SETPOINT = 7852           # P_SET, S16, 0.1 kW
    Q_SETPOINT = 7853               # Q_SET, S16, 0.1 kVAR

    # --- PCS 狀態暫存器 (RO) ---
    PCS_STATE = 7848                # PCS_state, U16 (see PCSState enum)
    PCS_ALARM = 7854                # PCS_alarm, U16, bitfield
    ACTUAL_POWER = 7855             # PCS_P_read, S16, 0.1 kW
    ACTUAL_Q = 7856                 # PCS_Q_read, S16, 0.1 kVAR
    FREQ = 7857                     # FREQ, U16, 0.1 Hz

    # Legacy aliases (kept for backward compatibility with audit logs)
    OPERATION_STATUS = PCS_STATE
    ERROR_CODE = PCS_ALARM


class PCSState(Enum):
    """PCS 狀態 (register 7848, read-only). Ref: CUBE V1.0.3"""
    INITIALIZE = 0
    FAULT = 1
    CALIBRATE = 2
    DISABLED = 3
    CHARGE_WAIT = 4
    CHARGING = 5
    STANDBY = 6
    TURN_ON_DELAY = 7
    ONLINE_GRID_TIE = 8
    OFFLINE = 9
    ACTIVE_RIDE_THRU = 10
    PASSIVE_RIDE_THRU = 11
    ONLINE_GRID_FORM = 12
    POWER_DOWN = 13
    TURN_OFF = 16


# Backward-compatible alias
PCSOperationMode = PCSState


@dataclass
class PowerWriteResult:
    """功率寫入結果"""
    success: bool
    simulated: bool
    requested_power_w: int
    actual_power_w: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None
    register_address: Optional[int] = None
    raw_value: Optional[int] = None


@dataclass
class ModbusPowerWriterConfig:
    """Modbus 功率寫入器配置"""
    # PCS 暫存器位址配置
    power_setpoint_address: int = PCSRegisterAddress.POWER_SETPOINT
    
    # Power scale: W (input) → 0.1 kW (register)
    # 50000 W × 0.01 = 500 → register value 500 = 50.0 kW
    power_scale_factor: float = 0.01
    
    # 寫入確認
    verify_after_write: bool = True  # 寫入後讀回確認
    verify_delay_s: float = 0.5      # 確認延遲
    
    # 重試配置
    max_retries: int = 3
    retry_delay_s: float = 1.0


class ModbusPowerWriter:
    """
    Modbus 功率寫入器 — 純 I/O 層
    
    僅負責 Modbus 暫存器讀寫，安全檢查由 SafePowerController 執行。
    
    使用方式:
        writer = ModbusPowerWriter(modbus_client=modbus_client)
        
        # 直接寫入（應由 SafePowerController 調用）
        result = await writer.write_power_to_modbus(50000)
    """
    
    def __init__(
        self,
        modbus_client,  # ModbusBMSClient
        config: Optional[ModbusPowerWriterConfig] = None,
    ):
        """
        Initialize Modbus power writer.
        
        Args:
            modbus_client: Modbus client for register I/O.
            config: Writer configuration.
        """
        self.modbus_client = modbus_client
        self.config = config or ModbusPowerWriterConfig()
        
        # 當前狀態
        self._current_power_w: int = 0
        self._last_write_time: Optional[float] = None
        
        logger.info("ModbusPowerWriter initialized")
    
    @property
    def current_power_w(self) -> int:
        """當前功率設定點（瓦）"""
        return self._current_power_w
    
    async def set_power(
        self,
        power_w: int,
        source: str = "manual"
    ) -> PowerWriteResult:
        """
        設定功率設定點（直接寫入 Modbus）
        
        ⚗️ 外部調用者應透過 SafePowerController.set_power_setpoint() 以確保安全檢查。
        此方法僅供內部和特殊場景（stop/de_energize）使用。
        
        Args:
            power_w: 功率設定點（W）
            source: 請求來源
        
        Returns:
            PowerWriteResult
        """
        return await self.write_power_to_modbus(power_w)
    
    async def write_power_to_modbus(self, power_w: int) -> PowerWriteResult:
        """
        寫入功率到 Modbus
        
        由 SafePowerController 在 PRODUCTION 模式下調用。
        """
        timestamp = datetime.now(timezone.utc)
        
        # 計算暫存器值
        register_value = self._power_to_register_value(power_w)
        
        # 記錄到審計日誌
        power_audit_logger.warning(
            f"MODBUS_WRITE | "
            f"power={power_w}W | "
            f"address={self.config.power_setpoint_address} | "
            f"value={register_value} | "
            f"timestamp={timestamp.isoformat()}"
        )
        
        # 重試機制
        for attempt in range(self.config.max_retries):
            # Emergency stop guard: 每次重試前檢查
            if EmergencyStop.is_stopped():
                power_audit_logger.warning(
                    f"MODBUS_WRITE_ABORTED | power={power_w}W | "
                    f"reason=emergency_stop | attempt={attempt + 1}"
                )
                return PowerWriteResult(
                    success=False,
                    simulated=False,
                    requested_power_w=power_w,
                    timestamp=timestamp,
                    error_message="Aborted: emergency stop active",
                )
            try:
                # P_SET is S16 (0.1 kW) — 16-bit signed write
                success = await self.modbus_client.write_register(
                    self.config.power_setpoint_address,
                    register_value & 0xFFFF
                )
                
                if not success:
                    raise Exception("Modbus write failed")
                
                # 寫入後驗證
                if self.config.verify_after_write:
                    await asyncio.sleep(self.config.verify_delay_s)
                    actual_value = await self._read_actual_power()
                else:
                    actual_value = None
                
                power_audit_logger.info(
                    f"MODBUS_WRITE_SUCCESS | "
                    f"power={power_w}W | "
                    f"actual={actual_value}W"
                )
                
                self._current_power_w = power_w
                self._last_write_time = time.monotonic()
                
                return PowerWriteResult(
                    success=True,
                    simulated=False,
                    requested_power_w=power_w,
                    actual_power_w=actual_value,
                    timestamp=timestamp,
                    register_address=self.config.power_setpoint_address,
                    raw_value=register_value,
                )
            
            except Exception as e:
                logger.error(
                    f"Modbus write failed (attempt {attempt + 1}): {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay_s)
                else:
                    power_audit_logger.error(
                        f"MODBUS_WRITE_FAILED | "
                        f"power={power_w}W | "
                        f"error={e}"
                    )
                    return PowerWriteResult(
                        success=False,
                        simulated=False,
                        requested_power_w=power_w,
                        timestamp=timestamp,
                        error_message=str(e),
                    )
        
        return PowerWriteResult(
            success=False,
            simulated=False,
            requested_power_w=power_w,
            timestamp=timestamp,
            error_message="Max retries exceeded",
        )
    
    def _power_to_register_value(self, power_w: int) -> int:
        """
        將功率（W）轉換為暫存器值
        
        根據 power_scale_factor 進行縮放
        """
        return int(power_w * self.config.power_scale_factor)
    
    def _register_value_to_power(self, value: int) -> int:
        """
        將暫存器值轉換為功率（W）
        """
        return int(value / self.config.power_scale_factor)
    
    async def _read_actual_power(self) -> Optional[int]:
        """
        讀取實際功率
        """
        try:
            registers = await self.modbus_client.read_registers(
                PCSRegisterAddress.ACTUAL_POWER,
                1
            )
            if registers:
                return self._register_value_to_power(registers[0])
        except Exception as e:
            logger.debug(f"Failed to read actual power: {e}")
        return None
    
    async def stop(self) -> PowerWriteResult:
        """
        停止功率輸出（設定為 0）
        """
        return await self.set_power(0, source="stop")
    
    async def de_energize(self, reason: str = "opModEnergize=false") -> PowerWriteResult:
        """
        去能控制：將 PCS 輸出功率設為 0
        
        對應 IEEE 2030.5 DERControlBase.opModEnergize=false
        
        執行動作：
        1. 功率設定點歸零
        2. 記錄去能事件到審計日誌
        
        注意：此方法不切換 PCS 運行模式。
        opModConnect=false 有額外的 STANDBY 模式切換，請使用 disconnect()。
        
        Args:
            reason: 去能原因描述
        
        Returns:
            PowerWriteResult
        """
        power_audit_logger.warning(
            f"DE_ENERGIZE | reason={reason} | "
            f"timestamp={datetime.now(timezone.utc).isoformat()}"
        )
        
        return await self.set_power(0, source=f"de-energize:{reason}")
    
    async def disconnect(self, reason: str = "opModConnect=false") -> PowerWriteResult:
        """
        Disconnect PCS: zero power then pulse PCS_OFF.

        Corresponds to IEEE 2030.5 DERControlBase.opModConnect=false.

        Steps:
        1. P_SET (7852) = 0  — zero power setpoint
        2. PCS_OFF (7851) = 1  — pulse to shut down PCS

        Args:
            reason: Disconnect reason description.

        Returns:
            PowerWriteResult
        """
        power_audit_logger.warning(
            f"DISCONNECT | reason={reason} | "
            f"timestamp={datetime.now(timezone.utc).isoformat()}"
        )

        # Step 1: 功率歸零
        power_result = await self.set_power(0, source=f"disconnect:{reason}")
        if not power_result.success:
            return power_result

        # Step 2: Pulse PCS_OFF to shut down
        try:
            off_success = await self.modbus_client.write_register(
                PCSRegisterAddress.PCS_OFF,
                1,  # pulse
            )
            if off_success:
                power_audit_logger.info(
                    f"DISCONNECT_PCS_OFF | "
                    f"register={PCSRegisterAddress.PCS_OFF} | value=1 (pulse)"
                )
            else:
                power_audit_logger.error(
                    f"DISCONNECT_PCS_OFF_FAILED | "
                    f"register={PCSRegisterAddress.PCS_OFF}"
                )
                return PowerWriteResult(
                    success=False,
                    simulated=False,
                    requested_power_w=0,
                    timestamp=datetime.now(timezone.utc),
                    error_message="Failed to pulse PCS_OFF",
                )
        except Exception as e:
            power_audit_logger.error(
                f"DISCONNECT_PCS_OFF_ERROR | error={e}"
            )
            return PowerWriteResult(
                success=False,
                simulated=False,
                requested_power_w=0,
                timestamp=datetime.now(timezone.utc),
                error_message=f"PCS_OFF write error: {e}",
            )

        return power_result
    
    async def reconnect(self, reason: str = "opModConnect=true") -> PowerWriteResult:
        """
        Reconnect PCS: pulse PCS_ON to start up.

        Inverse of disconnect(). Does NOT write a power setpoint — only
        pulses PCS_ON so subsequent power commands can be accepted.
        Corresponds to IEEE 2030.5 DERControlBase.opModConnect=true.

        Steps:
        1. PCS_ON (7850) = 1  — pulse to start PCS

        Args:
            reason: Reconnect reason description.

        Returns:
            PowerWriteResult
        """
        power_audit_logger.warning(
            f"RECONNECT | reason={reason} | "
            f"timestamp={datetime.now(timezone.utc).isoformat()}"
        )

        try:
            on_success = await self.modbus_client.write_register(
                PCSRegisterAddress.PCS_ON,
                1,  # pulse
            )
            if on_success:
                power_audit_logger.info(
                    f"RECONNECT_PCS_ON | "
                    f"register={PCSRegisterAddress.PCS_ON} | value=1 (pulse)"
                )
                return PowerWriteResult(
                    success=True,
                    simulated=False,
                    requested_power_w=0,
                    timestamp=datetime.now(timezone.utc),
                )
            else:
                power_audit_logger.error(
                    f"RECONNECT_PCS_ON_FAILED | "
                    f"register={PCSRegisterAddress.PCS_ON}"
                )
                return PowerWriteResult(
                    success=False,
                    simulated=False,
                    requested_power_w=0,
                    timestamp=datetime.now(timezone.utc),
                    error_message="Failed to pulse PCS_ON",
                )
        except Exception as e:
            power_audit_logger.error(f"RECONNECT_PCS_ON_ERROR | error={e}")
            return PowerWriteResult(
                success=False,
                simulated=False,
                requested_power_w=0,
                timestamp=datetime.now(timezone.utc),
                error_message=f"PCS_ON write error: {e}",
            )
    
    async def emergency_stop(self, reason: str) -> PowerWriteResult:
        """
        緊急停止
        
        觸發 EmergencyStop 並設定功率為 0
        """
        EmergencyStop.trigger(reason)
        
        # 立即重置 current_power_w
        self._current_power_w = 0
        
        logger.critical(f"Emergency stop triggered: {reason}")
        
        return PowerWriteResult(
            success=True,
            simulated=False,
            requested_power_w=0,
            timestamp=datetime.now(timezone.utc),
            error_message=f"Emergency stop: {reason}"
        )


class PCSPowerAdapter:
    """
    PCS 功率適配器
    
    將 IEEE 2030.5 DERControl 轉換為 Modbus 功率寫入
    
    使用方式:
        adapter = PCSPowerAdapter(power_writer)
        
        # 處理 DER Control
        result = await adapter.apply_der_control(der_control)
    """
    
    def __init__(self, power_writer: ModbusPowerWriter):
        """
        初始化 PCS 功率適配器
        
        Args:
            power_writer: Modbus 功率寫入器
        """
        self.power_writer = power_writer
    
    async def apply_der_control(
        self,
        der_control,  # DERControl
    ) -> PowerWriteResult:
        """
        應用 DERControl 指令
        
        Args:
            der_control: IEEE 2030.5 DERControl
        
        Returns:
            PowerWriteResult
        """
        power_w = der_control.get_power_setpoint_w()
        
        if power_w is None:
            return PowerWriteResult(
                success=False,
                simulated=False,
                requested_power_w=0,
                error_message="No power setpoint in DERControl"
            )
        
        return await self.power_writer.set_power(
            power_w=power_w,
            source="ieee2030.5_der_control"
        )
    
    async def apply_power_percent(
        self,
        percent: float,
        max_power_w: int,
    ) -> PowerWriteResult:
        """
        按百分比設定功率
        
        Args:
            percent: 功率百分比 (-100 to 100)
                    正值 = 放電, 負值 = 充電
            max_power_w: 最大功率（W）
        
        Returns:
            PowerWriteResult
        """
        power_w = int(max_power_w * percent / 100)
        
        return await self.power_writer.set_power(
            power_w=power_w,
            source="percent_control"
        )
