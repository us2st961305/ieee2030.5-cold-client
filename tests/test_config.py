"""
Tests for configuration module.
"""

import pytest
import tempfile
from pathlib import Path

from bms_2030_5_client.config import Config, IEEE2030_5Config, ModbusConfig


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        
        assert config.ieee2030_5.server_url == "https://localhost:7443"
        assert config.modbus.port == 502
        assert config.registers.rack_offset == 30

    def test_from_yaml(self, tmp_path):
        """Test loading configuration from YAML."""
        yaml_content = """
ieee2030_5:
  server_url: "https://192.168.1.1:7443"
  poll_rate: 60

modbus:
  host: "192.168.1.100"
  rack_count: 8
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml_content)
        
        config = Config.from_yaml(config_file)
        
        assert config.ieee2030_5.server_url == "https://192.168.1.1:7443"
        assert config.ieee2030_5.poll_rate == 60
        assert config.modbus.host == "192.168.1.100"
        assert config.modbus.rack_count == 8

    def test_to_yaml(self, tmp_path):
        """Test saving configuration to YAML."""
        config = Config()
        config.ieee2030_5.server_url = "https://test:7443"
        
        config_file = tmp_path / "output_config.yaml"
        config.to_yaml(config_file)
        
        # Reload and verify
        loaded = Config.from_yaml(config_file)
        assert loaded.ieee2030_5.server_url == "https://test:7443"

    def test_from_yaml_file_not_found(self):
        """Test error when config file not found."""
        with pytest.raises(FileNotFoundError):
            Config.from_yaml("/nonexistent/path/config.yaml")
