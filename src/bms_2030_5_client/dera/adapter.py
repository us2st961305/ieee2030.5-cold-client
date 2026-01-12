"""
DER Availability adapter for converting BMS data to DERAvailability.
"""

import logging
from datetime import datetime
from typing import Optional

from bms_2030_5_client.models import (
    BMSSnapshot,
    DERAvailability,
    ActivePower,
)

logger = logging.getLogger(__name__)


class DERAvailabilityAdapter:
    """
    Adapter to convert BMS snapshot to DERAvailability.
    
    Focuses on single DER representation (not rack-level).
    """

    def __init__(
        self,
        max_power: float = 100000.0,  # W (100 kW)
    ):
        """
        Initialize adapter with system ratings.
        
        Args:
            max_power: Maximum power rating in W
        """
        self.max_power = max_power

    def _to_active_power(self, watts: float) -> ActivePower:
        """Convert watts to ActivePower with appropriate multiplier."""
        # Use multiplier for scaling
        if abs(watts) >= 1000000:
            return ActivePower(multiplier=6, value=int(watts / 1000000))
        elif abs(watts) >= 1000:
            return ActivePower(multiplier=3, value=int(watts / 1000))
        else:
            return ActivePower(multiplier=0, value=int(watts))

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
