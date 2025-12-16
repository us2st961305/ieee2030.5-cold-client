"""
Tests for BMS data models.
"""

import pytest
from datetime import datetime

from bms_2030_5_client.models import RackData, SystemData, BMSSnapshot, RackStatus


class TestRackData:
    """Tests for RackData model."""

    def test_from_registers(self, sample_rack_registers):
        """Test creating RackData from Modbus registers."""
        rack = RackData.from_registers(0, sample_rack_registers)
        
        assert rack.rack_id == 0
        assert rack.voltage == 750.0
        assert rack.current == 10.0
        assert rack.soc == 85.0
        assert rack.cell_max_voltage == 3.650
        assert rack.cell_min_voltage == 3.580
        assert rack.cell_max_temp == 28
        assert rack.cell_min_temp == 24
        assert rack.status == RackStatus.CHARGING
        assert rack.soh == 98.0

    def test_cell_voltage_diff(self, sample_rack_data):
        """Test cell voltage difference calculation."""
        diff = sample_rack_data.cell_voltage_diff
        assert abs(diff - 0.07) < 0.001

    def test_is_charging(self, sample_rack_data):
        """Test charging detection."""
        assert sample_rack_data.is_charging is True
        assert sample_rack_data.is_discharging is False

    def test_from_registers_invalid_length(self):
        """Test error on insufficient register data."""
        with pytest.raises(ValueError):
            RackData.from_registers(0, [0] * 10)


class TestSystemData:
    """Tests for SystemData model."""

    def test_from_registers(self, sample_system_registers):
        """Test creating SystemData from Modbus registers."""
        system = SystemData.from_registers(sample_system_registers)
        
        assert system.system_status == 1
        assert system.total_voltage == 3000.0
        assert system.total_current == 40.0
        assert system.total_soc == 85.0
        assert system.active_rack_count == 4


class TestBMSSnapshot:
    """Tests for BMSSnapshot model."""

    def test_active_racks(self, sample_snapshot):
        """Test active racks filtering."""
        active = sample_snapshot.active_racks
        assert len(active) == 4

    def test_average_soc(self, sample_snapshot):
        """Test average SOC calculation."""
        avg_soc = sample_snapshot.average_soc
        # SOC values are 85, 84, 83, 82 = avg 83.5
        assert avg_soc == 83.5

    def test_has_alarms(self, sample_snapshot):
        """Test alarm detection."""
        assert sample_snapshot.has_alarms is False
