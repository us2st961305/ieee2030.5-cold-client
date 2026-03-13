"""
Power Control Safety Tests (功率控制安全測試)

測試確保安全機制正確運作，防止意外向 PCS 發送指令
"""

import os
from unittest.mock import patch

import pytest

from bms_2030_5_client.power_control import (
    AuthorizationRequired,
    ControlMode,
    EmergencyStop,
    PowerControlConfig,
    PowerLimitExceeded,
    PowerLimits,
    PowerValidator,
    SafePowerController,
    check_safety_environment,
)


@pytest.fixture(autouse=True)
def reset_emergency_stop():
    """每個測試後重置緊急停止狀態"""
    with EmergencyStop._lock:
        EmergencyStop._stopped = False
        EmergencyStop._reason = None
        EmergencyStop._timestamp = None
    yield
    with EmergencyStop._lock:
        EmergencyStop._stopped = False
        EmergencyStop._reason = None
        EmergencyStop._timestamp = None


@pytest.fixture(autouse=True)
def enforce_simulation_mode(monkeypatch):
    """強制所有測試使用模擬模式"""
    monkeypatch.setenv("POWER_CONTROL_SIMULATION", "true")
    monkeypatch.delenv("POWER_CONTROL_SAFETY_TOKEN", raising=False)
    monkeypatch.delenv("POWER_CONTROL_CONFIRM_PRODUCTION", raising=False)


class TestPowerLimits:
    """測試功率限制配置"""
    
    def test_default_limits(self):
        """測試預設限制值"""
        limits = PowerLimits()
        assert limits.max_charge_w == 100_000
        assert limits.max_discharge_w == 100_000
        assert limits.min_soc_percent == 10.0
        assert limits.max_soc_percent == 90.0
    
    def test_custom_limits(self):
        """測試自訂限制值"""
        limits = PowerLimits(
            max_charge_w=50_000,
            max_discharge_w=75_000,
            min_soc_percent=20.0,
            max_soc_percent=80.0
        )
        assert limits.max_charge_w == 50_000
        assert limits.max_discharge_w == 75_000
    
    def test_invalid_negative_power(self):
        """測試無效的負功率限制"""
        with pytest.raises(ValueError, match="must be positive"):
            PowerLimits(max_charge_w=-1000)
    
    def test_invalid_soc_range(self):
        """測試無效的 SOC 範圍"""
        with pytest.raises(ValueError, match="Invalid SOC limits"):
            PowerLimits(min_soc_percent=90, max_soc_percent=10)


class TestPowerValidator:
    """測試功率驗證器"""
    
    @pytest.fixture
    def validator(self):
        return PowerValidator(PowerLimits())
    
    def test_valid_discharge_power(self, validator):
        """測試有效的放電功率"""
        errors = validator.validate(50_000)  # 50kW discharge
        assert len(errors) == 0
    
    def test_valid_charge_power(self, validator):
        """測試有效的充電功率"""
        errors = validator.validate(-50_000)  # 50kW charge
        assert len(errors) == 0
    
    def test_zero_power(self, validator):
        """測試零功率"""
        errors = validator.validate(0)
        assert len(errors) == 0
    
    def test_exceed_discharge_limit(self, validator):
        """測試超出放電限制"""
        errors = validator.validate(150_000)  # 150kW > 100kW limit
        assert len(errors) == 1
        assert "Discharge power" in errors[0]
        assert "exceeds limit" in errors[0]
    
    def test_exceed_charge_limit(self, validator):
        """測試超出充電限制"""
        errors = validator.validate(-150_000)  # 150kW > 100kW limit
        assert len(errors) == 1
        assert "Charge power" in errors[0]
        assert "exceeds limit" in errors[0]
    
    def test_discharge_with_low_soc(self, validator):
        """測試低 SOC 時放電"""
        errors = validator.validate(50_000, current_soc=5.0)  # SOC < 10%
        assert len(errors) == 1
        assert "Cannot discharge" in errors[0]
    
    def test_charge_with_high_soc(self, validator):
        """測試高 SOC 時充電"""
        errors = validator.validate(-50_000, current_soc=95.0)  # SOC > 90%
        assert len(errors) == 1
        assert "Cannot charge" in errors[0]
    
    def test_ramp_rate_within_limit(self, validator):
        """測試變化速率在限制內"""
        errors = validator.validate_ramp_rate(
            current_power_w=0,
            target_power_w=5_000,
            time_interval_s=1.0
        )
        assert len(errors) == 0
    
    def test_ramp_rate_exceeds_limit(self, validator):
        """測試變化速率超出限制"""
        errors = validator.validate_ramp_rate(
            current_power_w=0,
            target_power_w=50_000,  # 50kW in 1 second
            time_interval_s=1.0
        )
        assert len(errors) == 1
        assert "Ramp rate" in errors[0]


