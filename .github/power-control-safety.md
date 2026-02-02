# Power Control Safety Guidelines (功率控制安全規範)

## ⚠️ CRITICAL SAFETY RULES - 關鍵安全規則

**此文件定義了 IEEE 2030.5 功率控制開發的安全規範。所有開發和測試必須遵守這些規則。**

---

## 1. 絕對禁止事項 (NEVER DO)

### 1.1 禁止直接控制 PCS
```
❌ 絕對禁止在測試或開發時直接向 PCS 發送功率控制指令
❌ 禁止繞過模擬模式直接操作實際硬體
❌ 禁止在沒有安全檢查的情況下執行 DER 控制命令
❌ 禁止硬編碼 PCS 的實際 IP 位址或控制端點
```

### 1.2 禁止的程式碼模式
```python
# ❌ 禁止：直接發送控制指令
async def set_power(watts: int):
    await pcs_client.write_register(POWER_REGISTER, watts)  # 危險！

# ❌ 禁止：沒有模擬模式檢查
def execute_der_control(control: DERControl):
    modbus_client.write(control.power_setpoint)  # 危險！

# ❌ 禁止：硬編碼實際設備位址
PCS_HOST = "192.168.1.187"  # 危險！不要硬編碼
```

---

## 2. 必須遵守事項 (ALWAYS DO)

### 2.1 強制使用模擬模式
所有開發和測試必須在模擬模式下進行：

```python
# ✅ 正確：使用模擬模式標誌
class PowerControlClient:
    def __init__(self, simulation_mode: bool = True):
        self.simulation_mode = simulation_mode
        if not simulation_mode:
            raise SafetyError("Production mode requires explicit authorization")
    
    async def set_power_setpoint(self, watts: int) -> None:
        if self.simulation_mode:
            logger.info(f"[SIMULATION] Would set power to {watts}W")
            return
        # 實際控制邏輯需要額外的安全層
```

### 2.2 強制安全檢查層
所有功率控制必須經過安全驗證：

```python
# ✅ 正確：多層安全檢查
class SafePowerController:
    def __init__(self, config: PowerControlConfig):
        self.simulation_mode = config.simulation_mode
        self.max_power_w = config.max_power_w
        self.safety_enabled = True
    
    def validate_power_command(self, watts: int) -> bool:
        """驗證功率指令是否在安全範圍內"""
        if abs(watts) > self.max_power_w:
            raise PowerLimitExceeded(f"Power {watts}W exceeds limit {self.max_power_w}W")
        return True
    
    async def request_power_change(self, watts: int) -> PowerControlResult:
        # 1. 檢查模擬模式
        if self.simulation_mode:
            return PowerControlResult(simulated=True, requested_power=watts)
        
        # 2. 檢查安全開關
        if not self.safety_enabled:
            raise SafetyDisabledError("Safety system is disabled")
        
        # 3. 驗證功率範圍
        self.validate_power_command(watts)
        
        # 4. 記錄操作
        logger.warning(f"PRODUCTION: Requesting power change to {watts}W")
        
        # 5. 執行（需要額外授權）
        return await self._execute_with_confirmation(watts)
```

### 2.3 配置文件安全預設
```yaml
# config/config.yaml - 安全預設值
power_control:
  # 預設必須為 True，只有在生產環境且經過授權才能設為 False
  simulation_mode: true
  
  # 功率限制（即使在生產模式也要遵守）
  max_charge_power_kw: 100
  max_discharge_power_kw: 100
  
  # 功率變化速率限制 (kW/s)
  ramp_rate_limit: 10
  
  # 安全確認
  require_confirmation: true
  confirmation_timeout_s: 30
```

---

## 3. 測試規範

