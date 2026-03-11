# IEEE 2030.5 Client 外部整合 API - Copilot 開發指南

> **本文件供 GitHub Copilot 或其他 AI 助手參考，用於編寫與 IEEE 2030.5 BMS Client 串接的外部程式。**

---

## 快速開始

```python
from bms_2030_5_client.external_api import (
    ExternalIntegrationAPI,
    get_external_api,
    init_external_api,
    PowerCommand,
    BMSStatusReport,
    RackStatusReport,
    PowerCommandType,
    ControlSource,
)
```

---

## API 概述

`ExternalIntegrationAPI` 是 IEEE 2030.5 Client 與外部程式的橋樑。

**用途：**
- 外部程式從 API 取得 IEEE 2030.5 DER Control 命令
- 外部程式向 API 回報 BMS/PCS 狀態
- 支援任意通訊協定（Modbus、CAN、REST、gRPC 等）

**資料流：**
```
IEEE 2030.5 Server ──DER Control──▶ BMSClient ──▶ ExternalIntegrationAPI
                                                          │
                                                          ▼
                                                    PowerCommand
                                                          │
                                                          ▼
                                                     外部程式
                                                          │
                                                          ▼
                                                    PCS/BMS 設備
                                                          │
                                                          ▼
                                                   BMSStatusReport
                                                          │
                                                          ▼
ExternalIntegrationAPI ◀────────────────────────────────┘
         │
         ▼
IEEE 2030.5 Server ◀── DER Status / Meter Readings
```

---

## 資料結構

### PowerCommand（功率控制命令）

```python
@dataclass
class PowerCommand:
    command_type: PowerCommandType  # 命令類型
    power_w: int                    # 功率 (W)，正=放電，負=充電
    duration_s: int                 # 持續時間 (秒)，0=無限
    start_time: int                 # 開始時間 (Unix timestamp)
    end_time: int                   # 結束時間 (Unix timestamp)
    source: ControlSource           # 控制來源
    priority: int                   # 優先級 (0-255，0最高)
    control_id: str                 # IEEE 2030.5 DERControl mRID
    ramp_rate_w_per_s: int          # 爬坡速率 (W/s)
    is_active: bool                 # 命令是否有效
    sequence_number: int            # 命令序號（用於確認）
    created_at: datetime            # 創建時間
```

### PowerCommandType（命令類型列舉）

```python
class PowerCommandType(IntEnum):
    NONE = 0              # 無命令
    SET_POWER = 1         # 設定功率
    SET_CHARGE = 2        # 設定充電功率
    SET_DISCHARGE = 3     # 設定放電功率
    LIMIT_POWER = 4       # 限制功率
    EMERGENCY_STOP = 5    # 緊急停止
```

### ControlSource（控制來源列舉）

```python
class ControlSource(IntEnum):
    MANUAL = 0            # 手動
    IEEE2030_5 = 1        # IEEE 2030.5 DER Control
    SCHEDULE = 2          # 排程
    DRLC = 3              # 需量反應負載控制
    PRICING = 4           # 價格信號
    LOCAL = 5             # 本地控制
```

### BMSStatusReport（BMS 狀態回報）

```python
@dataclass
class BMSStatusReport:
    timestamp: datetime              # 資料時間戳
    system_voltage: float            # 系統電壓 (V)
    system_current: float            # 系統電流 (A)，正=充電，負=放電
    system_soc: float                # 系統 SOC (%)
    system_power: float              # 系統功率 (W)
    charge_energy_kwh: float         # 今日充電能量 (kWh)
    discharge_energy_kwh: float      # 今日放電能量 (kWh)
    max_temperature: float           # 最高溫度 (°C)
    min_temperature: float           # 最低溫度 (°C)
    avg_temperature: float           # 平均溫度 (°C)
    active_rack_count: int           # 活動電池架數量
    total_rack_count: int            # 總電池架數量
    alarm_status: int                # 告警狀態 (bitfield)
    system_status: int               # 系統狀態 (0=離線, 1=線上)
    allowed_charge_power_w: float    # 允許充電功率 (W)
    allowed_discharge_power_w: float # 允許放電功率 (W)
    remaining_capacity_ah: float     # 剩餘容量 (Ah)
    full_charge_capacity_ah: float   # 滿充容量 (Ah)
    soh: float                       # 健康狀態 (%)
    cycle_count: int                 # 循環次數
    rack_data: List[Dict]            # 各電池架詳細資料
```