class TestPowerControlConfig:
    """測試功率控制配置"""
    
    def test_default_simulation_mode(self):
        """測試預設為模擬模式"""
        config = PowerControlConfig()
        assert config.simulation_mode is True
    
    def test_from_env_default(self, monkeypatch):
        """測試從環境變數創建配置（預設）"""
        monkeypatch.setenv("POWER_CONTROL_SIMULATION", "true")
        config = PowerControlConfig.from_env()
        assert config.simulation_mode is True
    
    def test_from_env_with_limits(self, monkeypatch):
        """測試從環境變數創建配置（自訂限制）"""
        monkeypatch.setenv("POWER_CONTROL_SIMULATION", "true")
        monkeypatch.setenv("MAX_CHARGE_POWER_W", "50000")
        monkeypatch.setenv("MAX_DISCHARGE_POWER_W", "75000")
        config = PowerControlConfig.from_env()
        assert config.limits.max_charge_w == 50_000
        assert config.limits.max_discharge_w == 75_000


class TestSafePowerController:
    """測試安全功率控制器"""
    
    @pytest.fixture
    def controller(self):
        return SafePowerController(PowerControlConfig(simulation_mode=True))
    
    def test_default_is_simulation_mode(self, controller):
        """測試預設為模擬模式"""
        assert controller.simulation_mode is True
        assert controller.control_mode == ControlMode.SIMULATION
    
    @pytest.mark.asyncio
    async def test_simulation_mode_does_not_execute(self, controller):
        """測試模擬模式不會實際執行"""
        result = await controller.set_power_setpoint(50_000)
        
        assert result.simulated is True
        assert result.executed is False
        assert result.success is True
        assert result.mode == ControlMode.SIMULATION
    
    @pytest.mark.asyncio
    async def test_simulation_mode_logs_correctly(self, controller, caplog):
        """測試模擬模式正確記錄"""
        await controller.set_power_setpoint(50_000, source="test")
        
        assert "SIMULATION" in caplog.text or "simulated" in caplog.text.lower()
    
    @pytest.mark.asyncio
    async def test_validation_errors_block_operation(self, controller):
        """測試驗證錯誤阻止操作"""
        # 嘗試設定超出限制的功率
        result = await controller.set_power_setpoint(200_000)  # 200kW > limit
        
        assert result.success is False
        assert result.executed is False
        assert result.simulated is False
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_emergency_stop_blocks_operation(self, controller):
        """測試緊急停止阻止操作"""
        EmergencyStop.trigger("test emergency")
        
        result = await controller.set_power_setpoint(50_000)
        
        assert result.success is False
        assert result.executed is False
        assert "Emergency stop" in result.errors[0]
    
    @pytest.mark.asyncio
    async def test_charge_power_negative_value(self, controller):
        """測試充電功率使用負值"""
        result = await controller.set_power_setpoint(-30_000)  # 30kW charge
        
        assert result.success is True
        assert result.requested_power_w == -30_000
    
    def test_production_mode_requires_authorization(self, monkeypatch):
        """測試生產模式需要授權"""
        monkeypatch.delenv("POWER_CONTROL_SAFETY_TOKEN", raising=False)
        
        with pytest.raises(AuthorizationRequired):
            SafePowerController(PowerControlConfig(simulation_mode=False))
    
    def test_production_mode_requires_confirmation(self, monkeypatch):
        """測試生產模式需要確認"""
        monkeypatch.setenv("POWER_CONTROL_SAFETY_TOKEN", "test_token")
        monkeypatch.delenv("POWER_CONTROL_CONFIRM_PRODUCTION", raising=False)
        
        with pytest.raises(AuthorizationRequired):
            SafePowerController(PowerControlConfig(simulation_mode=False))
    
    def test_production_mode_with_full_authorization(self, monkeypatch):
        """測試生產模式完整授權"""
        monkeypatch.setenv("POWER_CONTROL_SAFETY_TOKEN", "test_token")
        monkeypatch.setenv("POWER_CONTROL_CONFIRM_PRODUCTION", "I_UNDERSTAND_THE_RISKS")
        
        # 應該能成功創建（不拋出異常）
        controller = SafePowerController(PowerControlConfig(simulation_mode=False))
        assert controller.control_mode == ControlMode.PRODUCTION


