"""
Runtime Configuration Schema for BMS IEEE 2030.5 Client.

Schema Version: 2.0.0
Reference: IEEE Std 2030.5™-2023

This module defines the complete runtime configuration schema including:
- Profiles: IEEE 2030.5 server connection settings
- Modbus: BMS communication settings
- Poll Targets: Polling configuration for server resources
- Subscriptions: Push-based notification subscriptions
- Notification Server: Client-side TLS server for receiving notifications
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

import logging as _logging
from urllib.parse import urlparse

_config_logger = _logging.getLogger(__name__)


# ============================================
# Validation Helpers
# ============================================

class ConfigValidationError(ValueError):
    """Raised when configuration values fail validation."""
    pass


_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _validate_enum(value: str, enum_cls: type, field_name: str) -> str:
    """Validate that value is a valid enum member value."""
    valid = {e.value for e in enum_cls}
    if value not in valid:
        raise ConfigValidationError(
            f"{field_name}: '{value}' is not valid. "
            f"Must be one of: {sorted(valid)}"
        )
    return value


def _validate_port(value: Any, field_name: str) -> int:
    """Validate port number is in range 1-65535."""
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ConfigValidationError(
            f"{field_name}: '{value}' is not a valid integer"
        )
    if not 1 <= port <= 65535:
        raise ConfigValidationError(
            f"{field_name}: {port} is out of range (1-65535)"
        )
    return port


def _validate_url(value: str, field_name: str) -> str:
    """Validate URL has http/https scheme and a host."""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ConfigValidationError(
            f"{field_name}: '{value}' must start with http:// or https://"
        )
    if not parsed.netloc:
        raise ConfigValidationError(
            f"{field_name}: '{value}' is missing a host"
        )
    return value


def _validate_type(value: Any, expected_type: type, field_name: str) -> Any:
    """Validate and coerce to expected type."""
    if value is None:
        return value
    try:
        return expected_type(value)
    except (TypeError, ValueError):
        raise ConfigValidationError(
            f"{field_name}: '{value}' cannot be converted to "
            f"{expected_type.__name__}"
        )


def _validate_positive(value: Any, field_name: str) -> float:
    """Validate that a numeric value is positive."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ConfigValidationError(
            f"{field_name}: '{value}' is not a valid number"
        )
    if num <= 0:
        raise ConfigValidationError(
            f"{field_name}: {num} must be positive"
        )
    return num


def _validate_log_level(value: str, field_name: str) -> str:
    """Validate logging level string."""
    upper = str(value).upper()
    if upper not in _VALID_LOG_LEVELS:
        raise ConfigValidationError(
            f"{field_name}: '{value}' is not valid. "
            f"Must be one of: {sorted(_VALID_LOG_LEVELS)}"
        )
    return upper


def _validate_range(
    value: Any, field_name: str, *, expected_type: type = int,
    ge: float | None = None, gt: float | None = None,
    le: float | None = None, lt: float | None = None,
) -> int | float:
    """Validate and coerce a numeric value to expected_type within bounds."""
    try:
        num = expected_type(value)
    except (TypeError, ValueError):
        raise ConfigValidationError(
            f"{field_name}: '{value}' cannot be converted to "
            f"{expected_type.__name__}"
        )
    if ge is not None and num < ge:
        raise ConfigValidationError(
            f"{field_name}: {num} must be >= {ge}"
        )
    if gt is not None and num <= gt:
        raise ConfigValidationError(
            f"{field_name}: {num} must be > {gt}"
        )
    if le is not None and num > le:
        raise ConfigValidationError(
            f"{field_name}: {num} must be <= {le}"
        )
    if lt is not None and num >= lt:
        raise ConfigValidationError(
            f"{field_name}: {num} must be < {lt}"
        )
    return num


def _warn_tls_path(path_str: str, field_name: str) -> str:
    """Log warning if TLS file does not exist (non-blocking)."""
    if path_str and not Path(path_str).exists():
        _config_logger.warning("%s: file not found: %s", field_name, path_str)
    return path_str


def _validate_tls_path(path_str: str, field_name: str) -> str:
    """Raise error if TLS file does not exist."""
    if path_str and not Path(path_str).exists():
        raise ConfigValidationError(
            f"{field_name}: file not found: {path_str}"
        )
    return path_str