### RackStatusReport（電池架狀態）

```python
@dataclass
class RackStatusReport:
    rack_id: int            # 電池架 ID (0-23)
    voltage: float          # 電壓 (V)
    current: float          # 電流 (A)
    soc: float              # SOC (%)
    soh: float              # SOH (%)
    cell_max_voltage: float # 最高電芯電壓 (V)
    cell_min_voltage: float # 最低電芯電壓 (V)
    cell_max_temp: float    # 最高電芯溫度 (°C)
    cell_min_temp: float    # 最低電芯溫度 (°C)
    status: int             # 狀態 (0=離線, 1=待機, 2=充電, 3=放電, 4=故障)
    alarm_status: int       # 告警狀態 (bitfield)
```

---

## 核心 API 方法

### 1. 取得 API 實例

```python
# 取得全域單例
api = get_external_api()

# 或初始化並連接 BMSClient
api = init_external_api(bms_client=client)
```

### 2. 取得功率控制命令

```python
# 回傳 PowerCommand 物件
command = await api.get_power_command()

# 回傳字典格式（適合 JSON 傳輸）
command_dict = await api.get_power_command_dict()
```

### 3. 確認命令執行

```python
await api.acknowledge_command(
    sequence_number=command.sequence_number,  # 必填：命令序號
    success=True,                             # 必填：是否成功
    actual_power_w=50000,                     # 可選：實際功率
    error_code=0,                             # 可選：錯誤碼
    error_message="",                         # 可選：錯誤訊息
)
```

### 4. 回報 BMS 狀態

```python
# 使用 dataclass
status = BMSStatusReport(
    system_voltage=750.0,
    system_current=100.0,
    system_soc=75.0,
    system_power=75000.0,
    # ... 其他欄位
)
await api.report_bms_status(status)

# 使用字典（適合 JSON 傳輸）
await api.report_bms_status_dict({
    "system_voltage": 750.0,
    "system_current": 100.0,
    "system_soc": 75.0,
    "system_power": 75000.0,
    # ... 其他欄位
})
```

### 5. 緊急停止

```python
await api.emergency_stop(reason="BMS critical alarm")
```

### 6. 取得功率限制

```python
limits = await api.get_power_limits()
# 回傳:
# {
#     "max_charge_w": 100000,
#     "max_discharge_w": 100000,
#     "max_ramp_rate_w_per_s": 10000,
#     "min_soc_percent": 10.0,
#     "max_soc_percent": 90.0
# }
```

### 7. 取得 API 狀態

```python
status = await api.get_api_status_dict()
# 回傳:
# {
#     "is_connected": true,
#     "ieee2030_5_connected": true,
#     "last_command_time": "2025-02-11T10:00:00",
#     "last_status_time": "2025-02-11T10:00:05",
#     "pending_commands": 1,
#     "simulation_mode": true,
#     "control_mode": "simulation"
# }
```

---

## 典型整合模式

### 模式 A：Polling 模式（推薦）

```python
import asyncio
from bms_2030_5_client.external_api import get_external_api, BMSStatusReport

async def main():
    api = get_external_api()
    
    async def command_loop():
        """定期查詢並執行命令"""
        while True:
            command = await api.get_power_command()
            
            if command.is_active:
                # 1. 執行功率控制（透過你的協定）
                success = await your_pcs_control(command.power_w)
                
                # 2. 回報確認
                await api.acknowledge_command(
                    sequence_number=command.sequence_number,
                    success=success,
                    actual_power_w=command.power_w if success else 0,
                )
            
            await asyncio.sleep(1)  # 每秒查詢
    
    async def status_loop():
        """定期回報 BMS 狀態"""
        while True:
            # 1. 從設備讀取狀態（透過你的協定）
            data = await your_bms_read()
            
            # 2. 回報給 API
            status = BMSStatusReport(
                system_voltage=data.voltage,
                system_current=data.current,
                system_soc=data.soc,
                system_power=data.power,
                max_temperature=data.max_temp,
                min_temperature=data.min_temp,
                active_rack_count=data.online_racks,
                total_rack_count=data.total_racks,
                alarm_status=data.alarms,
                system_status=1,
                allowed_charge_power_w=data.max_charge_kw * 1000,
                allowed_discharge_power_w=data.max_discharge_kw * 1000,
                soh=data.soh,
                cycle_count=data.cycles,
            )
            await api.report_bms_status(status)
            
            await asyncio.sleep(5)  # 每 5 秒回報
    
    await asyncio.gather(command_loop(), status_loop())

asyncio.run(main())
```

