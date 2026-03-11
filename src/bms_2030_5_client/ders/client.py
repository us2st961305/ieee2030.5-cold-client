"""
DER Status client operations.
"""

import logging
from typing import TYPE_CHECKING

from bms_2030_5_client.models import DERStatus

if TYPE_CHECKING:
    from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client

logger = logging.getLogger(__name__)


class DERStatusClient:
    """
    Client for DER Status operations.
    
    Handles updating DER status on the IEEE 2030.5 server.
    """

    def __init__(self, ieee_client: "IEEE2030_5Client"):
        """
        Initialize DER Status client.
        
        Args:
            ieee_client: IEEE 2030.5 client instance
        """
        self.ieee_client = ieee_client

    async def update_status(self, der_path: str, status: DERStatus) -> bool:
        """
        Update DER status on server.
        
        Args:
            der_path: DER resource path
            status: DERStatus object
            
        Returns:
            True if successful
        """
        status_path = f"{der_path}/ders"
        success = await self.ieee_client._put(status_path, status)
        
        # Record to data recorder
        self._record_der_status(der_path, status, success)
        
        return success
    
    def _record_der_status(self, der_path: str, status: DERStatus, success: bool) -> None:
        """Record a DER status upload to the data recorder."""
        try:
            from bms_2030_5_client.web.data_recorder import get_data_recorder
            
            recorder = get_data_recorder()
            status_dict = {}
            
            # Extract status fields
            if hasattr(status, "stateOfChargeStatus"):
                soc = status.stateOfChargeStatus
                if hasattr(soc, "value"):
                    status_dict["soc"] = soc.value / 100.0  # Convert from 0-10000 to %
            
            if hasattr(status, "operationalModeStatus"):
                status_dict["operationalMode"] = status.operationalModeStatus
            
            if hasattr(status, "genConnectStatus"):
                gc = status.genConnectStatus
                if hasattr(gc, "value"):
                    status_dict["connected"] = bool(gc.value)
            
            if hasattr(status, "inverterStatus"):
                inv = status.inverterStatus
                if hasattr(inv, "value"):
                    status_dict["inverterStatus"] = inv.value
            
            if hasattr(status, "alarmStatus"):
                status_dict["alarmStatus"] = status.alarmStatus
            
            recorder.record_der_status(
                der_path=der_path,
                status=status_dict,
                status_code=200 if success else 500,
                success=success,
            )
        except Exception as e:
            logger.debug(f"Failed to record DER status: {e}")
