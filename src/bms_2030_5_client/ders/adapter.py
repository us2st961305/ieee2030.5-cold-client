"""
DER Status adapter for converting BMS data to DERStatus.
"""

import logging
from datetime import datetime
from typing import Optional

from bms_2030_5_client.models import (
    BMSSnapshot,
    RackStatus,
    DERStatus,
    ConnectStatusType,
    OperationalModeStatusType,
    ConnectStatusValue,
    OperationalModeStatusValue,
    AlarmStatusValue,
    StateOfCharge,
)

from bms_2030_5_client.protocols import (
    ErrorStatusBits,
    RackFlagBits,
    LECUFlagBits,
    AlarmStatusType,
)

logger = logging.getLogger(__name__)


def modbus_error_to_alarm_status(
    error_status: int = 0,
    rack_flag: int = 0,
    lecu_flag: int = 0,
) -> int:
    """
    Convert Modbus error status bits to IEEE 2030.5 AlarmStatusType.
    
    Maps BMS error registers to IEEE 2030.5 DERStatus.alarmStatus field.
    
    Args:
        error_status: RS-485 ErrorStatusBits (register 0x0008)
        rack_flag: CUBE RackFlagBits (register 7020)
        lecu_flag: CUBE LECUFlagBits (register 7019)
        
    Returns:
        Combined alarm status as IEEE 2030.5 AlarmStatusType bitfield
    """
    alarm = 0
    
    # === Map RS-485 ErrorStatusBits (0x0008) ===
    if error_status & ErrorStatusBits.LEVEL2_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_LEVEL2_ALARM
    if error_status & ErrorStatusBits.LEVEL3_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_LEVEL3_ALARM
    if error_status & ErrorStatusBits.PF_PROTECTION:
        alarm |= AlarmStatusType.DER_FAULT_PF_PROTECTION
    if error_status & ErrorStatusBits.RELAY_STUCK:
        alarm |= AlarmStatusType.DER_FAULT_RELAY_STUCK
    if error_status & ErrorStatusBits.VOLTAGE_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_VOLTAGE  # Could be over or under
    if error_status & ErrorStatusBits.TEMP_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_TEMP  # Could be over or under
    if error_status & ErrorStatusBits.CURRENT_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_CURRENT
    if error_status & ErrorStatusBits.COMM_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_COMM_ERROR
    if error_status & ErrorStatusBits.BALANCE_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_BALANCE_ERROR
    
    # === Map CUBE RackFlagBits (7020) - Low Byte (Alarms) ===
    if rack_flag & RackFlagBits.CELL_OV_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_VOLTAGE
    if rack_flag & RackFlagBits.CELL_UV_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_UNDER_VOLTAGE
    if rack_flag & RackFlagBits.CELL_OT_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_TEMP
    if rack_flag & RackFlagBits.CELL_UT_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_UNDER_TEMP
    if rack_flag & RackFlagBits.CHG_OC_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_CURRENT
    if rack_flag & RackFlagBits.DSC_OC_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_CURRENT
    if rack_flag & RackFlagBits.RACK_OV_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_OVER_VOLTAGE
    if rack_flag & RackFlagBits.RACK_UV_ALARM:
        alarm |= AlarmStatusType.DER_FAULT_UNDER_VOLTAGE
    
    # === Map CUBE RackFlagBits (7020) - High Byte (Protection triggered) ===
    if rack_flag & RackFlagBits.CELL_OV_PROT:
        alarm |= AlarmStatusType.DER_FAULT_OVER_VOLTAGE | AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    if rack_flag & RackFlagBits.CELL_UV_PROT:
        alarm |= AlarmStatusType.DER_FAULT_UNDER_VOLTAGE | AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    if rack_flag & RackFlagBits.CELL_OT_PROT:
        alarm |= AlarmStatusType.DER_FAULT_OVER_TEMP | AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    if rack_flag & RackFlagBits.CELL_UT_PROT:
        alarm |= AlarmStatusType.DER_FAULT_UNDER_TEMP | AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    if rack_flag & RackFlagBits.CHG_OC_PROT:
        alarm |= AlarmStatusType.DER_FAULT_OVER_CURRENT | AlarmStatusType.DER_FAULT_STORAGE_CHARGE_MAX
    if rack_flag & RackFlagBits.DSC_OC_PROT:
        alarm |= AlarmStatusType.DER_FAULT_OVER_CURRENT | AlarmStatusType.DER_FAULT_STORAGE_CHARGE_MIN
    
    # === Map CUBE LECUFlagBits (7019) ===
    if lecu_flag & LECUFlagBits.COMM_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_COMM_ERROR
    if lecu_flag & LECUFlagBits.HARDWARE_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    if lecu_flag & LECUFlagBits.AFE_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    if lecu_flag & LECUFlagBits.MEASURE_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    if lecu_flag & LECUFlagBits.BALANCE_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_BALANCE_ERROR
    if lecu_flag & LECUFlagBits.EEPROM_ERROR:
        alarm |= AlarmStatusType.DER_FAULT_INTERNAL_FAULT
    
    return alarm


class DERStatusAdapter:
    """
    Adapter to convert BMS snapshot to DERStatus.
    
    Focuses on single DER representation (not rack-level).
    Includes mapping of Modbus error status to IEEE 2030.5 alarmStatus.
    """

    def _to_soc(self, percent: float) -> StateOfCharge:
        """Convert percentage to StateOfCharge."""
        return StateOfCharge(
            dateTime=int(datetime.now().timestamp()),
            value=int(percent * 100)
        )

    def _aggregate_alarm_status(self, snapshot: BMSSnapshot) -> int:
        """
        Aggregate alarm status from all racks in the snapshot.
        
        Args:
            snapshot: BMS system snapshot
            
        Returns:
            Combined IEEE 2030.5 AlarmStatusType bitfield
        """
        combined_alarm = 0
        
        for rack in snapshot.racks:
            # Each rack's alarm_status contains the raw Modbus alarm bits
            # Convert each rack's alarm status and combine
            rack_alarm = modbus_error_to_alarm_status(
                error_status=rack.alarm_status,
                rack_flag=0,  # Will be populated if CUBE data is available
                lecu_flag=0,
            )
            combined_alarm |= rack_alarm
        
        return combined_alarm

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
            DERStatus object with alarmStatus populated from Modbus data
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
        
        # Aggregate alarm status from all racks
        alarm_status = self._aggregate_alarm_status(snapshot)
        
        ts = int(datetime.now().timestamp())

        return DERStatus(
            href=href,
            readingTime=ts,
            alarmStatus=AlarmStatusValue(dateTime=ts, value=f"{alarm_status:08X}") if alarm_status != 0 else None,
            genConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
            operationalModeStatus=OperationalModeStatusValue(dateTime=ts, value=f"{int(op_mode):02X}"),
            stateOfChargeStatus=self._to_soc(snapshot.average_soc),
            storConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
        )

    def rack_alarm_to_der_alarm_status(
        self,
        error_status: int = 0,
        rack_flag: int = 0,
        lecu_flag: int = 0,
    ) -> str:
        """
        Convert single rack's Modbus error bits to alarmStatus hex string.
        
        Args:
            error_status: RS-485 ErrorStatusBits (register 0x0008)
            rack_flag: CUBE RackFlagBits (register 7020)
            lecu_flag: CUBE LECUFlagBits (register 7019)
            
        Returns:
            8-character hex string for IEEE 2030.5 alarmStatus
        """
        alarm = modbus_error_to_alarm_status(error_status, rack_flag, lecu_flag)
        return f"{alarm:08X}"
