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
    StateOfCharge,
)

logger = logging.getLogger(__name__)


class DERStatusAdapter:
    """
    Adapter to convert BMS snapshot to DERStatus.
    
    Focuses on single DER representation (not rack-level).
    """

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
