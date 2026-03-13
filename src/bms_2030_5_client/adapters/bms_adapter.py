"""
BMS to IEEE 2030.5 data adapter.

Transforms CUBE BMS data to IEEE 2030.5 DER models.
This adapter now delegates to specialized modules for better organization.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from bms_2030_5_client.models import (
    # BMS models
    RackData,
    RackStatus,
    SystemData,
    BMSSnapshot,
    # IEEE 2030.5 models
    DERStatus,
    DERAvailability,
    DERSettings,
    DERCapability,
    DERType,
    ActivePower,
    ReactivePower,
    Voltage,
    Current,
    StateOfCharge,
    ConnectStatusType,
    OperationalModeStatusType,
    ConnectStatusValue,
    OperationalModeStatusValue,
    # Metering models
    MirrorUsagePoint,
    MirrorMeterReading,
)

# Import specialized adapters
from bms_2030_5_client.ders import DERStatusAdapter, modbus_error_to_alarm_status
from bms_2030_5_client.dera import DERAvailabilityAdapter
from bms_2030_5_client.mup import MirrorUsagePointAdapter

logger = logging.getLogger(__name__)


class BMSAdapter:
    """
    Adapter to convert BMS data to IEEE 2030.5 DER models.
    
    Maps CUBE battery rack data to IEEE 2030.5 DERStatus,
    DERAvailability, and other DER resources.
    
    This adapter now delegates to specialized modules:
    - DERStatusAdapter for DER status conversion
    - DERAvailabilityAdapter for DER availability conversion  
    - MirrorUsagePointAdapter for meter reading conversion
    """

    def __init__(
        self,
        nominal_voltage: float = 750.0,  # V
        max_power: float = 100000.0,  # W (100 kW)
        max_current: float = 150.0,  # A
    ):
        """
        Initialize adapter with system ratings.
        
        Args:
            nominal_voltage: Nominal system voltage in V
            max_power: Maximum power rating in W
            max_current: Maximum current rating in A
        """
        self.nominal_voltage = nominal_voltage
        self.max_power = max_power
        self.max_current = max_current
        
        # Initialize specialized adapters
        self._ders_adapter = DERStatusAdapter()
        self._dera_adapter = DERAvailabilityAdapter(max_power=max_power)
        self._mup_adapter = MirrorUsagePointAdapter()

    def _to_active_power(self, watts: float) -> ActivePower:
        """Convert watts to ActivePower with appropriate multiplier."""
        # Use multiplier for scaling
        if abs(watts) >= 1000000:
            return ActivePower(multiplier=6, value=int(watts / 1000000))
        elif abs(watts) >= 1000:
            return ActivePower(multiplier=3, value=int(watts / 1000))
        else:
            return ActivePower(multiplier=0, value=int(watts))

    def _to_voltage(self, volts: float) -> Voltage:
        """Convert volts to Voltage."""
        # Store as 0.1V units
        return Voltage(multiplier=-1, value=int(volts * 10))

    def _to_current(self, amps: float) -> Current:
        """Convert amps to Current."""
        # Store as 0.1A units
        return Current(multiplier=-1, value=int(amps * 10))

    def _to_soc(self, percent: float) -> StateOfCharge:
        """Convert percentage to StateOfCharge.
        
        Args:
            percent: SOC as percentage (0.0 - 100.0)
            
        Returns:
            StateOfCharge with value 0-10000 (0.00% - 100.00%)
        """
        # Clamp to valid range 0-100%
        clamped = max(0.0, min(100.0, percent))
        # Convert to IEEE 2030.5 format: 0-10000
        value = int(clamped * 100)
        return StateOfCharge(
            dateTime=int(datetime.now(timezone.utc).timestamp()),
            value=value
        )

    def snapshot_to_der_status(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERStatus:
        """
        Convert BMS snapshot to DERStatus.
        
        Delegates to DERStatusAdapter.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the status resource
            
        Returns:
            DERStatus object
        """
        return self._ders_adapter.snapshot_to_der_status(snapshot, href)

    def snapshot_to_der_availability(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERAvailability:
        """
        Convert BMS snapshot to DERAvailability.
        
        Delegates to DERAvailabilityAdapter.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the availability resource
            
        Returns:
            DERAvailability object
        """
        return self._dera_adapter.snapshot_to_der_availability(snapshot, href)

    def snapshot_to_der_settings(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERSettings:
        """
        Convert BMS snapshot to DERSettings.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the settings resource
            
        Returns:
            DERSettings object
        """
        # Get limits from active racks
        if snapshot.active_racks:
            max_charge_current = max(r.max_charge_current for r in snapshot.active_racks)
            max_discharge_current = max(r.max_discharge_current for r in snapshot.active_racks)
            max_voltage = max(r.max_charge_voltage for r in snapshot.active_racks)
            avg_voltage = sum(r.voltage for r in snapshot.active_racks) / len(snapshot.active_racks)
            
            max_charge_w = max_charge_current * avg_voltage
            max_discharge_w = max_discharge_current * avg_voltage
        else:
            max_charge_w = self.max_power
            max_discharge_w = self.max_power
            max_voltage = self.nominal_voltage

        return DERSettings(
            href=href,
            setMaxW=self._to_active_power(max_discharge_w),
            setMaxChargeRateW=self._to_active_power(max_charge_w),
            setMaxDischargeRateW=self._to_active_power(max_discharge_w),
            setVRef=self._to_voltage(self.nominal_voltage),
            updatedTime=int(datetime.now(timezone.utc).timestamp()),
        )

    def create_der_capability(
        self,
        href: Optional[str] = None,
    ) -> DERCapability:
        """
        Create DERCapability for the BMS.
        
        Args:
            href: Optional href for the capability resource
            
        Returns:
            DERCapability object
        """
        return DERCapability(
            href=href,
            modesSupported=0x0F,  # Support basic modes
            rtgMaxW=self._to_active_power(self.max_power),
            rtgMaxChargeRateW=self._to_active_power(self.max_power),
            rtgMaxDischargeRateW=self._to_active_power(self.max_power),
            rtgVNom=self._to_voltage(self.nominal_voltage),
            rtgAMax=self._to_current(self.max_current),
            type_=DERType.BATTERY_STORAGE,
        )

    def rack_to_der_status(
        self,
        rack: RackData,
        href: Optional[str] = None,
    ) -> DERStatus:
        """
        Convert single rack data to DERStatus.
        
        Args:
            rack: Single rack data
            href: Optional href
            
        Returns:
            DERStatus for the rack with alarmStatus from Modbus data
        """
        # Connection status
        connect_status = ConnectStatusType.CONNECTED
        if rack.status != RackStatus.OFFLINE:
            connect_status |= ConnectStatusType.AVAILABLE
        if rack.status in (RackStatus.CHARGING, RackStatus.DISCHARGING):
            connect_status |= ConnectStatusType.OPERATING
        if rack.status == RackStatus.FAULT or rack.alarm_status != 0:
            connect_status |= ConnectStatusType.FAULT

        # Operational mode - use OPERATING for active state
        if rack.status == RackStatus.STANDBY:
            op_mode = OperationalModeStatusType.OPERATING
        elif rack.status in (RackStatus.CHARGING, RackStatus.DISCHARGING):
            op_mode = OperationalModeStatusType.OPERATING
        else:
            op_mode = OperationalModeStatusType.OFF

        # Convert Modbus alarm status to IEEE 2030.5 format
        alarm_status = modbus_error_to_alarm_status(
            error_status=rack.alarm_status,
            rack_flag=0,  # Can be populated if CUBE 7020 register data is available
            lecu_flag=0,  # Can be populated if CUBE 7019 register data is available
        )

        ts = int(rack.timestamp.timestamp())

        return DERStatus(
            href=href,
            readingTime=ts,
            alarmStatus=f"{alarm_status:08X}",  # Simple hexBinary string
            genConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
            operationalModeStatus=OperationalModeStatusValue(dateTime=ts, value=f"{int(op_mode):02X}"),
            stateOfChargeStatus=self._to_soc(rack.soc),
            storConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
        )

    # =========================================================================
    # Metering / MirrorUsagePoint Conversion Methods
    # =========================================================================

    def create_bms_mirror_usage_point(
        self,
        device_lfdi: str,
        description: str = "BMS Battery Storage Meter",
        post_rate: int = 60,
        include_readings: bool = False,
        mup_mrid: str | None = None,
    ) -> MirrorUsagePoint:
        """
        Create a MirrorUsagePoint for the BMS system.
        
        Delegates to MirrorUsagePointAdapter.
        
        Args:
            device_lfdi: Device LFDI (Long-Form Device Identifier)
            description: Description of the meter
            post_rate: Posting rate in seconds
            include_readings: Whether to include MirrorMeterReading
            mup_mrid: Persisted mRID to reuse across restarts
            
        Returns:
            MirrorUsagePoint ready to register with server
        """
        return self._mup_adapter.create_mirror_usage_point(
            device_lfdi=device_lfdi,
            description=description,
            post_rate=post_rate,
            include_readings=include_readings,
            mup_mrid=mup_mrid,
        )

    def snapshot_to_meter_readings(
        self,
        snapshot: BMSSnapshot,
        reading_mrids: Optional[dict] = None,
        soh: Optional[float] = None,
        cycle_count: Optional[int] = None,
        include_reading_type: bool = False,
    ) -> List[MirrorMeterReading]:
        """
        Convert BMS snapshot to meter readings for upload.
        
        Delegates to MirrorUsagePointAdapter.
        
        Per IEEE 2030.5 spec, ReadingType SHOULD NOT be included in
        subsequent data updates after initial registration.
        
        Args:
            snapshot: BMS system snapshot
            reading_mrids: Optional dict mapping reading names to mRIDs
                          for updating existing readings
            soh: Optional SOH value (0-100%), if None calculates from active racks
            cycle_count: Optional cycle count value, if None uses 0
            include_reading_type: Whether to include ReadingType in readings.
                                  Should be False for periodic updates (default).
            
        Returns:
            List of MirrorMeterReading objects ready for upload
        """
        return self._mup_adapter.snapshot_to_meter_readings(
            snapshot, reading_mrids, soh=soh, cycle_count=cycle_count,
            include_reading_type=include_reading_type,
        )