# ============================================
# Enumerations
# ============================================

class ContentType(str, Enum):
    """Supported content types for IEEE 2030.5."""
    SEP_XML = "application/sep+xml"
    SEP_EXI = "application/sep-exi"


class ModbusMode(str, Enum):
    """Modbus connection modes."""
    TCP = "tcp"
    RTU = "rtu"


class ParseFormat(str, Enum):
    """Supported parse formats."""
    SEP_XML = "sep_xml"
    SEP_EXI = "sep_exi"
    JSON = "json"


class ModbusDataType(str, Enum):
    """Modbus register data types."""
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    FLOAT32 = "float32"


# ============================================
# Profile Configuration
# ============================================

@dataclass
class TLSConfig:
    """TLS client configuration for mTLS connections."""
    client_cert_path: str = "certs/client.crt"
    client_key_path: str = "certs/client.key"
    ca_bundle_path: str = "certs/ca.crt"
    verify_server: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TLSConfig":
        """Create from dictionary."""
        instance = cls(
            client_cert_path=data.get("client_cert_path", cls.client_cert_path),
            client_key_path=data.get("client_key_path", cls.client_key_path),
            ca_bundle_path=data.get("ca_bundle_path", cls.ca_bundle_path),
            verify_server=data.get("verify_server", cls.verify_server),
        )
        _warn_tls_path(instance.client_cert_path, "tls.client_cert_path")
        _warn_tls_path(instance.client_key_path, "tls.client_key_path")
        _warn_tls_path(instance.ca_bundle_path, "tls.ca_bundle_path")
        return instance


@dataclass
class ProfileConfig:
    """IEEE 2030.5 server profile configuration."""
    name: str = "default"
    server_base_url: str = "https://localhost:7443"
    tls: TLSConfig = field(default_factory=TLSConfig)
    content_type_preference: str = ContentType.SEP_XML.value
    device_id: str = "bms-client-001"
    pin: int = 12345

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProfileConfig":
        """Create from dictionary."""
        tls_data = data.get("tls", {})
        server_base_url = data.get("server_base_url", cls.server_base_url)
        content_type = data.get("content_type_preference", ContentType.SEP_XML.value)
        _validate_url(server_base_url, "profile.server_base_url")
        _validate_enum(content_type, ContentType, "profile.content_type_preference")
        return cls(
            name=data.get("name", "default"),
            server_base_url=server_base_url,
            tls=TLSConfig.from_dict(tls_data) if tls_data else TLSConfig(),
            content_type_preference=content_type,
            device_id=data.get("device_id", cls.device_id),
            pin=_validate_type(data.get("pin", cls.pin), int, "profile.pin"),
        )


# ============================================
# Modbus Configuration
# ============================================

@dataclass
class ModbusDefaults:
    """Default Modbus function codes."""
    function_code_read: int = 3   # 0x03 Read Holding Registers
    function_code_write: int = 6  # 0x06 Write Single Register

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModbusDefaults":
        """Create from dictionary."""
        return cls(
            function_code_read=data.get("function_code_read", cls.function_code_read),
            function_code_write=data.get("function_code_write", cls.function_code_write),
        )


@dataclass
class RegisterSystemConfig:
    """System register configuration."""
    base_address: int = 3999  # Doc: 4000
    count: int = 100

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegisterSystemConfig":
        """Create from dictionary."""
        return cls(
            base_address=data.get("base_address", cls.base_address),
            count=data.get("count", cls.count),
        )


@dataclass
class RegisterRackConfig:
    """Rack register configuration."""
    base_address: int = 6999  # Doc: 7000
    offset: int = 30
    max_racks: int = 24

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegisterRackConfig":
        """Create from dictionary."""
        return cls(
            base_address=data.get("base_address", cls.base_address),
            offset=data.get("offset", cls.offset),
            max_racks=data.get("max_racks", cls.max_racks),
        )


