"""
Time Sync Client for IEEE 2030.5 Server Time Synchronization.

This module provides the TimeSyncClient class for synchronizing time with
an IEEE 2030.5 server by fetching the Time resource from the /tm endpoint.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from bms_2030_5_client.core.sep_client import SepClientError
from bms_2030_5_client.ieee2030_5.client import IEEE2030_5Client
from bms_2030_5_client.ieee2030_5.xml_utils import xml_to_dataclass
from bms_2030_5_client.models.ieee2030_5_models import Time

logger = logging.getLogger(__name__)


class TimeSyncClient:
    """
    Client for synchronizing time with an IEEE 2030.5 server.
    
    This client fetches the Time resource from the server's /tm endpoint
    and provides methods to synchronize and log time differences.
    """

    def __init__(self, client: IEEE2030_5Client):
        """
        Initialize the TimeSyncClient.

        Args:
            client: An instance of IEEE2030_5Client to handle HTTP requests.
        """
        self._client = client
        self._time_resource_path = "/tm"

    async def get_server_time(self) -> Optional[Time]:
        """
        Fetch the Time resource from the server.

        Returns:
            A Time object if successful, otherwise None.
        """
        try:
            logger.debug(f"Requesting server time from {self._time_resource_path}")
            response = await self._client.get(self._time_resource_path)

            if not response.is_success:
                logger.error(
                    f"Failed to get server time. Status: {response.status_code}, "
                    f"Body: {response.body}"
                )
                return None

            time_obj = xml_to_dataclass(response.body, Time)
            return time_obj

        except SepClientError as e:
            logger.error(f"Error getting server time: {e}", exc_info=True)
            return None
        except Exception:
            logger.exception("An unexpected error occurred during time synchronization.")
            return None

    async def sync_and_log_time(self) -> None:
        """
        Fetch server time, calculate the offset, and log the result.
        This method handles graceful degradation if the sync fails.
        """
        server_time = await self.get_server_time()
        if server_time and server_time.currentTime > 0:
            local_time = int(time.time())
            delta = server_time.currentTime - local_time
            logger.info(
                f"Time synchronized with server. Server Time: {server_time.currentTime}, "
                f"Local Time: {local_time}, Delta: {delta}s"
            )
        else:
            logger.warning(
                "Could not synchronize time with server. "
                "Falling back to local system time."
            )