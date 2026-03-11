"""
IEEE 2030.5 BMS Client Package

A Python client for integrating Battery Management Systems with IEEE 2030.5 servers.

模組結構:
- core: SEP HTTP Client (mTLS)
- subscription: 訂閱管理器 + 通知伺服器 (主要模組)
- modbus: Modbus TCP/RTU 通訊
- external_api: 外部整合 API (供外部程式串接)
- polling: 背景輪詢 Worker
- runtime_config: 統一配置
- web: Flask Web UI (開發/調試用)
- subs: 簡化版訂閱管理 (Web UI 用)
"""

from bms_2030_5_client.client import BMSClient
from bms_2030_5_client.config import Config
from bms_2030_5_client.runtime_config import RuntimeConfig

# Export specialized modules
from bms_2030_5_client import ders, dera, mup

# Export External Integration API
from bms_2030_5_client.external_api import (
    ExternalIntegrationAPI,
    PowerCommand,
    BMSStatusReport,
    RackStatusReport,
    CommandAcknowledgment,
    APIStatus,
    PowerCommandType,
    ControlSource,
    get_external_api,
    init_external_api,
    # Backward compatibility aliases
    ModbusIntegrationAPI,
    get_modbus_api,
    init_modbus_api,
)

__version__ = "0.2.0"
__all__ = [
    # Main client
    "BMSClient",
    # Configuration
    "Config",
    "RuntimeConfig",
    # Specialized modules
    "ders",
    "dera",
    "mup",
    # External Integration API
    "ExternalIntegrationAPI",
    "PowerCommand",
    "BMSStatusReport",
    "RackStatusReport",
    "CommandAcknowledgment",
    "APIStatus",
    "PowerCommandType",
    "ControlSource",
    "get_external_api",
    "init_external_api",
    # Backward compatibility aliases
    "ModbusIntegrationAPI",
    "get_modbus_api",
    "init_modbus_api",
]