@dataclass
class RegistersConfig:
    """Register configuration."""
    system: RegisterSystemConfig = field(default_factory=RegisterSystemConfig)
    rack: RegisterRackConfig = field(default_factory=RegisterRackConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistersConfig":
        """Create from dictionary."""
        return cls(
            system=RegisterSystemConfig.from_dict(data.get("system", {})),
            rack=RegisterRackConfig.from_dict(data.get("rack", {})),
        )


@dataclass
class ModbusConfig:
    """Modbus BMS communication configuration."""
    mode: str = ModbusMode.TCP.value
    host: str = "192.168.1.187"
    port: int = 502
    unit_id: int = 1
    timeout: float = 5.0
    defaults: ModbusDefaults = field(default_factory=ModbusDefaults)
    rack_count: int = 4
    registers: RegistersConfig = field(default_factory=RegistersConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModbusConfig":
        """Create from dictionary."""
        mode = data.get("mode", cls.mode)
        _validate_enum(mode, ModbusMode, "modbus.mode")
        return cls(
            mode=mode,
            host=data.get("host", cls.host),
            port=_validate_port(data.get("port", cls.port), "modbus.port"),
            unit_id=_validate_type(data.get("unit_id", cls.unit_id), int, "modbus.unit_id"),
            timeout=_validate_positive(data.get("timeout", cls.timeout), "modbus.timeout"),
            defaults=ModbusDefaults.from_dict(data.get("defaults", {})),
            rack_count=_validate_type(data.get("rack_count", cls.rack_count), int, "modbus.rack_count"),
            registers=RegistersConfig.from_dict(data.get("registers", {})),
        )


# ============================================
# Poll Target Configuration
# ============================================

@dataclass
class ParseConfig:
    """Response parsing configuration."""
    format: str = ParseFormat.SEP_XML.value
    xpath: Optional[str] = None
    field_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParseConfig":
        """Create from dictionary."""
        fmt = data.get("format", cls.format)
        _validate_enum(fmt, ParseFormat, "parse.format")
        return cls(
            format=fmt,
            xpath=data.get("xpath"),
            field_path=data.get("field_path"),
        )


@dataclass
class TransformConfig:
    """Value transformation configuration."""
    scale: float = 1.0
    offset: float = 0.0
    clamp_min: Optional[float] = None
    clamp_max: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransformConfig":
        """Create from dictionary."""
        return cls(
            scale=data.get("scale", cls.scale),
            offset=data.get("offset", cls.offset),
            clamp_min=data.get("clamp_min"),
            clamp_max=data.get("clamp_max"),
        )

    def apply(self, value: float) -> float:
        """Apply transformation to a value."""
        result = (value * self.scale) + self.offset
        if self.clamp_min is not None:
            result = max(result, self.clamp_min)
        if self.clamp_max is not None:
            result = min(result, self.clamp_max)
        return result


@dataclass
class ModbusWriteConfig:
    """Modbus write configuration."""
    address: int = 0
    datatype: str = ModbusDataType.INT16.value
    scale: float = 1.0
    offset: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModbusWriteConfig":
        """Create from dictionary."""
        datatype = data.get("datatype", cls.datatype)
        _validate_enum(datatype, ModbusDataType, "modbus_write.datatype")
        return cls(
            address=_validate_type(data.get("address", cls.address), int, "modbus_write.address"),
            datatype=datatype,
            scale=_validate_type(data.get("scale", cls.scale), float, "modbus_write.scale"),
            offset=_validate_type(data.get("offset", cls.offset), float, "modbus_write.offset"),
        )

    def convert_value(self, value: float) -> int:
        """Convert value for Modbus register."""
        return int((value + self.offset) * self.scale)


@dataclass
class PollTargetConfig:
    """Poll target configuration."""
    id: str = ""
    name: str = ""
    enabled: bool = True
    profile_name: str = "default"
    method: str = "GET"
    uri: str = ""
    interval_ms: int = 60000
    parse: ParseConfig = field(default_factory=ParseConfig)
    transform: TransformConfig = field(default_factory=TransformConfig)
    modbus_write: Optional[ModbusWriteConfig] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PollTargetConfig":
        """Create from dictionary."""
        modbus_write_data = data.get("modbus_write")
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            profile_name=data.get("profile_name", "default"),
            method=data.get("method", "GET"),
            uri=data.get("uri", ""),
            interval_ms=data.get("interval_ms", 60000),
            parse=ParseConfig.from_dict(data.get("parse", {})),
            transform=TransformConfig.from_dict(data.get("transform", {})),
            modbus_write=ModbusWriteConfig.from_dict(modbus_write_data) if modbus_write_data else None,
        )


# ============================================
# Subscription Configuration
# ============================================

@dataclass
class SubscriptionConditions:
    """Subscription notification conditions."""
    lower_threshold: Optional[float] = None
    upper_threshold: Optional[float] = None
    attribute_identifier: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["SubscriptionConditions"]:
        """Create from dictionary."""
        if data is None:
            return None
        return cls(
            lower_threshold=data.get("lower_threshold"),
            upper_threshold=data.get("upper_threshold"),
            attribute_identifier=data.get("attribute_identifier"),
        )


@dataclass
class SubscriptionConfig:
    """Subscription configuration for push-based notifications."""
    id: str = ""
    name: str = ""
    enabled: bool = True
    profile_name: str = "default"
    resource_uri: str = ""
    notification_endpoint: str = ""
    conditions: Optional[SubscriptionConditions] = None
    renew_interval_hours: int = 24
    parse: ParseConfig = field(default_factory=ParseConfig)
    modbus_write: Optional[ModbusWriteConfig] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubscriptionConfig":
        """Create from dictionary."""
        modbus_write_data = data.get("modbus_write")
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            profile_name=data.get("profile_name", "default"),
            resource_uri=data.get("resource_uri", ""),
            notification_endpoint=data.get("notification_endpoint", ""),
            conditions=SubscriptionConditions.from_dict(data.get("conditions")),
            renew_interval_hours=data.get("renew_interval_hours", 24),
            parse=ParseConfig.from_dict(data.get("parse", {})),
            modbus_write=ModbusWriteConfig.from_dict(modbus_write_data) if modbus_write_data else None,
        )


