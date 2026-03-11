"""
Modbus communication module.
"""

from bms_2030_5_client.modbus.modbus_client import (
    ModbusBMSClient,
    BMSDataCollector,
    ModbusClientError,
)
from bms_2030_5_client.modbus.power_writer import (
    ModbusPowerWriter,
    ModbusPowerWriterConfig,
    PowerWriteResult,
    PCSPowerAdapter,
    PCSRegisterAddress,
    PCSOperationMode,
)
from bms_2030_5_client.modbus.register_writer import (
    ModbusRegisterWriter,
    WriteResult,
    ModbusWriterError,
)
from bms_2030_5_client.modbus.modbus_writer import (
    ModbusWriter,
    DataType,
    WriteResult as ModbusWriteResult,
    create_writer,
)

__all__ = [
    "ModbusBMSClient",
    "BMSDataCollector",
    "ModbusClientError",
    # Power writing
    "ModbusPowerWriter",
    "ModbusPowerWriterConfig",
    "PowerWriteResult",
    "PCSPowerAdapter",
    "PCSRegisterAddress",
    "PCSOperationMode",
    # Register writing (async)
    "ModbusRegisterWriter",
    "WriteResult",
    "ModbusWriterError",
    # Modbus writer (sync)
    "ModbusWriter",
    "DataType",
    "ModbusWriteResult",
    "create_writer",
]