### 模式 B：回調模式

```python
from bms_2030_5_client.external_api import get_external_api

api = get_external_api()

# 註冊命令回調
def on_command(command):
    print(f"收到命令: {command.power_w}W")
    # 執行控制...

api.add_command_callback(on_command)

# 註冊狀態回調（當狀態被接收時觸發）
def on_status(status):
    print(f"狀態已更新: SOC={status.system_soc}%")

api.add_status_callback(on_status)
```

### 模式 C：REST API 整合

```python
from flask import Flask, jsonify, request
from bms_2030_5_client.external_api import get_external_api
import asyncio

app = Flask(__name__)

def run_async(coro):
    """同步包裝非同步函數"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route("/api/command", methods=["GET"])
def get_command():
    api = get_external_api()
    command = run_async(api.get_power_command_dict())
    return jsonify(command)

@app.route("/api/command/ack", methods=["POST"])
def ack_command():
    api = get_external_api()
    data = request.json
    result = run_async(api.acknowledge_command(
        sequence_number=data["sequence_number"],
        success=data["success"],
        actual_power_w=data.get("actual_power_w", 0),
    ))
    return jsonify({"accepted": result})

@app.route("/api/status", methods=["POST"])
def post_status():
    api = get_external_api()
    result = run_async(api.report_bms_status_dict(request.json))
    return jsonify({"accepted": result})

@app.route("/api/emergency-stop", methods=["POST"])
def emergency_stop():
    api = get_external_api()
    reason = request.json.get("reason", "API trigger")
    result = run_async(api.emergency_stop(reason))
    return jsonify({"triggered": result})
```

---

## Modbus TCP 整合範例

```python
from pymodbus.client import AsyncModbusTcpClient
from bms_2030_5_client.external_api import get_external_api, BMSStatusReport

class ModbusIntegration:
    BMS_HOST = "192.168.1.100"
    PCS_HOST = "192.168.1.101"
    
    def __init__(self):
        self.api = get_external_api()
        self.bms_client = None
        self.pcs_client = None
    
    async def connect(self):
        self.bms_client = AsyncModbusTcpClient(self.BMS_HOST)
        self.pcs_client = AsyncModbusTcpClient(self.PCS_HOST)
        await self.bms_client.connect()
        await self.pcs_client.connect()
    
    async def read_bms(self) -> BMSStatusReport:
        """從 BMS 讀取狀態"""
        result = await self.bms_client.read_holding_registers(3999, 44)
        regs = result.registers
        
        def signed16(v): return v - 65536 if v > 32767 else v
        
        return BMSStatusReport(
            system_voltage=regs[0] * 0.1,
            system_current=signed16(regs[1]) * 0.1,
            system_power=signed16(regs[2]) * 100,
            system_soc=regs[5] * 0.1,
            charge_energy_kwh=regs[3] * 0.1,
            discharge_energy_kwh=regs[4] * 0.1,
            remaining_capacity_ah=regs[6],
            full_charge_capacity_ah=regs[7],
            active_rack_count=regs[8],
            max_temperature=signed16(regs[16]),
            min_temperature=signed16(regs[17]),
            allowed_discharge_power_w=regs[42] * 100,
            allowed_charge_power_w=regs[43] * 100,
            system_status=regs[12],
        )
    
    async def write_pcs_power(self, power_w: int) -> bool:
        """寫入 PCS 功率設定點"""
        value = int(power_w / 100)
        if value < 0:
            value += 65536
        result = await self.pcs_client.write_register(40001, value)
        return not result.isError()
    
    async def run(self):
        await self.connect()
        
        while True:
            # 查詢命令
            command = await self.api.get_power_command()
            if command.is_active:
                success = await self.write_pcs_power(command.power_w)
                await self.api.acknowledge_command(
                    command.sequence_number, success,
                    actual_power_w=command.power_w if success else 0
                )
            
            # 回報狀態
            status = await self.read_bms()
            await self.api.report_bms_status(status)
            
            await asyncio.sleep(1)
```

