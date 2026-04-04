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
        
        return success