# ============================================
# Notification Server Configuration
# ============================================

@dataclass
class NotificationServerConfig:
    """Client-side notification server configuration."""
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 8443
    tls_server_enabled: bool = True
    tls_server_cert_path: str = "certs/server.crt"
    tls_server_key_path: str = "certs/server.key"
    tls_require_client_cert: bool = False
    tls_client_ca_path: str = "certs/server_ca.crt"
    endpoint_path: str = "/notify"
    public_uri: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationServerConfig":
        """Create from dictionary."""
        enabled = data.get("enabled", cls.enabled)
        tls_enabled = data.get("tls_server_enabled", cls.tls_server_enabled)
        cert_path = data.get("tls_server_cert_path", cls.tls_server_cert_path)
        key_path = data.get("tls_server_key_path", cls.tls_server_key_path)
        ca_path = data.get("tls_client_ca_path", cls.tls_client_ca_path)
        instance = cls(
            enabled=enabled,
            listen_host=data.get("listen_host", cls.listen_host),
            listen_port=_validate_port(
                data.get("listen_port", cls.listen_port),
                "notification_server.listen_port",
            ),
            tls_server_enabled=tls_enabled,
            tls_server_cert_path=cert_path,
            tls_server_key_path=key_path,
            tls_require_client_cert=data.get("tls_require_client_cert", cls.tls_require_client_cert),
            tls_client_ca_path=ca_path,
            endpoint_path=data.get("endpoint_path", cls.endpoint_path),
            public_uri=data.get("public_uri", cls.public_uri),
        )
        if enabled and tls_enabled:
            _warn_tls_path(cert_path, "notification_server.tls_server_cert_path")
            _warn_tls_path(key_path, "notification_server.tls_server_key_path")
        else:
            _warn_tls_path(cert_path, "notification_server.tls_server_cert_path")
            _warn_tls_path(key_path, "notification_server.tls_server_key_path")
        return instance


# ============================================
# Power Control Configuration
# ============================================

class PowerControlMode(str, Enum):
    """Power control operational mode."""
    SIMULATION = "simulation"   # Log only, no Modbus writes
    DRY_RUN = "dry_run"         # Full validation, no actual write
    PRODUCTION = "production"   # Actually write to PCS