### 3.1 單元測試必須使用 Mock
```python
# ✅ 正確：使用 Mock 進行測試
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_power_controller():
    """提供模擬的功率控制器"""
    controller = Mock(spec=PowerController)
    controller.simulation_mode = True
    controller.set_power = AsyncMock(return_value=PowerControlResult(simulated=True))
    return controller

def test_der_control_uses_simulation(mock_power_controller):
    """確保 DER 控制使用模擬模式"""
    assert mock_power_controller.simulation_mode is True
```

### 3.2 整合測試使用模擬伺服器
```python
# ✅ 正確：使用模擬 Modbus 伺服器
@pytest.fixture
async def simulated_modbus_server():
    """啟動模擬 Modbus 伺服器進行測試"""
    server = SimulatedModbusServer(
        host="127.0.0.1",
        port=5020,  # 使用非標準端口
        simulation_mode=True
    )
    await server.start()
    yield server
    await server.stop()
```

### 3.3 禁止在測試中連接實際設備
```python
# conftest.py - 強制安全檢查
import pytest
import os

@pytest.fixture(autouse=True)
def enforce_simulation_mode(monkeypatch):
    """強制所有測試使用模擬模式"""
    monkeypatch.setenv("POWER_CONTROL_SIMULATION", "true")
    monkeypatch.setenv("ALLOW_REAL_PCS_CONNECTION", "false")

def pytest_configure(config):
    """pytest 啟動時的安全檢查"""
    if os.getenv("ALLOW_REAL_PCS_CONNECTION", "false").lower() == "true":
        pytest.exit("ERROR: Real PCS connection is not allowed in test environment!")
```

---

## 4. DER 控制安全實現

### 4.1 IEEE 2030.5 DER Control 安全包裝
```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class ControlMode(Enum):
    SIMULATION = "simulation"
    DRY_RUN = "dry_run"      # 記錄但不執行
    PRODUCTION = "production"  # 需要特殊授權

@dataclass
class SafeDERControlRequest:
    """安全的 DER 控制請求"""
    control_mode: ControlMode
    op_mod_fixed_w: Optional[int] = None  # 固定功率模式 (W)
    op_mod_fixed_var: Optional[int] = None  # 固定無功功率 (VAR)
    
    def __post_init__(self):
        if self.control_mode == ControlMode.PRODUCTION:
            raise ValueError(
                "Production mode requires SafeDERControlRequest.create_production() "
                "with explicit authorization token"
            )
    
    @classmethod
    def create_simulation(cls, **kwargs) -> "SafeDERControlRequest":
        """創建模擬模式的控制請求"""
        return cls(control_mode=ControlMode.SIMULATION, **kwargs)
    
    @classmethod
    def create_dry_run(cls, **kwargs) -> "SafeDERControlRequest":
        """創建乾跑模式的控制請求（記錄但不執行）"""
        return cls(control_mode=ControlMode.DRY_RUN, **kwargs)
```

### 4.2 功率限制驗證器
```python
@dataclass
class PowerLimits:
    """功率限制配置"""
    max_charge_w: int = 100_000      # 最大充電功率 100kW
    max_discharge_w: int = 100_000   # 最大放電功率 100kW
    max_ramp_rate_w_per_s: int = 10_000  # 最大變化速率 10kW/s
    min_soc_percent: float = 10.0    # 最低 SOC 限制
    max_soc_percent: float = 90.0    # 最高 SOC 限制

class PowerValidator:
    def __init__(self, limits: PowerLimits):
        self.limits = limits
    
    def validate(self, requested_power_w: int, current_soc: float) -> list[str]:
        """驗證功率請求，返回錯誤列表（空列表表示通過）"""
        errors = []
        
        # 充電功率檢查（負值表示充電）
        if requested_power_w < 0:
            if abs(requested_power_w) > self.limits.max_charge_w:
                errors.append(
                    f"Charge power {abs(requested_power_w)}W exceeds limit "
                    f"{self.limits.max_charge_w}W"
                )
            if current_soc >= self.limits.max_soc_percent:
                errors.append(
                    f"SOC {current_soc}% at or above max limit "
                    f"{self.limits.max_soc_percent}%"
                )
        
        # 放電功率檢查（正值表示放電）
        if requested_power_w > 0:
            if requested_power_w > self.limits.max_discharge_w:
                errors.append(
                    f"Discharge power {requested_power_w}W exceeds limit "
                    f"{self.limits.max_discharge_w}W"
                )
            if current_soc <= self.limits.min_soc_percent:
                errors.append(
                    f"SOC {current_soc}% at or below min limit "
                    f"{self.limits.min_soc_percent}%"
                )
        
        return errors
```

