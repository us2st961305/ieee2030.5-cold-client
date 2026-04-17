"""
IEEE 2030.5 Time Synchronization Client.

Implements periodic time synchronization with the IEEE 2030.5 server
as required by IEEE 2030.5-2018 Section 5.10: Time Function Set.

The Time resource (/tm) does not support subscription/notification,
so polling is the only method for time synchronization.
"""

import asyncio
import logging
import time

from bms_2030_5_client.core.sep_client import SepClient, SepClientError
from bms_2030_5_client.ieee2030_5.xml_utils import xml_to_dataclass
from bms_2030_5_client.models.ieee2030_5_models import Time
from bms_2030_5_client.runtime_config import TimeSyncConfig

logger = logging.getLogger(__name__)


class TimeSyncClient:
    """
    Periodically synchronizes client time with the IEEE 2030.5 server.
    
    According to IEEE 2030.5-2018 Section 5.10, clients must periodically
    poll the server's Time resource (/tm) to maintain clock accuracy.
    The recommended polling interval is 15 minutes.
    """

    def __init__(self, client: SepClient, config: TimeSyncConfig):
        """
        Initialize the TimeSyncClient.

        Args:
            client: The SepClient instance for server communication.
            config: Time synchronization configuration.
        """
        self._client = client
        self._config = config
        self._running = False

    async def run(self):
        """
        The main loop for the time synchronization task.
        """
        if not self._config.enabled:
            logger.info("Time synchronization is disabled by configuration.")
            return

        logger.info(
            f"Starting time synchronization task with a {self._config.interval_seconds}s interval."
        )
        self._running = True
        while self._running:
            try:
                await self.sync_and_log_time()
            except Exception:
                logger.exception("An unexpected error occurred during time synchronization")
            
            await asyncio.sleep(self._config.interval_seconds)

    def stop(self):
        """Stops the synchronization loop."""
        self._running = False

    async def sync_and_log_time(self) -> None:
        """
        Performs a single time synchronization with the server and logs the result.
        """
        try:
            logger.debug("Requesting server time from /tm")
            response = await self._client.get("/tm")
            response.raise_for_status()

            time_obj = xml_to_dataclass(response.text, Time)
            server_time = time_obj.currentTime
            local_time = int(time.time())
            offset = server_time - local_time

            if server_time <= 0:
                logger.warning("Could not synchronize time with server. Falling back to local system time.")
                return

            logger.info(
                f"Time synchronized with server. Server Time: {server_time}, "
                f"Local Time: {local_time}, Delta: {offset}s"
            )

        except (SepClientError, Exception) as e:
            logger.warning(f"Could not synchronize time with server. Falling back to local system time. Error: {e}")
