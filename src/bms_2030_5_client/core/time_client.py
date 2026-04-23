"""
IEEE 2030.5 Time Synchronization Client.

Implements periodic time synchronization with the IEEE 2030.5 server
as required by IEEE 2030.5-2018 Section 5.10: Time Function Set.

The Time resource (/tm) does not support subscription/notification,
so polling is the only method for time synchronization.

Design decisions (locked — do NOT simplify):
1. get_server_time() returns Optional[int] (Unix epoch seconds), NOT a Time object.
   This ensures type safety across callers and avoids attribute access bugs.
2. _time_offset is stored on the instance after each sync so callers (e.g.,
   mup/adapter.py) can retrieve the corrected time via get_corrected_time().
3. config parameter is optional for backward compatibility (legacy code that
   instantiates with only `client` continues to work).
4. sync_and_log_time() MUST compute AND store the offset, not just log it.
   This was the root cause of repeated "timestamp imprecision" regressions.
"""

import asyncio
import logging
import time
from typing import Optional, TYPE_CHECKING

from bms_2030_5_client.core.sep_client import SepClientError
from bms_2030_5_client.ieee2030_5.xml_utils import xml_to_dataclass
from bms_2030_5_client.models.ieee2030_5_models import Time

if TYPE_CHECKING:
    from bms_2030_5_client.runtime_config import TimeSyncConfig

logger = logging.getLogger(__name__)


class TimeSyncClient:
    """
    Periodically synchronizes client time with the IEEE 2030.5 server.

    According to IEEE 2030.5-2018 Section 5.10, clients must periodically
    poll the server's Time resource (/tm) to maintain clock accuracy.
    The recommended polling interval is 15 minutes.

    After each successful sync, the computed offset is stored in
    _time_offset (seconds). Use get_corrected_time() to get a
    server-aligned Unix timestamp for use in data reporting.
    """

    def __init__(self, client, config=None):
        """
        Initialize the TimeSyncClient.

        Args:
            client: The SepClient / IEEE2030_5Client instance for server communication.
            config: Optional TimeSyncConfig. If provided, enables the run() loop and
                    controls polling interval. If None, sync must be called manually.
        """
        self._client = client
        self._config = config
        self._running = False
        # Stored offset: server_time - local_time (seconds).
        # Positive means local clock is behind the server.
        self._time_offset: int = 0
        self._synced_at_least_once: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_corrected_time(self) -> int:
        """
        Return the current Unix timestamp corrected by the last known
        server time offset.

        This is the value that MUST be used for all data reporting
        (MirrorMeterReading timestamps, DERStatus dateTime, etc.).

        Returns:
            int: Server-aligned Unix timestamp in seconds.
        """
        return int(time.time()) + self._time_offset

    @property
    def time_offset(self) -> int:
        """The last computed offset: server_time - local_time (seconds)."""
        return self._time_offset

    @property
    def is_synced(self) -> bool:
        """True if at least one successful sync has occurred."""
        return self._synced_at_least_once

    async def get_server_time(self) -> Optional[int]:
        """
        Retrieve the current server time from the /tm resource.

        Returns:
            int: Server's currentTime as Unix epoch seconds, or None on failure.

        Note: Returns int (not a Time object) for type safety across callers.
        """
        try:
            logger.debug("Requesting server time from /tm")
            response = await self._client.get("/tm")
            if not response.is_success:
                logger.debug(f"Failed to retrieve server time: HTTP {response.status_code}")
                return None

            text = response.body
            time_obj = xml_to_dataclass(text, Time)
            server_time = time_obj.currentTime

            if server_time <= 0:
                logger.debug(f"Server returned invalid currentTime: {server_time}")
                return None

            return server_time

        except (SepClientError, Exception) as e:
            logger.debug(f"Failed to retrieve server time: {e}")
            return None

    async def sync_and_log_time(self) -> None:
        """
        Perform a single time synchronization: retrieve server time,
        compute and STORE the offset, and log the result.

        IMPORTANT: The offset is stored in self._time_offset so that
        get_corrected_time() returns accurate values for data reporting.
        Merely logging the delta (without storing it) is a known bug
        that caused repeated timestamp imprecision regressions.
        """
        try:
            server_time = await self.get_server_time()
            if server_time is None:
                logger.warning(
                    "Could not synchronize time with server. "
                    "Falling back to local system time."
                )
                return

            local_time = int(time.time())
            offset = server_time - local_time

            # Store offset for use by get_corrected_time()
            self._time_offset = offset
            self._synced_at_least_once = True

            logger.info(
                f"Time synchronized with server. Server Time: {server_time}, "
                f"Local Time: {local_time}, Delta: {offset}s"
            )

        except (SepClientError, Exception) as e:
            logger.warning(
                f"Could not synchronize time with server. "
                f"Falling back to local system time. Error: {e}"
            )

    async def run(self):
        """
        The main polling loop for periodic time synchronization.
        Requires config to be set (raises RuntimeError otherwise).
        """
        if self._config is None:
            raise RuntimeError(
                "TimeSyncClient.run() requires a config object. "
                "Pass config= when constructing TimeSyncClient."
            )

        if not self._config.enabled:
            logger.info("Time synchronization is disabled by configuration.")
            return

        interval = getattr(self._config, "interval_seconds", 900)
        logger.info(f"Starting time synchronization task with a {interval}s interval.")
        self._running = True
        while self._running:
            try:
                await self.sync_and_log_time()
            except Exception:
                logger.exception("An unexpected error occurred during time synchronization")

            await asyncio.sleep(interval)

    def stop(self):
        """Stop the synchronization loop."""
        self._running = False
