"""
BMS to IEEE 2030.5 data adapter.

Transforms CUBE BMS data to IEEE 2030.5 DER models.
"""

import logging
from datetime import datetime
from typing import Optional

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
)

logger = logging.getLogger(__name__)


class BMSAdapter:
    """
    Adapter to convert BMS data to IEEE 2030.5 DER models.
    
    Maps CUBE battery rack data to IEEE 2030.5 DERStatus,
    DERAvailability, and other DER resources.
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
        """Convert percentage to StateOfCharge (0-10000)."""
    def _to_soc(self, percent: float) -> StateOfCharge:
        """Convert percentage to StateOfCharge."""
        return StateOfCharge(
            dateTime=int(datetime.now().timestamp()),
            value=int(percent * 100)
        )

    def snapshot_to_der_status(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERStatus:
        """
        Convert BMS snapshot to DERStatus.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the status resource
            
        Returns:
            DERStatus object
        """
        # Determine connection status
        connect_status = ConnectStatusType.CONNECTED
        if snapshot.system.active_rack_count > 0:
            connect_status |= ConnectStatusType.AVAILABLE
            
        # Check if any rack is operating
        operating = any(
            r.status in (RackStatus.CHARGING, RackStatus.DISCHARGING)
            for r in snapshot.racks
        )
        if operating:
            connect_status |= ConnectStatusType.OPERATING

        # Check for faults
        if snapshot.has_alarms or any(r.status == RackStatus.FAULT for r in snapshot.racks):
            connect_status |= ConnectStatusType.FAULT

        # Determine operational mode - use OPERATING for any active state
        op_mode = OperationalModeStatusType.OPERATING
        
        ts = int(datetime.now().timestamp())

        return DERStatus(
            href=href,
            readingTime=ts,
            genConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
            operationalModeStatus=OperationalModeStatusValue(dateTime=ts, value=f"{int(op_mode):02X}"),
            stateOfChargeStatus=self._to_soc(snapshot.average_soc),
            storConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
        )

    def snapshot_to_der_availability(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERAvailability:
        """
        Convert BMS snapshot to DERAvailability.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the availability resource
            
        Returns:
            DERAvailability object
        """
        # Calculate available power based on SOC and system limits
        avg_soc = snapshot.average_soc
        
        # Available discharge power (depends on SOC)
        # Lower SOC = less available discharge power
        discharge_factor = avg_soc / 100.0
        avail_discharge_w = self.max_power * discharge_factor
        
        # Available charge power (depends on remaining capacity)
        charge_factor = (100.0 - avg_soc) / 100.0
        avail_charge_w = self.max_power * charge_factor

        # Calculate max charge/discharge from rack limits
        if snapshot.active_racks:
            max_charge_current = min(r.max_charge_current for r in snapshot.active_racks)
            max_discharge_current = min(r.max_discharge_current for r in snapshot.active_racks)
            avg_voltage = sum(r.voltage for r in snapshot.active_racks) / len(snapshot.active_racks)
            
            # Limit by current capabilities
            avail_charge_w = min(avail_charge_w, max_charge_current * avg_voltage)
            avail_discharge_w = min(avail_discharge_w, max_discharge_current * avg_voltage)

        return DERAvailability(
            href=href,
            readingTime=int(datetime.now().timestamp()),
            reserveChargePercent=int(avg_soc * 100),  # 0-10000
            reservePercent=int(avg_soc * 100),
            statWAvail=self._to_active_power(avail_discharge_w),
        )

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
            updatedTime=int(datetime.now().timestamp()),
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
            DERStatus for the rack
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

        ts = int(rack.timestamp.timestamp())

        return DERStatus(
            href=href,
            readingTime=ts,
            genConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
            operationalModeStatus=OperationalModeStatusValue(dateTime=ts, value=f"{int(op_mode):02X}"),
            stateOfChargeStatus=self._to_soc(rack.soc),
            storConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
        )
