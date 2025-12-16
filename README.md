# IEEE 2030.5 BMS Client

一個用於連接 IEEE 2030.5 伺服器並整合電池管理系統（BMS）的 Python 客戶端。

## 功能特點

- **IEEE 2030.5 協定支援**：完整實作 CSIP (Common Smart Inverter Profile) 客戶端
- **Modbus TCP/IP 整合**：與 CUBE 電池組 BMS 通訊
- **多 Rack 支援**：支援最多 24 個電池 Rack（暫存器偏移 30）
- **TLS 安全連線**：使用 X.509 憑證進行雙向驗證
- **非同步架構**：基於 asyncio 的高效能設計

## 系統架構

```
┌─────────────────┐     Modbus TCP     ┌─────────────────┐
│   CUBE BMS      │◄──────────────────►│                 │
│  (電池 Racks)    │     Port 502       │                 │
└─────────────────┘                    │   BMS Client    │
                                       │                 │
┌─────────────────┐     HTTPS/TLS      │                 │
│  IEEE 2030.5    │◄──────────────────►│                 │
│    Server       │     Port 7443      │                 │
└─────────────────┘                    └─────────────────┘
```

## 安裝

### 使用 Poetry（推薦）

```bash
# 安裝 Poetry
pip install poetry

# 安裝依賴
poetry install

# 啟用虛擬環境
poetry shell
```

### 使用 pip

```bash
pip install -e .
```

## 配置

編輯 `config/config.yaml`：

```yaml
# IEEE 2030.5 伺服器設定
ieee2030_5:
  server_url: "https://localhost:7443"
  dcap_path: "/dcap"
  cert_file: "certs/client.crt"
  key_file: "certs/client.pem"
  ca_file: "certs/ca.crt"
  poll_rate: 30

# Modbus BMS 設定
modbus:
  host: "192.168.1.100"
  port: 502
  unit_id: 1
  timeout: 5.0
  rack_count: 4
  refresh_interval: 0.5
```

## 使用方式

### 啟動客戶端

```bash
# 使用預設配置
bms-client

# 指定配置檔
bms-client --config /path/to/config.yaml

# Debug 模式
bms-client --debug
```

### 程式化使用

```python
import asyncio
from bms_2030_5_client import BMSClient

async def main():
    client = BMSClient.from_config("config/config.yaml")
    await client.start()
    
    # 取得電池狀態
    status = await client.get_battery_status()
    print(f"SOC: {status.soc}%")
    print(f"Voltage: {status.voltage}V")
    
    await client.stop()

asyncio.run(main())
```

## Modbus 暫存器對應

### Rack 等級資料（7000 系列）

| 暫存器 | 名稱 | 格式 | 單位 |
|--------|------|------|------|
| 7000 | rack_vol | U16 | 0.1 V |
| 7001 | rack_current | S16 | 0.1 A |
| 7002 | SOC | U16 | 0.1 % |
| 7003 | cell_max_v | U16 | 0.001 V |
| 7004 | cell_min_v | U16 | 0.001 V |
| 7005 | cell_max_t | S16 | 1 °C |
| 7006 | cell_min_t | S16 | 1 °C |

每個 Rack 偏移 30，最多支援 24 個 Racks（0-23）。

## 開發

### 執行測試

```bash
pytest tests/ -v
```

### 程式碼格式化

```bash
black src/ tests/
ruff check src/ tests/
```

### 型別檢查

```bash
mypy src/
```