---

## 5. 日誌和審計

### 5.1 所有功率控制必須記錄
```python
import logging
from datetime import datetime

# 創建專用的功率控制日誌
power_control_logger = logging.getLogger("power_control.audit")
power_control_logger.setLevel(logging.INFO)

def log_power_control_request(
    request_id: str,
    mode: ControlMode,
    requested_power_w: int,
    source: str,  # IEEE2030.5, Manual, etc.
    result: str
):
    """記錄所有功率控制請求"""
    power_control_logger.info(
        f"POWER_CONTROL | "
        f"id={request_id} | "
        f"mode={mode.value} | "
        f"power={requested_power_w}W | "
        f"source={source} | "
        f"result={result} | "
        f"timestamp={datetime.utcnow().isoformat()}"
    )
```

---

## 6. 環境變數安全檢查

```python
# 啟動時的安全檢查
import os
import sys

def check_safety_environment():
    """檢查安全環境變數"""
    simulation_mode = os.getenv("POWER_CONTROL_SIMULATION", "true").lower()
    
    if simulation_mode != "true":
        # 非模擬模式需要額外的安全確認
        safety_token = os.getenv("POWER_CONTROL_SAFETY_TOKEN")
        if not safety_token:
            print("ERROR: Production mode requires POWER_CONTROL_SAFETY_TOKEN")
            sys.exit(1)
        
        confirm = os.getenv("POWER_CONTROL_CONFIRM_PRODUCTION")
        if confirm != "I_UNDERSTAND_THE_RISKS":
            print("ERROR: Production mode requires explicit confirmation")
            print("Set POWER_CONTROL_CONFIRM_PRODUCTION='I_UNDERSTAND_THE_RISKS'")
            sys.exit(1)
    
    return simulation_mode == "true"
```

---

## 7. Copilot 開發指引

### 當 Copilot 協助開發功率控制相關功能時：

1. **永遠先問**：是否需要連接實際 PCS？如果答案是否定的，確保使用模擬模式。

2. **預設安全**：所有新代碼必須預設為 `simulation_mode=True`。

3. **不要生成**：
   - 直接連接 PCS 的代碼
   - 繞過安全檢查的代碼
   - 硬編碼的設備位址

4. **必須包含**：
   - 模擬模式檢查
   - 功率限制驗證
   - 適當的日誌記錄
   - 錯誤處理

5. **測試代碼**：
   - 使用 Mock 和模擬伺服器
   - 不連接實際硬體
   - 驗證安全檢查是否有效

---

## 8. 緊急停止

```python
class EmergencyStop:
    """緊急停止功能"""
    
    _instance = None
    _stopped = False
    
    @classmethod
    def trigger(cls, reason: str):
        """觸發緊急停止"""
        cls._stopped = True
        power_control_logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")
    
    @classmethod
    def is_stopped(cls) -> bool:
        """檢查是否已緊急停止"""
        return cls._stopped
    
    @classmethod
    def reset(cls, authorization_token: str):
        """重置緊急停止（需要授權）"""
        # 驗證授權...
        cls._stopped = False
        power_control_logger.warning("Emergency stop reset")
```

---

## 版本歷史

| 版本 | 日期 | 變更說明 |
|------|------|----------|
| 1.0 | 2026-02-02 | 初始版本 |

---

**記住：安全第一！寧可多一層檢查，也不要冒險直接控制 PCS。**
