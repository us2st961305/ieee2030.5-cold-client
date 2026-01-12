"""
MirrorUsagePoint client operations.
"""

import logging
from typing import TYPE_CHECKING, List, Optional, Dict

from bms_2030_5_client.models import MirrorUsagePoint, MirrorMeterReading

if TYPE_CHECKING:
    from bms_2030_5_client.ieee2030_5 import IEEE2030_5Client

logger = logging.getLogger(__name__)


class MirrorUsagePointClient:
    """
    Client for MirrorUsagePoint operations.
    
    Handles meter registration and reading uploads to the IEEE 2030.5 server.
    """

    def __init__(self, ieee_client: "IEEE2030_5Client"):
        """
        Initialize MirrorUsagePoint client.
        
        Args:
            ieee_client: IEEE 2030.5 client instance
        """
        self.ieee_client = ieee_client
        self._mup_href: Optional[str] = None
        self._reading_mrids: Dict[str, str] = {}

    async def register_meter(
        self,
        mup: MirrorUsagePoint,
    ) -> Optional[str]:
        """
        Register MirrorUsagePoint (meter) with IEEE 2030.5 server.
        
        Uses two-step process required by the server:
        1. POST MirrorUsagePoint without MirrorMeterReading
        2. PUT MirrorUsagePoint with MirrorMeterReading
        
        Args:
            mup: MirrorUsagePoint to register (should have include_readings=False)
            
        Returns:
            MirrorUsagePoint href if successful, None otherwise
        """
        logger.info("Registering MirrorUsagePoint (meter)...")
        
        try:
            # Step 1: Create MirrorUsagePoint WITHOUT MirrorMeterReading
            _, location = await self.ieee_client.create_mirror_usage_point(mup)
            self._mup_href = location
            logger.info(f"Created MirrorUsagePoint at: {self._mup_href}")
            
            return self._mup_href
            
        except Exception as e:
            logger.warning(f"Failed to register MirrorUsagePoint: {e}")
            self._mup_href = None
            return None

    async def update_meter_with_readings(
        self,
        mup_with_readings: MirrorUsagePoint,
    ) -> bool:
        """
        Update MirrorUsagePoint with MirrorMeterReading (step 2).
        
        Args:
            mup_with_readings: MirrorUsagePoint with readings included
            
        Returns:
            True if successful
        """
        if not self._mup_href:
            logger.warning("No MirrorUsagePoint href available")
            return False
        
        try:
            success = await self.ieee_client.update_mirror_usage_point(
                self._mup_href,
                mup_with_readings,
            )
            
            if success:
                # Fetch the updated resource to cache reading mRIDs
                created_mup = await self.ieee_client.get_mirror_usage_point(self._mup_href)
                
                # Cache reading mRIDs for future updates
                if created_mup and created_mup.MirrorMeterReading:
                    for reading in created_mup.MirrorMeterReading:
                        if reading.description and reading.mRID:
                            # Map description to mRID
                            name = reading.description.lower().replace(" ", "_")
                            if "soc" in name:
                                self._reading_mrids["soc"] = reading.mRID
                            elif "current" in name:
                                self._reading_mrids["current"] = reading.mRID
                            elif "power" in name:
                                self._reading_mrids["power"] = reading.mRID
                            elif "charge" in name and "discharge" not in name:
                                self._reading_mrids["charge_energy"] = reading.mRID
                            elif "discharge" in name:
                                self._reading_mrids["discharge_energy"] = reading.mRID
                
                logger.info(f"Updated MirrorUsagePoint with readings at: {self._mup_href}")
                return True
            else:
                logger.warning("Failed to update MirrorUsagePoint with readings")
                return False
            
        except Exception as e:
            logger.warning(f"Failed to update MirrorUsagePoint with readings: {e}")
            return False

    async def upload_readings(
        self,
        readings: List[MirrorMeterReading],
    ) -> int:
        """
        Upload meter readings to the server.
        
        Args:
            readings: List of MirrorMeterReading objects
            
        Returns:
            Number of readings successfully uploaded
        """
        if not self._mup_href:
            logger.debug("No MirrorUsagePoint href available")
            return 0

        uploaded_count = 0
        for reading in readings:
            try:
                success = await self.ieee_client.update_mirror_meter_reading(
                    self._mup_href,
                    reading,
                )
                if success:
                    uploaded_count += 1
            except Exception as e:
                logger.error(f"Failed to upload {reading.description}: {e}")
        
        logger.debug(f"Uploaded {uploaded_count}/{len(readings)} meter readings")
        return uploaded_count

    @property
    def mup_href(self) -> Optional[str]:
        """Get the MirrorUsagePoint href."""
        return self._mup_href

    @property
    def reading_mrids(self) -> Dict[str, str]:
        """Get cached reading mRIDs."""
        return self._reading_mrids
