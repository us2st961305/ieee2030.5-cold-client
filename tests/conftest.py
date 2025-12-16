"""
Pytest fixtures for BMS Client tests.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from bms_2030_5_client.config import Config
from bms_2030_5_client.models import RackData, SystemData, BMSSnapshot, RackStatus


@pytest.fixture
def sample_config():
    """Create sample configuration."""
    return Config()


@pytest.fixture
def sample_rack_registers():
    """Sample Modbus registers for a rack (7000-7029)."""
    return [
        7500,   # 7000: rack_vol (750.0V)
        100,    # 7001: rack_current (10.0A charging)
        850,    # 7002: SOC (85.0%)
        3650,   # 7003: cell_max_v (3.650V)
        3580,   # 7004: cell_min_v (3.580V)
        28,     # 7005: cell_max_t (28°C)
        24,     # 7006: cell_min_t (24°C)
        5,      # 7007: tag_max_v (cell 5)
        12,     # 7008: tag_min_v (cell 12)
        3,      # 7009: tag_max_t (cell 3)
        8,      # 7010: tag_min_t (cell 8)
        15000,  # 7011: RM (150.00 AH)
        18000,  # 7012: FCC (180.00 AH)
        0,      # 7013: rack_power high (0)
        75000,  # 7014: rack_power low (7500.0W)
        150,    # 7015: cycle_count
        2,      # 7016: rack_status (CHARGING)
        0,      # 7017: alarm_status (no alarms)
        980,    # 7018: soh (98.0%)
        500,    # 7019: max_charge_current (50.0A)
        600,    # 7020: max_discharge_current (60.0A)
        8000,   # 7021: max_charge_voltage (800.0V)
        6000,   # 7022: min_discharge_voltage (600.0V)
        0, 0, 0, 0, 0, 0, 0,  # Reserved registers
    ]


@pytest.fixture
def sample_system_registers():
    """Sample Modbus registers for system data (4000-4034)."""
    return [
        1,      # 4000: system_status
        0,      # 4001: total_voltage high
        30000,  # 4002: total_voltage low (3000.0V)
        0,      # 4003: total_current high
        400,    # 4004: total_current low (40.0A)
        850,    # 4005: total_soc (85.0%)
        0,      # 4006: total_power high
        1200,   # 4007: total_power low (120.0 kW)
        1,      # 4008: pcs_status
        1,      # 4009: bms_mode
        4,      # 4010: active_rack_count
        0x000F, # 4011: rack_enable_status (racks 0-3 enabled)
        0,      # 4012-4034: reserved
    ] + [0] * 22


@pytest.fixture
def sample_rack_data():
    """Create sample RackData."""
    return RackData(
        rack_id=0,
        voltage=750.0,
        current=10.0,
        soc=85.0,
        cell_max_voltage=3.65,
        cell_min_voltage=3.58,
        cell_max_temp=28.0,
        cell_min_temp=24.0,
        tag_max_v=5,
        tag_min_v=12,
        tag_max_t=3,
        tag_min_t=8,
        remaining_capacity=150.0,
        full_charge_capacity=180.0,
        power=7500.0,
        cycle_count=150,
        status=RackStatus.CHARGING,
        alarm_status=0,
        soh=98.0,
        max_charge_current=50.0,
        max_discharge_current=60.0,
        max_charge_voltage=800.0,
        min_discharge_voltage=600.0,
    )


@pytest.fixture
def sample_system_data():
    """Create sample SystemData."""
    return SystemData(
        system_status=1,
        total_voltage=3000.0,
        total_current=40.0,
        total_soc=85.0,
        total_power=120.0,
        pcs_status=1,
        bms_mode=1,
        active_rack_count=4,
        rack_enable_status=[True, True, True, True] + [False] * 20,
    )


@pytest.fixture
def sample_snapshot(sample_system_data, sample_rack_data):
    """Create sample BMSSnapshot."""
    racks = [
        RackData(
            rack_id=i,
            voltage=750.0 + i,
            current=10.0 if i % 2 == 0 else -10.0,
            soc=85.0 - i,
            cell_max_voltage=3.65,
            cell_min_voltage=3.58,
            cell_max_temp=28.0,
            cell_min_temp=24.0,
            tag_max_v=5,
            tag_min_v=12,
            tag_max_t=3,
            tag_min_t=8,
            remaining_capacity=150.0,
            full_charge_capacity=180.0,
            status=RackStatus.CHARGING if i % 2 == 0 else RackStatus.DISCHARGING,
            max_charge_current=50.0,
            max_discharge_current=60.0,
            max_charge_voltage=800.0,
            min_discharge_voltage=600.0,
        )
        for i in range(4)
    ]
    return BMSSnapshot(system=sample_system_data, racks=racks)


@pytest.fixture
def mock_modbus_client():
    """Create mock Modbus client."""
    client = AsyncMock()
    client.connected = True
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def mock_ieee2030_5_client():
    """Create mock IEEE 2030.5 client."""
    client = AsyncMock()
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.lfdi = "ABCD1234567890ABCD1234567890ABCD12345678"
    client.sfdi = 12345678901
    return client