@dataclass
class PCSModbusConfig:
    """PCS Modbus TCP connection settings (may differ from BMS)."""
    host: str = "mainline.proxy.rlwy.net"
    port: int = 30623
    unit_id: int = 1
    timeout: float = 5.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PCSModbusConfig":
        """Create from dictionary."""
        return cls(
            host=data.get("host", cls.host),
            port=_validate_port(data.get("port", cls.port), "pcs_modbus.port"),
            unit_id=_validate_type(data.get("unit_id", cls.unit_id), int, "pcs_modbus.unit_id"),
            timeout=_validate_positive(data.get("timeout", cls.timeout), "pcs_modbus.timeout"),
        )


@dataclass
class PCSRegistersConfig:
    """PCS Modbus register addresses."""
    power_setpoint: int = 40001
    power_setpoint_high: int = 40002
    operation_mode: int = 40010
    enable_control: int = 40011
    actual_power: int = 40100
    operation_status: int = 40101
    error_code: int = 40102

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PCSRegistersConfig":
        """Create from dictionary."""
        return cls(
            power_setpoint=data.get("power_setpoint", cls.power_setpoint),
            power_setpoint_high=data.get("power_setpoint_high", cls.power_setpoint_high),
            operation_mode=data.get("operation_mode", cls.operation_mode),
            enable_control=data.get("enable_control", cls.enable_control),
            actual_power=data.get("actual_power", cls.actual_power),
            operation_status=data.get("operation_status", cls.operation_status),
            error_code=data.get("error_code", cls.error_code),
        )


_MAX_POWER_W = 10_000_000  # 10 MW — sanity guard for any equipment type


@dataclass
class PowerLimitsConfig:
    """Power safety limits (enforced in ALL modes)."""
    max_charge_w: int = 3000
    max_discharge_w: int = 3000
    ramp_rate_w_per_s: int = 3000
    min_soc_percent: float = 10.0
    max_soc_percent: float = 90.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PowerLimitsConfig":
        """Create from dictionary."""
        min_soc = _validate_range(
            data.get("min_soc_percent", cls.min_soc_percent),
            "limits.min_soc_percent", expected_type=float, ge=0.0, le=100.0,
        )
        max_soc = _validate_range(
            data.get("max_soc_percent", cls.max_soc_percent),
            "limits.max_soc_percent", expected_type=float, ge=0.0, le=100.0,
        )
        if min_soc >= max_soc:
            raise ConfigValidationError(
                f"limits.min_soc_percent ({min_soc}) must be less than "
                f"limits.max_soc_percent ({max_soc})"
            )
        return cls(
            max_charge_w=_validate_range(
                data.get("max_charge_w", cls.max_charge_w),
                "limits.max_charge_w", ge=0, le=_MAX_POWER_W,
            ),
            max_discharge_w=_validate_range(
                data.get("max_discharge_w", cls.max_discharge_w),
                "limits.max_discharge_w", ge=0, le=_MAX_POWER_W,
            ),
            ramp_rate_w_per_s=_validate_range(
                data.get("ramp_rate_w_per_s", cls.ramp_rate_w_per_s),
                "limits.ramp_rate_w_per_s", ge=1, le=_MAX_POWER_W,
            ),
            min_soc_percent=min_soc,
            max_soc_percent=max_soc,
        )


@dataclass
class ProductionAuthConfig:
    """Production mode authorization settings."""
    safety_token: str = ""
    confirm_production: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProductionAuthConfig":
        """Create from dictionary."""
        return cls(
            safety_token=data.get("safety_token", ""),
            confirm_production=data.get("confirm_production", False),
        )


