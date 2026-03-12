"""
Tests for runtime configuration validation.

Covers: Enum validation, port range, URL format, type coercion, TLS path checks.
"""

import pytest
from pathlib import Path

from bms_2030_5_client.runtime_config import (
    ConfigValidationError,
    ContentType,
    LoggingConfig,
    ModbusConfig,
    ModbusDataType,
    ModbusMode,
    ModbusWriteConfig,
    NotificationServerConfig,
    PCSModbusConfig,
    ParseConfig,
    ParseFormat,
    PowerControlConfig,
    PowerControlMode,
    PowerLimitsConfig,
    ProfileConfig,
    RuntimeConfig,
    TLSConfig,
)


# ============================================
# Enum Validation
# ============================================

class TestEnumValidation:
    """Verify that invalid enum values are rejected."""

    def test_modbus_mode_valid(self):
        cfg = ModbusConfig.from_dict({"mode": "tcp"})
        assert cfg.mode == "tcp"

    def test_modbus_mode_invalid(self):
        with pytest.raises(ConfigValidationError, match="modbus.mode"):
            ModbusConfig.from_dict({"mode": "invalid"})

    def test_modbus_mode_rtu(self):
        cfg = ModbusConfig.from_dict({"mode": "rtu"})
        assert cfg.mode == "rtu"

    def test_power_control_mode_valid(self):
        for mode in ("simulation", "dry_run", "production"):
            cfg = PowerControlConfig.from_dict({"mode": mode})
            assert cfg.mode == mode

    def test_power_control_mode_invalid(self):
        with pytest.raises(ConfigValidationError, match="power_control.mode"):
            PowerControlConfig.from_dict({"mode": "typo_mode"})

    def test_content_type_valid(self):
        cfg = ProfileConfig.from_dict({
            "server_base_url": "https://localhost:7443",
            "content_type_preference": "application/sep+xml",
        })
        assert cfg.content_type_preference == "application/sep+xml"

    def test_content_type_invalid(self):
        with pytest.raises(ConfigValidationError, match="content_type_preference"):
            ProfileConfig.from_dict({
                "server_base_url": "https://localhost:7443",
                "content_type_preference": "text/plain",
            })

    def test_parse_format_valid(self):
        cfg = ParseConfig.from_dict({"format": "sep_xml"})
        assert cfg.format == "sep_xml"

    def test_parse_format_invalid(self):
        with pytest.raises(ConfigValidationError, match="parse.format"):
            ParseConfig.from_dict({"format": "csv"})

    def test_modbus_datatype_valid(self):
        for dt in ("int16", "uint16", "int32", "uint32", "float32"):
            cfg = ModbusWriteConfig.from_dict({"datatype": dt})
            assert cfg.datatype == dt

    def test_modbus_datatype_invalid(self):
        with pytest.raises(ConfigValidationError, match="modbus_write.datatype"):
            ModbusWriteConfig.from_dict({"datatype": "string"})

    def test_logging_level_valid(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            cfg = LoggingConfig.from_dict({"level": level})
            assert cfg.level == level

    def test_logging_level_case_insensitive(self):
        cfg = LoggingConfig.from_dict({"level": "debug"})
        assert cfg.level == "DEBUG"

    def test_logging_level_invalid(self):
        with pytest.raises(ConfigValidationError, match="logging.level"):
            LoggingConfig.from_dict({"level": "VERBOSE"})


# ============================================
# Port Validation
# ============================================

class TestPortValidation:
    """Verify port numbers are in range 1-65535."""

    def test_modbus_port_valid(self):
        cfg = ModbusConfig.from_dict({"port": 502})
        assert cfg.port == 502

    def test_modbus_port_zero(self):
        with pytest.raises(ConfigValidationError, match="modbus.port"):
            ModbusConfig.from_dict({"port": 0})

    def test_modbus_port_negative(self):
        with pytest.raises(ConfigValidationError, match="modbus.port"):
            ModbusConfig.from_dict({"port": -1})

    def test_modbus_port_too_large(self):
        with pytest.raises(ConfigValidationError, match="modbus.port"):
            ModbusConfig.from_dict({"port": 999999})

    def test_modbus_port_boundary_1(self):
        cfg = ModbusConfig.from_dict({"port": 1})
        assert cfg.port == 1

    def test_modbus_port_boundary_65535(self):
        cfg = ModbusConfig.from_dict({"port": 65535})
        assert cfg.port == 65535

    def test_pcs_port_invalid(self):
        with pytest.raises(ConfigValidationError, match="pcs_modbus.port"):
            PCSModbusConfig.from_dict({"port": 0})

    def test_notification_port_invalid(self):
        with pytest.raises(ConfigValidationError, match="notification_server.listen_port"):
            NotificationServerConfig.from_dict({"listen_port": -1})

    def test_port_string_coercion(self):
        cfg = ModbusConfig.from_dict({"port": "502"})
        assert cfg.port == 502

    def test_port_string_invalid(self):
        with pytest.raises(ConfigValidationError, match="modbus.port"):
            ModbusConfig.from_dict({"port": "abc"})


# ============================================
# URL Validation
# ============================================

class TestURLValidation:
    """Verify server_base_url has valid scheme and host."""

    def test_https_url(self):
        cfg = ProfileConfig.from_dict({
            "server_base_url": "https://192.168.1.1:7443",
        })
        assert cfg.server_base_url == "https://192.168.1.1:7443"

    def test_http_url(self):
        cfg = ProfileConfig.from_dict({
            "server_base_url": "http://localhost:8080",
        })
        assert cfg.server_base_url == "http://localhost:8080"

    def test_invalid_scheme(self):
        with pytest.raises(ConfigValidationError, match="server_base_url"):
            ProfileConfig.from_dict({
                "server_base_url": "ftp://localhost",
            })

    def test_no_scheme(self):
        with pytest.raises(ConfigValidationError, match="server_base_url"):
            ProfileConfig.from_dict({
                "server_base_url": "localhost:7443",
            })

    def test_empty_url(self):
        with pytest.raises(ConfigValidationError, match="server_base_url"):
            ProfileConfig.from_dict({
                "server_base_url": "",
            })

    def test_random_string(self):
        with pytest.raises(ConfigValidationError, match="server_base_url"):
            ProfileConfig.from_dict({
                "server_base_url": "not-a-url",
            })


# ============================================
# Type Coercion & Validation
# ============================================

class TestTypeValidation:
    """Verify type coercion and rejection of incompatible types."""

    def test_port_string_to_int(self):
        cfg = ModbusConfig.from_dict({"port": "8080"})
        assert cfg.port == 8080
        assert isinstance(cfg.port, int)

    def test_timeout_string_to_float(self):
        cfg = ModbusConfig.from_dict({"timeout": "5.0"})
        assert cfg.timeout == 5.0

    def test_timeout_negative(self):
        with pytest.raises(ConfigValidationError, match="modbus.timeout"):
            ModbusConfig.from_dict({"timeout": -1.0})

    def test_timeout_zero(self):
        with pytest.raises(ConfigValidationError, match="modbus.timeout"):
            ModbusConfig.from_dict({"timeout": 0})

    def test_pcs_timeout_negative(self):
        with pytest.raises(ConfigValidationError, match="pcs_modbus.timeout"):
            PCSModbusConfig.from_dict({"timeout": -5.0})

    def test_unit_id_string(self):
        cfg = ModbusConfig.from_dict({"unit_id": "1"})
        assert cfg.unit_id == 1

    def test_unit_id_non_numeric(self):
        with pytest.raises(ConfigValidationError, match="modbus.unit_id"):
            ModbusConfig.from_dict({"unit_id": "abc"})

    def test_pin_string_to_int(self):
        cfg = ProfileConfig.from_dict({
            "server_base_url": "https://localhost:7443",
            "pin": "54321",
        })
        assert cfg.pin == 54321

    def test_logging_buffer_size_string(self):
        cfg = LoggingConfig.from_dict({"buffer_size": "1000"})
        assert cfg.buffer_size == 1000

    def test_modbus_write_address_string(self):
        cfg = ModbusWriteConfig.from_dict({"address": "100"})
        assert cfg.address == 100


# ============================================
# TLS Path Validation
# ============================================

class TestTLSPathValidation:
    """Verify TLS path existence checks."""

    def test_tls_config_warns_missing(self, caplog):
        """TLSConfig should warn but not raise for missing paths."""
        import logging
        with caplog.at_level(logging.WARNING):
            cfg = TLSConfig.from_dict({
                "client_cert_path": "/nonexistent/cert.pem",
                "client_key_path": "/nonexistent/key.pem",
                "ca_bundle_path": "/nonexistent/ca.pem",
            })
        assert cfg.client_cert_path == "/nonexistent/cert.pem"
        assert "file not found" in caplog.text

    def test_tls_config_existing_path(self, tmp_path):
        """TLSConfig should not warn for existing paths."""
        cert = tmp_path / "cert.pem"
        cert.write_text("cert")
        key = tmp_path / "key.pem"
        key.write_text("key")
        ca = tmp_path / "ca.pem"
        ca.write_text("ca")
        cfg = TLSConfig.from_dict({
            "client_cert_path": str(cert),
            "client_key_path": str(key),
            "ca_bundle_path": str(ca),
        })
        assert cfg.client_cert_path == str(cert)

    def test_notification_server_enabled_tls_missing_warns(self, caplog):
        """Enabled notification server with TLS should warn on missing certs."""
        import logging
        with caplog.at_level(logging.WARNING):
            cfg = NotificationServerConfig.from_dict({
                "enabled": True,
                "tls_server_enabled": True,
                "tls_server_cert_path": "/nonexistent/server.crt",
                "tls_server_key_path": "/nonexistent/server.key",
            })
        assert cfg.enabled is True
        assert "file not found" in caplog.text

    def test_notification_server_disabled_tls_warns(self, caplog):
        """Disabled notification server should only warn for missing TLS paths."""
        import logging
        with caplog.at_level(logging.WARNING):
            cfg = NotificationServerConfig.from_dict({
                "enabled": False,
                "tls_server_enabled": True,
                "tls_server_cert_path": "/nonexistent/server.crt",
                "tls_server_key_path": "/nonexistent/server.key",
            })
        assert cfg.tls_server_cert_path == "/nonexistent/server.crt"

    def test_notification_server_with_existing_tls(self, tmp_path):
        """Enabled notification server should pass with existing TLS files."""
        cert = tmp_path / "server.crt"
        cert.write_text("cert")
        key = tmp_path / "server.key"
        key.write_text("key")
        cfg = NotificationServerConfig.from_dict({
            "enabled": True,
            "tls_server_enabled": True,
            "tls_server_cert_path": str(cert),
            "tls_server_key_path": str(key),
        })
        assert cfg.enabled is True


# ============================================
# Power Limits Validation
# ============================================

class TestPowerLimitsValidation:
    """Verify safety boundary checks for power limits."""

    # --- max_charge_w ---
    def test_max_charge_w_valid(self):
        cfg = PowerLimitsConfig.from_dict({"max_charge_w": 5000})
        assert cfg.max_charge_w == 5000

    def test_max_charge_w_zero(self):
        cfg = PowerLimitsConfig.from_dict({"max_charge_w": 0})
        assert cfg.max_charge_w == 0

    def test_max_charge_w_negative(self):
        with pytest.raises(ConfigValidationError, match="max_charge_w"):
            PowerLimitsConfig.from_dict({"max_charge_w": -1})

    def test_max_charge_w_exceeds_10mw(self):
        with pytest.raises(ConfigValidationError, match="max_charge_w"):
            PowerLimitsConfig.from_dict({"max_charge_w": 10_000_001})

    def test_max_charge_w_at_10mw(self):
        cfg = PowerLimitsConfig.from_dict({"max_charge_w": 10_000_000})
        assert cfg.max_charge_w == 10_000_000

    # --- max_discharge_w ---
    def test_max_discharge_w_valid(self):
        cfg = PowerLimitsConfig.from_dict({"max_discharge_w": 100_000})
        assert cfg.max_discharge_w == 100_000

    def test_max_discharge_w_negative(self):
        with pytest.raises(ConfigValidationError, match="max_discharge_w"):
            PowerLimitsConfig.from_dict({"max_discharge_w": -500})

    def test_max_discharge_w_exceeds_10mw(self):
        with pytest.raises(ConfigValidationError, match="max_discharge_w"):
            PowerLimitsConfig.from_dict({"max_discharge_w": 99_999_999})

    # --- ramp_rate_w_per_s ---
    def test_ramp_rate_valid(self):
        cfg = PowerLimitsConfig.from_dict({"ramp_rate_w_per_s": 1000})
        assert cfg.ramp_rate_w_per_s == 1000

    def test_ramp_rate_min_1(self):
        cfg = PowerLimitsConfig.from_dict({"ramp_rate_w_per_s": 1})
        assert cfg.ramp_rate_w_per_s == 1

    def test_ramp_rate_zero(self):
        with pytest.raises(ConfigValidationError, match="ramp_rate_w_per_s"):
            PowerLimitsConfig.from_dict({"ramp_rate_w_per_s": 0})

    def test_ramp_rate_negative(self):
        with pytest.raises(ConfigValidationError, match="ramp_rate_w_per_s"):
            PowerLimitsConfig.from_dict({"ramp_rate_w_per_s": -100})

    def test_ramp_rate_exceeds_10mw(self):
        with pytest.raises(ConfigValidationError, match="ramp_rate_w_per_s"):
            PowerLimitsConfig.from_dict({"ramp_rate_w_per_s": 10_000_001})

    # --- min_soc_percent ---
    def test_min_soc_valid(self):
        cfg = PowerLimitsConfig.from_dict({"min_soc_percent": 20.0})
        assert cfg.min_soc_percent == 20.0

    def test_min_soc_zero(self):
        cfg = PowerLimitsConfig.from_dict({"min_soc_percent": 0.0})
        assert cfg.min_soc_percent == 0.0

    def test_min_soc_negative(self):
        with pytest.raises(ConfigValidationError, match="min_soc_percent"):
            PowerLimitsConfig.from_dict({"min_soc_percent": -1.0})

    def test_min_soc_over_100(self):
        with pytest.raises(ConfigValidationError, match="min_soc_percent"):
            PowerLimitsConfig.from_dict({"min_soc_percent": 150.0})

    # --- max_soc_percent ---
    def test_max_soc_valid(self):
        cfg = PowerLimitsConfig.from_dict({"max_soc_percent": 95.0})
        assert cfg.max_soc_percent == 95.0

    def test_max_soc_at_100(self):
        cfg = PowerLimitsConfig.from_dict({
            "min_soc_percent": 5.0, "max_soc_percent": 100.0,
        })
        assert cfg.max_soc_percent == 100.0

    def test_max_soc_negative(self):
        with pytest.raises(ConfigValidationError, match="max_soc_percent"):
            PowerLimitsConfig.from_dict({"max_soc_percent": -10.0})

    def test_max_soc_over_100(self):
        with pytest.raises(ConfigValidationError, match="max_soc_percent"):
            PowerLimitsConfig.from_dict({"max_soc_percent": 101.0})

    # --- cross-validation ---
    def test_min_soc_equals_max_soc(self):
        with pytest.raises(ConfigValidationError, match="must be less than"):
            PowerLimitsConfig.from_dict({
                "min_soc_percent": 50.0, "max_soc_percent": 50.0,
            })

    def test_min_soc_greater_than_max_soc(self):
        with pytest.raises(ConfigValidationError, match="must be less than"):
            PowerLimitsConfig.from_dict({
                "min_soc_percent": 90.0, "max_soc_percent": 10.0,
            })

    # --- type coercion ---
    def test_string_coercion(self):
        cfg = PowerLimitsConfig.from_dict({
            "max_charge_w": "5000", "max_discharge_w": "3000",
            "ramp_rate_w_per_s": "1000",
        })
        assert cfg.max_charge_w == 5000

    def test_string_invalid(self):
        with pytest.raises(ConfigValidationError, match="max_charge_w"):
            PowerLimitsConfig.from_dict({"max_charge_w": "abc"})

    # --- defaults ---
    def test_defaults(self):
        cfg = PowerLimitsConfig.from_dict({})
        assert cfg.max_charge_w == 3000
        assert cfg.max_discharge_w == 3000
        assert cfg.ramp_rate_w_per_s == 3000
        assert cfg.min_soc_percent == 10.0
        assert cfg.max_soc_percent == 90.0


# ============================================
# Default Values (regression)
# ============================================

class TestDefaultValues:
    """Verify defaults still work after validation is added."""

    def test_modbus_defaults(self):
        cfg = ModbusConfig.from_dict({})
        assert cfg.mode == "tcp"
        assert cfg.port == 502
        assert cfg.timeout == 5.0

    def test_power_control_defaults(self):
        cfg = PowerControlConfig.from_dict({})
        assert cfg.mode == "simulation"

    def test_logging_defaults(self):
        cfg = LoggingConfig.from_dict({})
        assert cfg.level == "INFO"

    def test_notification_server_defaults(self):
        cfg = NotificationServerConfig.from_dict({})
        assert cfg.listen_port == 8443
        assert cfg.enabled is False

    def test_full_runtime_config_defaults(self):
        cfg = RuntimeConfig.from_dict({})
        assert cfg.modbus.port == 502
        assert cfg.power_control.mode == "simulation"
        assert cfg.logging.level == "INFO"