class TestEmergencyStop:
    """測試緊急停止功能"""
    
    def test_initial_state_not_stopped(self):
        """測試初始狀態未停止"""
        assert EmergencyStop.is_stopped() is False
    
    def test_trigger_emergency_stop(self):
        """測試觸發緊急停止"""
        EmergencyStop.trigger("test reason")
        
        assert EmergencyStop.is_stopped() is True
        status = EmergencyStop.get_status()
        assert status["stopped"] is True
        assert status["reason"] == "test reason"
    
    def test_reset_without_token_fails(self):
        """測試無 token 重置失敗"""
        EmergencyStop.trigger("test")
        
        result = EmergencyStop.reset("invalid_token")
        
        assert result is False
        assert EmergencyStop.is_stopped() is True
    
    def test_reset_with_valid_token(self, monkeypatch):
        """測試有效 token 重置成功"""
        monkeypatch.setenv("POWER_CONTROL_SAFETY_TOKEN", "valid_token")
        EmergencyStop.trigger("test")
        
        result = EmergencyStop.reset("valid_token")
        
        assert result is True
        assert EmergencyStop.is_stopped() is False

    def test_concurrent_trigger_and_get_status(self):
        """測試並發 trigger + get_status 狀態一致性"""
        import threading

        errors: list[str] = []

        def trigger_loop():
            for i in range(200):
                EmergencyStop.trigger(f"reason-{i}")

        def read_loop():
            for _ in range(200):
                status = EmergencyStop.get_status()
                if status["stopped"] and status["reason"] is None:
                    errors.append("stopped=True but reason=None")
                if status["stopped"] and status["timestamp"] is None:
                    errors.append("stopped=True but timestamp=None")

        t1 = threading.Thread(target=trigger_loop)
        t2 = threading.Thread(target=read_loop)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == [], f"Race condition detected: {errors[:5]}"

    def test_concurrent_trigger_and_reset(self, monkeypatch):
        """測試並發 trigger + reset 不會丟失觸發原因"""
        import threading

        monkeypatch.setenv("POWER_CONTROL_SAFETY_TOKEN", "tok")
        errors: list[str] = []

        def trigger_and_check():
            for i in range(200):
                EmergencyStop.trigger(f"fault-{i}")
                status = EmergencyStop.get_status()
                if status["stopped"] and status["reason"] is None:
                    errors.append(f"iter {i}: stopped but reason lost")

        def reset_loop():
            for _ in range(200):
                EmergencyStop.reset("tok")

        t1 = threading.Thread(target=trigger_and_check)
        t2 = threading.Thread(target=reset_loop)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == [], f"Race condition detected: {errors[:5]}"


class TestSafetyEnvironmentCheck:
    """測試安全環境檢查"""
    
    def test_simulation_mode_returns_true(self, monkeypatch):
        """測試模擬模式返回 True"""
        monkeypatch.setenv("POWER_CONTROL_SIMULATION", "true")
        
        result = check_safety_environment()
        
        assert result is True
    
    def test_production_mode_without_token_exits(self, monkeypatch):
        """測試生產模式無 token 時退出"""
        monkeypatch.setenv("POWER_CONTROL_SIMULATION", "false")
        monkeypatch.delenv("POWER_CONTROL_SAFETY_TOKEN", raising=False)
        
        with pytest.raises(SystemExit):
            check_safety_environment()
    
    def test_production_mode_without_confirmation_exits(self, monkeypatch):
        """測試生產模式無確認時退出"""
        monkeypatch.setenv("POWER_CONTROL_SIMULATION", "false")
        monkeypatch.setenv("POWER_CONTROL_SAFETY_TOKEN", "token")
        monkeypatch.delenv("POWER_CONTROL_CONFIRM_PRODUCTION", raising=False)
        
        with pytest.raises(SystemExit):
            check_safety_environment()
    
    def test_production_mode_with_full_auth(self, monkeypatch):
        """測試生產模式完整授權"""
        monkeypatch.setenv("POWER_CONTROL_SIMULATION", "false")
        monkeypatch.setenv("POWER_CONTROL_SAFETY_TOKEN", "token")
        monkeypatch.setenv("POWER_CONTROL_CONFIRM_PRODUCTION", "I_UNDERSTAND_THE_RISKS")
        
        result = check_safety_environment()
        
        assert result is False  # False 表示非模擬模式


class TestIEEE2030_5Integration:
    """測試 IEEE 2030.5 整合場景"""
    
    @pytest.fixture
    def controller(self):
        return SafePowerController(PowerControlConfig(simulation_mode=True))
    
    @pytest.mark.asyncio
    async def test_der_control_op_mod_fixed_w_simulation(self, controller):
        """測試 DER Control opModFixedW 模擬模式"""
        # 模擬從 IEEE 2030.5 Server 收到的功率指令
        # opModFixedW: 50kW = 50000W
        power_w = 50_000
        
        result = await controller.set_power_setpoint(power_w, source="ieee2030.5")
        
        assert result.simulated is True
        assert result.executed is False
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_der_control_charge_command(self, controller):
        """測試 DER Control 充電指令"""
        # 負值表示充電
        power_w = -30_000  # 30kW 充電
        
        result = await controller.set_power_setpoint(power_w, source="ieee2030.5")
        
        assert result.success is True
        assert result.requested_power_w == -30_000
    
    @pytest.mark.asyncio
    async def test_der_control_respects_limits(self, controller):
        """測試 DER Control 遵守功率限制"""
        # 嘗試設定超出限制的功率
        power_w = 200_000  # 超出 100kW 限制
        
        result = await controller.set_power_setpoint(power_w, source="ieee2030.5")
        
        assert result.success is False
        assert "exceeds limit" in result.errors[0]