@dataclass
class PowerControlConfig:
    """Complete power control configuration."""
    mode: str = PowerControlMode.SIMULATION.value
    pcs_modbus: PCSModbusConfig = field(default_factory=PCSModbusConfig)
    registers: PCSRegistersConfig = field(default_factory=PCSRegistersConfig)
    datatype: str = "uint16"
    power_scale_factor: float = 1.0
    use_32bit: bool = False
    verify_after_write: bool = True
    limits: PowerLimitsConfig = field(default_factory=PowerLimitsConfig)
    production_auth: ProductionAuthConfig = field(default_factory=ProductionAuthConfig)

    @property
    def is_simulation(self) -> bool:
        return self.mode == PowerControlMode.SIMULATION.value

    @property
    def is_dry_run(self) -> bool:
        return self.mode == PowerControlMode.DRY_RUN.value

    @property
    def is_production(self) -> bool:
        return self.mode == PowerControlMode.PRODUCTION.value

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PowerControlConfig":
        """Create from dictionary."""
        mode = data.get("mode", cls.mode)
        _validate_enum(mode, PowerControlMode, "power_control.mode")
        return cls(
            mode=mode,
            pcs_modbus=PCSModbusConfig.from_dict(data.get("pcs_modbus", {})),
            registers=PCSRegistersConfig.from_dict(data.get("registers", {})),
            datatype=data.get("datatype", cls.datatype),
            power_scale_factor=_validate_type(
                data.get("power_scale_factor", cls.power_scale_factor),
                float, "power_control.power_scale_factor",
            ),
            use_32bit=data.get("use_32bit", cls.use_32bit),
            verify_after_write=data.get("verify_after_write", cls.verify_after_write),
            limits=PowerLimitsConfig.from_dict(data.get("limits", {})),
            production_auth=ProductionAuthConfig.from_dict(data.get("production_auth", {})),
        )


# ============================================
# Logging Configuration
# ============================================

@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None
    buffer_size: int = 500
    max_bytes: int = 10 * 1024 * 1024  # 10 MB per log file
    backup_count: int = 5              # number of rotated files to keep

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoggingConfig":
        """Create from dictionary."""
        level = data.get("level", cls.level)
        level = _validate_log_level(level, "logging.level")
        return cls(
            level=level,
            format=data.get("format", cls.format),
            file=data.get("file"),
            buffer_size=_validate_type(data.get("buffer_size", cls.buffer_size), int, "logging.buffer_size"),
            max_bytes=_validate_type(data.get("max_bytes", cls.max_bytes), int, "logging.max_bytes"),
            backup_count=_validate_type(data.get("backup_count", cls.backup_count), int, "logging.backup_count"),
        )


# ============================================
# Main Runtime Configuration
# ============================================

_KNOWN_TOP_LEVEL_KEYS = {
    "profiles", "modbus", "poll_targets", "subscriptions",
    "notification_server", "power_control", "logging",
}