---

## CAN Bus 整合範例

```python
import can
from bms_2030_5_client.external_api import get_external_api, BMSStatusReport

class CANIntegration:
    def __init__(self, channel="can0", bustype="socketcan"):
        self.api = get_external_api()
        self.bus = can.interface.Bus(channel=channel, bustype=bustype)
    
    def parse_bms_frame(self, msg: can.Message) -> dict:
        """解析 BMS CAN 訊息"""
        data = {}
        if msg.arbitration_id == 0x100:  # 系統狀態
            data["voltage"] = int.from_bytes(msg.data[0:2], 'big') * 0.1
            data["current"] = int.from_bytes(msg.data[2:4], 'big', signed=True) * 0.1
            data["soc"] = msg.data[4] * 0.4
        elif msg.arbitration_id == 0x101:  # 溫度
            data["max_temp"] = msg.data[0] - 40
            data["min_temp"] = msg.data[1] - 40
        return data
    
    def build_power_frame(self, power_w: int) -> can.Message:
        """建立功率控制 CAN 訊息"""
        value = int(power_w / 10)
        data = value.to_bytes(4, 'big', signed=True)
        return can.Message(arbitration_id=0x200, data=data)
    
    async def run(self):
        bms_data = {}
        
        while True:
            # 接收 BMS 資料
            msg = self.bus.recv(timeout=0.1)
            if msg:
                bms_data.update(self.parse_bms_frame(msg))
            
            # 查詢並執行命令
            command = await self.api.get_power_command()
            if command.is_active:
                frame = self.build_power_frame(command.power_w)
                self.bus.send(frame)
                await self.api.acknowledge_command(
                    command.sequence_number, True, command.power_w
                )
            
            # 回報狀態
            if bms_data:
                status = BMSStatusReport(
                    system_voltage=bms_data.get("voltage", 0),
                    system_current=bms_data.get("current", 0),
                    system_soc=bms_data.get("soc", 0),
                    max_temperature=bms_data.get("max_temp", 0),
                    min_temperature=bms_data.get("min_temp", 0),
                )
                await self.api.report_bms_status(status)
            
            await asyncio.sleep(0.1)
```

---

## 錯誤碼對照表

| 錯誤碼 | 說明 |
|-------|------|
| 0 | 無錯誤 |
| 100 | BMS 通訊失敗 |
| 101 | PCS 通訊失敗 |
| 102 | 功率超出限制 |
| 103 | SOC 超出限制 |
| 104 | 爬坡速率超出限制 |
| 105 | 緊急停止中 |
| 200 | 命令序號不符 |
| 201 | 命令已過期 |
| 300 | 系統錯誤 |

---

## 告警狀態位元定義 (IEEE 2030.5 DER Alarm Status)

| Bit | 說明 |
|-----|------|
| 0 | DER_FAULT_OVER_CURRENT |
| 1 | DER_FAULT_OVER_VOLTAGE |
| 2 | DER_FAULT_UNDER_VOLTAGE |
| 3 | DER_FAULT_OVER_FREQUENCY |
| 4 | DER_FAULT_UNDER_FREQUENCY |
| 5 | DER_FAULT_VOLTAGE_IMBALANCE |
| 6 | DER_FAULT_CURRENT_IMBALANCE |
| 7 | DER_FAULT_EMERGENCY_LOCAL |
| 8 | DER_FAULT_EMERGENCY_REMOTE |
| 9 | DER_FAULT_LOW_POWER_INPUT |
| 10 | DER_FAULT_PHASE_ROTATION |

---

## 最佳實踐

1. **定期查詢命令**：建議每 1 秒查詢一次 `get_power_command()`
2. **立即確認命令**：執行完畢後立即呼叫 `acknowledge_command()`
3. **定期回報狀態**：建議每 5 秒呼叫一次 `report_bms_status()`
4. **處理緊急停止**：檢查 `command_type == EMERGENCY_STOP` 時立即停止
5. **檢查功率限制**：執行前先呼叫 `get_power_limits()` 檢查限制
6. **錯誤處理**：確認失敗時提供 `error_code` 和 `error_message`

---

## 版本資訊

- API 版本: 1.0.0
- 最後更新: 2025-02-11
- 相容性: Python 3.9+
