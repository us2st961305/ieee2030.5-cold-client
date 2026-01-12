"""
DER Availability client operations.
"""

import logging
from typing import TYPE_CHECKING

from bms_2030_5_client.models import DERAvailability

if TYPE_CHECKING:
    from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client

logger = logging.getLogger(__name__)


class DERAvailabilityClient:
    """
    Client for DER Availability operations.
    
    Handles updating DER availability on the IEEE 2030.5 server.
    """

    def __init__(self, ieee_client: "IEEE2030_5Client"):
        """
        Initialize DER Availability client.
        
        Args:
            ieee_client: IEEE 2030.5 client instance
        """
        self.ieee_client = ieee_client

    async def update_availability(
        self,
        der_path: str,
        availability: DERAvailability,
    ) -> bool:
        """
        Update DER availability on server.
        
        Args:
            der_path: DER resource path
            availability: DERAvailability object
            
        Returns:
            True if successful
        """
        avail_path = f"{der_path}/dera"
        return await self.ieee_client._put(avail_path, availability)
