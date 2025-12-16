"""
Configuration management for BMS 2030.5 Client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import yaml


@dataclass
class IEEE2030_5Config:
    """IEEE 2030.5 server configuration."""
    server_url: str = "https://localhost:7443"
    dcap_path: str = "/dcap"
    cert_file: str = "certs/client.crt"
    key_file: str = "certs/client.pem"
    ca_file: str = "certs/ca.crt"
    poll_rate: int = 30
    device_id: str = "bms-client-001"
    pin: int = 12345


@dataclass
class ModbusConfig:
    """Modbus TCP configuration."""
    host: str = "192.168.1.100"
    port: int = 502
    unit_id: int = 1
    timeout: float = 5.0
    rack_count: int = 4
    refresh_interval: float = 0.5


@dataclass
class RegisterConfig:
    """Register mapping configuration."""
    system_base_address: int = 4000
    system_count: int = 100
    rack_base_address: int = 7000
    rack_offset: int = 30
    max_racks: int = 24


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None


@dataclass
class Config:
    """Main configuration class."""
    ieee2030_5: IEEE2030_5Config = field(default_factory=IEEE2030_5Config)
    modbus: ModbusConfig = field(default_factory=ModbusConfig)
    registers: RegisterConfig = field(default_factory=RegisterConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "Config":
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        config = cls()

        if "ieee2030_5" in data:
            config.ieee2030_5 = IEEE2030_5Config(**data["ieee2030_5"])

        if "modbus" in data:
            config.modbus = ModbusConfig(**data["modbus"])

        if "registers" in data:
            reg_data = data["registers"]
            config.registers = RegisterConfig(
                system_base_address=reg_data.get("system", {}).get("base_address", 4000),
                system_count=reg_data.get("system", {}).get("count", 100),
                rack_base_address=reg_data.get("rack", {}).get("base_address", 7000),
                rack_offset=reg_data.get("rack", {}).get("offset", 30),
                max_racks=reg_data.get("rack", {}).get("max_racks", 24),
            )

        if "logging" in data:
            config.logging = LoggingConfig(**data["logging"])

        return config

    def to_yaml(self, path: Union[str, Path]) -> None:
        """Save configuration to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "ieee2030_5": {
                "server_url": self.ieee2030_5.server_url,
                "dcap_path": self.ieee2030_5.dcap_path,
                "cert_file": self.ieee2030_5.cert_file,
                "key_file": self.ieee2030_5.key_file,
                "ca_file": self.ieee2030_5.ca_file,
                "poll_rate": self.ieee2030_5.poll_rate,
                "device_id": self.ieee2030_5.device_id,
                "pin": self.ieee2030_5.pin,
            },
            "modbus": {
                "host": self.modbus.host,
                "port": self.modbus.port,
                "unit_id": self.modbus.unit_id,
                "timeout": self.modbus.timeout,
                "rack_count": self.modbus.rack_count,
                "refresh_interval": self.modbus.refresh_interval,
            },
            "registers": {
                "system": {
                    "base_address": self.registers.system_base_address,
                    "count": self.registers.system_count,
                },
                "rack": {
                    "base_address": self.registers.rack_base_address,
                    "offset": self.registers.rack_offset,
                    "max_racks": self.registers.max_racks,
                },
            },
            "logging": {
                "level": self.logging.level,
                "format": self.logging.format,
                "file": self.logging.file,
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
