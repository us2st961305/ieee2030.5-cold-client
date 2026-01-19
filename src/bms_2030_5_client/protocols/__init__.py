"""
BMS/EMS Communication Protocol Definitions.

This module contains register mappings and message definitions for:
- RS-485 Modbus RTU (BMS to EMS communication protocol V1.7)
- CUBE Modbus TCP/IP (CUBE 電池組暫存器通訊表 V1.0.3)
- CAN 2.0B messaging
- IEEE 2030.5 Smart Energy Profile (IEEE Std 2030.5-2023)
"""

from .modbus_registers import (
    RS485_REGISTERS,
    RS485_BALANCE_REGISTERS,
    CUBE_RACK_REGISTERS,
    CUBE_SYSTEM_REGISTERS,
    ErrorStatusBits,
    RackFlagBits,
    LECUFlagBits,
    BalanceFunctionBits,
    ModbusConfig,
)

from .can_messages import (
    CAN_CONFIG,
    CAN_READ_COMMANDS,
    CAN_RESPONSE_IDS,
    CAN_CONTROL_COMMANDS,
    CAN_WRITE_COMMANDS,
)

from .ieee2030_5_protocol import (
    IEEE2030_5_CONFIG,
    HTTPMethod,
    HTTPStatus,
    FunctionSetIdentifiers,
    DERType,
    ConnectStatusType,
    OperationalModeStatusType,
    InverterStatusType,
    StorageModeStatusType,
    AlarmStatusType,
    DERControlType,
    UnitOfMeasure,
    PowerOfTenMultiplier,
    URIPaths,
    DeviceIdentifier,
    ResponseRequired,
    ResponseStatus,
    QualityFlags,
    watts_to_sep_value,
    sep_value_to_watts,
    soc_to_sep_value,
    sep_value_to_soc,
    # LogEvent definitions
    FunctionSetIdentifier,
    LogEventCode,
    LOG_EVENT_CODE_DESCRIPTIONS,
)

__all__ = [
    # RS-485 Registers
    "RS485_REGISTERS",
    "RS485_BALANCE_REGISTERS",
    # CUBE Registers
    "CUBE_RACK_REGISTERS",
    "CUBE_SYSTEM_REGISTERS",
    # Bit Definitions
    "ErrorStatusBits",
    "RackFlagBits",
    "LECUFlagBits",
    "BalanceFunctionBits",
    # Modbus Config
    "ModbusConfig",
    # CAN Definitions
    "CAN_CONFIG",
    "CAN_READ_COMMANDS",
    "CAN_RESPONSE_IDS",
    "CAN_CONTROL_COMMANDS",
    "CAN_WRITE_COMMANDS",
    # IEEE 2030.5 Definitions
    "IEEE2030_5_CONFIG",
    "HTTPMethod",
    "HTTPStatus",
    "FunctionSetIdentifiers",
    "DERType",
    "ConnectStatusType",
    "OperationalModeStatusType",
    "InverterStatusType",
    "StorageModeStatusType",
    "AlarmStatusType",
    "DERControlType",
    "UnitOfMeasure",
    "PowerOfTenMultiplier",
    "URIPaths",
    "DeviceIdentifier",
    "ResponseRequired",
    "ResponseStatus",
    "QualityFlags",
    # Conversion Helpers
    "watts_to_sep_value",
    "sep_value_to_watts",
    "soc_to_sep_value",
    "sep_value_to_soc",
    # LogEvent definitions
    "FunctionSetIdentifier",
    "LogEventCode",
    "LOG_EVENT_CODE_DESCRIPTIONS",
]
