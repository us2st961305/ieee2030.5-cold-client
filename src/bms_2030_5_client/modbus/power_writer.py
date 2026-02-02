"""
Modbus Power Writer - 安全的功率設定點寫入介面

此模組負責：
1. 透過 Modbus 將功率設定點寫入 PCS
2. 整合 SafePowerController 確保安全
3. 支援模擬模式（不實際寫入）

⚠️ 安全注意：
- 此模組預設為模擬模式
- 生產模式需要特殊授權
- 所有寫入操作都會記錄到審計日誌
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Awaitable

from bms_2030_5_client.power_control import (
    SafePowerController,
    PowerControlConfig,
    PowerControlResult,
    PowerLimits,
    ControlMode,
    EmergencyStop,
    check_safety_environment,
)

logger = logging.getLogger(__name__)
power_audit_logger = logging.getLogger("power_control.audit")


# =============================================================================
# PCS Register Addresses (PCS 暫存器位址)
# =============================================================================

class PCSRegisterAddress:
    """
    PCS Modbus 暫存器位址定義
    
    ⚠️ 注意：這些位址需要根據實際 PCS 設備進行調整
    """
    # 功率控制暫存器（示例位址，需根據實際 PCS 調整）
    POWER_SETPOINT = 40001          # 功率設定點 (W or 0.1kW)
    POWER_SETPOINT_HIGH = 40002     # 功率設定點高位元（32-bit）
    
    # 模式控制
    OPERATION_MODE = 40010          # 運行模式
    ENABLE_CONTROL = 40011          # 啟用控制
    
    # 狀態暫存器
    ACTUAL_POWER = 40100            # 實際功率
    OPERATION_STATUS = 40101        # 運行狀態
    ERROR_CODE = 40102              # 錯誤碼


class PCSOperationMode(Enum):
    """PCS 運行模式"""
    STANDBY = 0         # 待機
    CHARGING = 1        # 充電
    DISCHARGING = 2     # 放電
    AUTO = 3            # 自動
    REMOTE = 4          # 遠程控制


@dataclass
class PowerWriteResult:
    """功率寫入結果"""
    success: bool
    simulated: bool
    requested_power_w: int
    actual_power_w: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    register_address: Optional[int] = None
    raw_value: Optional[int] = None


@dataclass
class ModbusPowerWriterConfig:
    """Modbus 功率寫入器配置"""
    # PCS 暫存器位址配置
    power_setpoint_address: int = PCSRegisterAddress.POWER_SETPOINT
    use_32bit_power: bool = False   # 是否使用 32-bit 功率值
    
    # 功率縮放
    power_scale_factor: float = 1.0  # 1.0 = W, 0.1 = 0.1kW, 0.001 = kW
    
    # 寫入確認
    verify_after_write: bool = True  # 寫入後讀回確認
    verify_delay_s: float = 0.5      # 確認延遲
    
    # 重試配置
    max_retries: int = 3
    retry_delay_s: float = 1.0


class ModbusPowerWriter:
    """
    Modbus 功率寫入器
    
    整合 SafePowerController 實現安全的功率寫入
    
    使用方式:
        writer = ModbusPowerWriter(
            modbus_client=modbus_client,
            power_controller=safe_controller,
        )
        
        # 設定功率（模擬模式下只會記錄）
        result = await writer.set_power(50000)  # 50kW
    
    ⚠️ 安全注意：
    - 預設為模擬模式
    - 生產模式需要配置 SafePowerController
    """
    
    def __init__(
        self,
        modbus_client,  # ModbusBMSClient
        power_controller: Optional[SafePowerController] = None,
        config: Optional[ModbusPowerWriterConfig] = None,
    ):
        """
        初始化 Modbus 功率寫入器
        
        Args:
            modbus_client: Modbus 客戶端
            power_controller: 安全功率控制器（如果為 None，將創建預設的模擬模式控制器）
            config: 寫入器配置
        """
        self.modbus_client = modbus_client
        self.power_controller = power_controller or SafePowerController(
            PowerControlConfig(simulation_mode=True)
        )
        self.config = config or ModbusPowerWriterConfig()
        
        # 當前狀態
        self._current_power_w: int = 0
        self._last_write_time: Optional[float] = None
        
        logger.info(
            f"ModbusPowerWriter initialized "
            f"(simulation_mode={self.power_controller.simulation_mode})"
        )
    
    @property
    def simulation_mode(self) -> bool:
        """是否為模擬模式"""
        return self.power_controller.simulation_mode
    
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
        設定功率設定點
        
        Args:
            power_w: 功率設定點（W）
                    正值 = 放電, 負值 = 充電
            source: 請求來源
        
        Returns:
            PowerWriteResult 包含寫入結果
        """
        timestamp = datetime.utcnow()
        
        # 1. 透過安全控制器驗證和執行
        control_result = await self.power_controller.set_power_setpoint(
            power_w=power_w,
            source=source
        )
        
        # 2. 如果驗證失敗，返回錯誤
        if not control_result.success:
            return PowerWriteResult(
                success=False,
                simulated=control_result.simulated,
                requested_power_w=power_w,
                timestamp=timestamp,
                error_message="; ".join(control_result.errors)
            )
        
        # 3. 模擬模式：只記錄不實際寫入
        if control_result.simulated:
            self._current_power_w = power_w
            self._last_write_time = time.time()
            
            logger.info(
                f"[SIMULATION] Power setpoint: {power_w}W "
                f"(would write to register {self.config.power_setpoint_address})"
            )
            
            return PowerWriteResult(
                success=True,
                simulated=True,
                requested_power_w=power_w,
                timestamp=timestamp,
                register_address=self.config.power_setpoint_address,
            )
        
        # 4. 生產模式：實際寫入 Modbus
        write_result = await self._write_power_to_modbus(power_w)
        
        if write_result.success:
            self._current_power_w = power_w
            self._last_write_time = time.time()
        
        return write_result
    
    async def _write_power_to_modbus(self, power_w: int) -> PowerWriteResult:
        """
        實際寫入功率到 Modbus
        
        ⚠️ 此方法只在生產模式下被調用
        """
        timestamp = datetime.utcnow()
        
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
            try:
                if self.config.use_32bit_power:
                    # 32-bit 寫入（高位元 + 低位元）
                    high_word = (register_value >> 16) & 0xFFFF
                    low_word = register_value & 0xFFFF
                    
                    await self.modbus_client.write_register(
                        self.config.power_setpoint_address,
                        low_word
                    )
                    await self.modbus_client.write_register(
                        self.config.power_setpoint_address + 1,
                        high_word
                    )
                else:
                    # 16-bit 寫入
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
    
    async def emergency_stop(self, reason: str) -> PowerWriteResult:
        """
        緊急停止
        
        觸發 EmergencyStop 並設定功率為 0
        """
        EmergencyStop.trigger(reason)
        
        # 立即重置 current_power_w（不需要等待 set_power）
        self._current_power_w = 0
        
        logger.critical(f"Emergency stop triggered: {reason}")
        
        return PowerWriteResult(
            success=True,
            simulated=self.power_controller.simulation_mode,
            requested_power_w=0,
            timestamp=datetime.utcnow(),
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
                simulated=True,
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