@dataclass
class RuntimeConfig:
    """
    Complete runtime configuration for BMS IEEE 2030.5 Client.
    
    This is the main configuration class that holds all settings.
    Load from YAML using RuntimeConfig.from_yaml().
    """
    profiles: List[ProfileConfig] = field(default_factory=list)
    modbus: ModbusConfig = field(default_factory=ModbusConfig)
    poll_targets: List[PollTargetConfig] = field(default_factory=list)
    subscriptions: List[SubscriptionConfig] = field(default_factory=list)
    notification_server: NotificationServerConfig = field(default_factory=NotificationServerConfig)
    power_control: PowerControlConfig = field(default_factory=PowerControlConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def get_profile(self, name: str) -> Optional[ProfileConfig]:
        """Get a profile by name."""
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def get_enabled_poll_targets(self) -> List[PollTargetConfig]:
        """Get all enabled poll targets."""
        return [t for t in self.poll_targets if t.enabled]

    def get_enabled_subscriptions(self) -> List[SubscriptionConfig]:
        """Get all enabled subscriptions."""
        return [s for s in self.subscriptions if s.enabled]

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "RuntimeConfig":
        """
        Load configuration from YAML file.
        
        Args:
            path: Path to YAML configuration file
            
        Returns:
            RuntimeConfig instance
            
        Raises:
            FileNotFoundError: If configuration file not found
            yaml.YAMLError: If YAML parsing fails
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeConfig":
        """Create from dictionary.

        Unknown top-level keys are logged as warnings and collected
        in the returned instance's ``config_warnings`` attribute.
        """
        warnings: List[str] = []
        unknown = set(data.keys()) - _KNOWN_TOP_LEVEL_KEYS
        if unknown:
            msg = (
                f"Unknown top-level config keys (ignored): "
                f"{sorted(unknown)}"
            )
            _config_logger.warning(msg)
            warnings.append(msg)

        profiles = [
            ProfileConfig.from_dict(p) for p in data.get("profiles", [])
        ]
        
        poll_targets = [
            PollTargetConfig.from_dict(t) for t in data.get("poll_targets", [])
        ]
        
        subscriptions = [
            SubscriptionConfig.from_dict(s) for s in data.get("subscriptions", [])
        ]

        instance = cls(
            profiles=profiles,
            modbus=ModbusConfig.from_dict(data.get("modbus", {})),
            poll_targets=poll_targets,
            subscriptions=subscriptions,
            notification_server=NotificationServerConfig.from_dict(
                data.get("notification_server", {})
            ),
            power_control=PowerControlConfig.from_dict(data.get("power_control", {})),
            logging=LoggingConfig.from_dict(data.get("logging", {})),
        )
        instance.config_warnings = warnings
        return instance

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "profiles": [
                {
                    "name": p.name,
                    "server_base_url": p.server_base_url,
                    "tls": {
                        "client_cert_path": p.tls.client_cert_path,
                        "client_key_path": p.tls.client_key_path,
                        "ca_bundle_path": p.tls.ca_bundle_path,
                        "verify_server": p.tls.verify_server,
                    },
                    "content_type_preference": p.content_type_preference,
                    "device_id": p.device_id,
                    "pin": p.pin,
                }
                for p in self.profiles
            ],
            "modbus": {
                "mode": self.modbus.mode,
                "host": self.modbus.host,
                "port": self.modbus.port,
                "unit_id": self.modbus.unit_id,
                "timeout": self.modbus.timeout,
                "defaults": {
                    "function_code_read": self.modbus.defaults.function_code_read,
                    "function_code_write": self.modbus.defaults.function_code_write,
                },
                "rack_count": self.modbus.rack_count,
                "registers": {
                    "system": {
                        "base_address": self.modbus.registers.system.base_address,
                        "count": self.modbus.registers.system.count,
                    },
                    "rack": {
                        "base_address": self.modbus.registers.rack.base_address,
                        "offset": self.modbus.registers.rack.offset,
                        "max_racks": self.modbus.registers.rack.max_racks,
                    },
                },
            },
            "poll_targets": [
                {
                    "id": t.id,
                    "name": t.name,
                    "enabled": t.enabled,
                    "profile_name": t.profile_name,
                    "method": t.method,
                    "uri": t.uri,
                    "interval_ms": t.interval_ms,
                    "parse": {
                        "format": t.parse.format,
                        "xpath": t.parse.xpath,
                        "field_path": t.parse.field_path,
                    },
                    "transform": {
                        "scale": t.transform.scale,
                        "offset": t.transform.offset,
                        "clamp_min": t.transform.clamp_min,
                        "clamp_max": t.transform.clamp_max,
                    },
                    "modbus_write": {
                        "address": t.modbus_write.address,
                        "datatype": t.modbus_write.datatype,
                        "scale": t.modbus_write.scale,
                        "offset": t.modbus_write.offset,
                    } if t.modbus_write else None,
                }
                for t in self.poll_targets
            ],
            "subscriptions": [
                {
                    "id": s.id,
                    "name": s.name,
                    "enabled": s.enabled,
                    "profile_name": s.profile_name,
                    "resource_uri": s.resource_uri,
                    "notification_endpoint": s.notification_endpoint,
                    "conditions": {
                        "lower_threshold": s.conditions.lower_threshold,
                        "upper_threshold": s.conditions.upper_threshold,
                        "attribute_identifier": s.conditions.attribute_identifier,
                    } if s.conditions else None,
                    "renew_interval_hours": s.renew_interval_hours,
                    "parse": {
                        "format": s.parse.format,
                        "xpath": s.parse.xpath,
                        "field_path": s.parse.field_path,
                    },
                    "modbus_write": {
                        "address": s.modbus_write.address,
                        "datatype": s.modbus_write.datatype,
                        "scale": s.modbus_write.scale,
                        "offset": s.modbus_write.offset,
                    } if s.modbus_write else None,
                }
                for s in self.subscriptions
            ],
            "notification_server": {
                "enabled": self.notification_server.enabled,
                "listen_host": self.notification_server.listen_host,
                "listen_port": self.notification_server.listen_port,
                "tls_server_enabled": self.notification_server.tls_server_enabled,
                "tls_server_cert_path": self.notification_server.tls_server_cert_path,
                "tls_server_key_path": self.notification_server.tls_server_key_path,
                "tls_require_client_cert": self.notification_server.tls_require_client_cert,
                "tls_client_ca_path": self.notification_server.tls_client_ca_path,
                "endpoint_path": self.notification_server.endpoint_path,
                "public_uri": self.notification_server.public_uri,
            },
            "power_control": {
                "mode": self.power_control.mode,
                "pcs_modbus": {
                    "host": self.power_control.pcs_modbus.host,
                    "port": self.power_control.pcs_modbus.port,
                    "unit_id": self.power_control.pcs_modbus.unit_id,
                    "timeout": self.power_control.pcs_modbus.timeout,
                },
                "registers": {
                    "power_setpoint": self.power_control.registers.power_setpoint,
                    "power_setpoint_high": self.power_control.registers.power_setpoint_high,
                    "operation_mode": self.power_control.registers.operation_mode,
                    "enable_control": self.power_control.registers.enable_control,
                    "actual_power": self.power_control.registers.actual_power,
                    "operation_status": self.power_control.registers.operation_status,
                    "error_code": self.power_control.registers.error_code,
                },
                "datatype": self.power_control.datatype,
                "power_scale_factor": self.power_control.power_scale_factor,
                "use_32bit": self.power_control.use_32bit,
                "verify_after_write": self.power_control.verify_after_write,
                "limits": {
                    "max_charge_w": self.power_control.limits.max_charge_w,
                    "max_discharge_w": self.power_control.limits.max_discharge_w,
                    "ramp_rate_w_per_s": self.power_control.limits.ramp_rate_w_per_s,
                    "min_soc_percent": self.power_control.limits.min_soc_percent,
                    "max_soc_percent": self.power_control.limits.max_soc_percent,
                },
                "production_auth": {
                    "safety_token": self.power_control.production_auth.safety_token,
                    "confirm_production": self.power_control.production_auth.confirm_production,
                },
            },
            "logging": {
                "level": self.logging.level,
                "format": self.logging.format,
                "file": self.logging.file,
                "buffer_size": self.logging.buffer_size,
            },
        }

    def to_yaml(self, path: Union[str, Path]) -> None:
        """
        Save configuration to YAML file.
        
        Args:
            path: Path to save YAML file
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.to_dict(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )


# ============================================
# Backward Compatibility with Legacy Config
# ============================================

def runtime_to_legacy_config(runtime: RuntimeConfig) -> "Config":
    """
    Convert RuntimeConfig to legacy Config for backward compatibility.
    
    This allows existing code using the old Config class to work
    with the new RuntimeConfig schema.
    """
    from bms_2030_5_client.config import (
        Config,
        IEEE2030_5Config,
        ModbusConfig as LegacyModbusConfig,
        RegisterConfig,
        LoggingConfig as LegacyLoggingConfig,
        SubscriptionConfig as LegacySubscriptionConfig,
    )
    
    # Get the first profile (or use defaults)
    profile = runtime.profiles[0] if runtime.profiles else ProfileConfig()
    
    return Config(
        ieee2030_5=IEEE2030_5Config(
            server_url=profile.server_base_url,
            dcap_path="/dcap",
            cert_file=profile.tls.client_cert_path,
            key_file=profile.tls.client_key_path,
            ca_file=profile.tls.ca_bundle_path,
            device_id=profile.device_id,
            pin=profile.pin,
        ),
        modbus=LegacyModbusConfig(
            host=runtime.modbus.host,
            port=runtime.modbus.port,
            unit_id=runtime.modbus.unit_id,
            timeout=runtime.modbus.timeout,
            rack_count=runtime.modbus.rack_count,
        ),
        registers=RegisterConfig(
            system_base_address=runtime.modbus.registers.system.base_address,
            system_count=runtime.modbus.registers.system.count,
            rack_base_address=runtime.modbus.registers.rack.base_address,
            rack_offset=runtime.modbus.registers.rack.offset,
            max_racks=runtime.modbus.registers.rack.max_racks,
        ),
        logging=LegacyLoggingConfig(
            level=runtime.logging.level,
            format=runtime.logging.format,
            file=runtime.logging.file,
        ),
        subscription=LegacySubscriptionConfig(
            enabled=runtime.notification_server.enabled,
            notification_host=runtime.notification_server.listen_host,
            notification_port=runtime.notification_server.listen_port,
            public_uri=runtime.notification_server.public_uri,
        ),
    )
