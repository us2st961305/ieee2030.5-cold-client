# IEEE 2030.5 BMS Client

一個用於連接 IEEE 2030.5 伺服器並整合電池管理系統（BMS）的 Python 客戶端。

> **📦 Recent Restructuring:** The codebase has been reorganized into modular components for better maintainability. See [RESTRUCTURING.md](RESTRUCTURING.md) for details about the new `ders`, `dera`, and `mup` modules.

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

### 使用 runtime.yaml (推薦)

新版本使用 `config/runtime.yaml` 作為統一配置檔。

```bash
cp config/runtime.example.yaml config/runtime.yaml
```

詳細配置說明請參考 [Runtime Configuration](#runtime-configuration-詳細說明)。

### Legacy 配置

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

## Web UI 管理面板

啟動 Web UI：

```bash
# 預設埠號 5000
bms-web

# 自訂埠號
bms-web --port 8080

# Debug 模式
bms-web --debug
```

### Dashboard 功能

| 元件 | 說明 |
|------|------|
| **Polling Worker** | 背景輪詢 IEEE 2030.5 資源並寫入 Modbus |
| **Subscription Manager** | 管理 IEEE 2030.5 訂閱生命週期 |
| **Notification Server** | 接收伺服器推送的通知 |

### API 端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/start` | POST | 啟動所有元件 |
| `/api/stop` | POST | 停止所有元件 |
| `/api/reload` | POST | 重載配置並套用 |
| `/notify` | POST | 接收 IEEE 2030.5 Notification |

---

## Runtime Configuration 詳細說明

### 完整 runtime.yaml 範例

```yaml
# config/runtime.yaml
schema_version: "2.0.0"

# ============================================
# 1. Profiles: IEEE 2030.5 伺服器連線設定
# ============================================
profiles:
  - name: "production"
    server_base_url: "https://sep-server.example.com:7443"
    device_id: "bms-client-001"
    pin: 12345
    content_type_preference: "application/sep+xml"
    tls:
      client_cert_path: "certs/client.crt"
      client_key_path: "certs/client.key"
      ca_bundle_path: "certs/ca.crt"
      verify_server: true

# ============================================
# 2. Modbus: BMS 通訊設定
# ============================================
modbus:
  mode: "tcp"
  host: "192.168.1.100"
  port: 502
  unit_id: 1
  timeout: 5.0

# ============================================
# 3. Poll Targets: 輪詢目標
# ============================================
poll_targets:
  - id: "der_status"
    name: "DER Status"
    enabled: true
    profile_name: "production"
    uri: "/edev/1/der/1/ders"
    interval_ms: 60000
    parse:
      format: "sep_xml"
      xpath: "//stateOfChargeStatus/value"
    transform:
      scale: 0.01   # 10000 -> 100%
    modbus_write:
      address: 4100
      datatype: "uint16"
      scale: 10     # 100% -> 1000

# ============================================
# 4. Subscriptions: 訂閱設定 (Push)
# ============================================
subscriptions:
  - id: "der_control_sub"
    name: "DER Control Subscription"
    enabled: true                      # ← 設為 true 啟用訂閱
    profile_name: "production"
    resource_uri: "/edev/1/der/1/derc"
    notification_endpoint: ""          # 留空使用 notification_server 設定
    renew_interval_hours: 24           # 每 24 小時續訂
    parse:
      xpath: "//DERControl/opModFixedW/value"
    modbus_write:
      address: 4200
      datatype: "int16"
      scale: 0.001

# ============================================
# 5. Notification Server: 通知接收端
# ============================================
notification_server:
  enabled: true                        # ← 設為 true 啟用
  listen_host: "0.0.0.0"
  listen_port: 8443
  endpoint_path: "/notify"             # POST /notify 接收通知
  public_uri: "https://192.168.1.50:8443"  # 填入此 client 的公開 URI
  
  # TLS Server 設定 (規範要求 HTTPS)
  tls_server_enabled: true
  tls_server_cert_path: "certs/server.crt"   # 伺服器憑證
  tls_server_key_path: "certs/server.key"    # 伺服器私鑰
  tls_require_client_cert: false              # 是否要求客戶端憑證 (mTLS)
  tls_client_ca_path: "certs/server_ca.crt"  # 客戶端 CA (僅 mTLS 需要)

# ============================================
# 6. Logging
# ============================================
logging:
  level: "INFO"
  buffer_size: 500
```

### 如何啟用 Subscription

1. 在 `subscriptions` 區塊加入訂閱設定
2. 設定 `enabled: true`
3. 填入 `resource_uri` (要訂閱的資源路徑)
4. 確保 `notification_server.enabled: true`
5. 設定正確的 `public_uri` (IEEE 2030.5 Server 回傳通知的目標位址)

```yaml
subscriptions:
  - id: "my_subscription"
    enabled: true                    # ← 必須為 true
    resource_uri: "/edev/1/der/1/derc"
    renew_interval_hours: 24

notification_server:
  enabled: true                      # ← 必須為 true
  public_uri: "https://YOUR_IP:8443" # ← 填入本機公開 IP
```

### TLS 憑證設定

#### 目錄結構

```
certs/
├── client.crt        # Client 憑證 (連線到 IEEE 2030.5 Server)
├── client.key        # Client 私鑰
├── ca.crt            # CA 憑證 (驗證 Server)
├── server.crt        # Server 憑證 (Notification Server)
├── server.key        # Server 私鑰
└── server_ca.crt     # Client CA (驗證連入的 Server，僅 mTLS)
```

#### 產生自簽憑證 (測試用)

```bash
# 產生 Notification Server 憑證
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/server.key \
  -out certs/server.crt \
  -days 365 \
  -subj "/CN=bms-notification-server"
```

---

## 測試 Notification Endpoint

### 使用 curl 發送測試通知

```bash
# HTTP 模式 (tls_server_enabled: false)
curl -X POST http://localhost:8443/notify \
  -H "Content-Type: application/sep+xml" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<Notification xmlns="urn:ieee:std:2030.5:ns">
  <subscriptionURI>/edev/1/sub/123</subscriptionURI>
  <subscribedResource>/edev/1/der/1/derc</subscribedResource>
  <status>3</status>
  <newResourceURI>/edev/1/der/1/derc/456</newResourceURI>
</Notification>'

# HTTPS 模式 (需要加 -k 忽略憑證驗證，或用正確的 CA)
curl -k -X POST https://localhost:8443/notify \
  -H "Content-Type: application/sep+xml" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<NotificationList xmlns="urn:ieee:std:2030.5:ns">
  <Notification>
    <subscriptionURI>/sub/1</subscriptionURI>
    <subscribedResource>/edev/1/der/1/derc</subscribedResource>
    <status>3</status>
  </Notification>
</NotificationList>'
```

### 預期回應

```
HTTP/1.1 204 No Content
```

### 在 Web UI 確認

1. 開啟 `http://localhost:5000`
2. 在 Dashboard 查看 **Notification Server** 卡片
3. 確認 **Received** 計數增加
4. 查看 **Recent Logs** 區塊

---

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

