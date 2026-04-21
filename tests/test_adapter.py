"""
Tests for BMS to IEEE 2030.5 adapter.
"""

import pytest

from bms_2030_5_client.adapters import BMSAdapter
from bms_2030_5_client.models import (
    RackStatus,
    ConnectStatusType,
    OperationalModeStatusType,
)


class TestBMSAdapter:
    """Tests for BMSAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return BMSAdapter(
            nominal_voltage=750.0,
            max_power=100000.0,
            max_current=150.0,
        )

    def test_snapshot_to_der_status(self, adapter, sample_snapshot):
        """Test converting snapshot to DERStatus."""
        status = adapter.snapshot_to_der_status(sample_snapshot)
        
        assert status.readingTime > 0
        assert status.stateOfChargeStatus is not None
        assert status.stateOfChargeStatus.value == 8500  # 85.0% * 100

    def test_snapshot_to_der_availability(self, adapter, sample_snapshot):
        """Test converting snapshot to DERAvailability."""
        availability = adapter.snapshot_to_der_availability(sample_snapshot)
        
        assert availability.readingTime > 0
        assert availability.statWAvail is not None

    def test_create_der_capability(self, adapter):
        """Test creating DERCapability."""
        capability = adapter.create_der_capability()
        
        assert capability.rtgMaxW is not None
        assert capability.rtgVNom is not None

    def test_rack_to_der_status_charging(self, adapter, sample_rack_data):
        """Test rack status when charging."""
        sample_rack_data.status = RackStatus.CHARGING
        sample_rack_data.current = 10.0
        
        status = adapter.rack_to_der_status(sample_rack_data)
        
        assert status.operationalModeStatus.value == f"{int(OperationalModeStatusType.OPERATING):02X}"

    def test_rack_to_der_status_discharging(self, adapter, sample_rack_data):
        """Test rack status when discharging."""
        sample_rack_data.status = RackStatus.DISCHARGING
        sample_rack_data.current = -10.0
        
        status = adapter.rack_to_der_status(sample_rack_data)
        
        assert status.operationalModeStatus.value == f"{int(OperationalModeStatusType.OPERATING):02X}"

    def test_rack_to_der_status_fault(self, adapter, sample_rack_data):
        """Test rack status with fault."""
        sample_rack_data.status = RackStatus.FAULT
        sample_rack_data.alarm_status = 1
        
        status = adapter.rack_to_der_status(sample_rack_data)
        
        assert int(status.genConnectStatus.value, 16) & ConnectStatusType.FAULT
