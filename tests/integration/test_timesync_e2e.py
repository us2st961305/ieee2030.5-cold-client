import asyncio
import logging
import time
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import threading
from pathlib import Path

# We need to mock the necessary classes because we are running this as a standalone test
# but we want to use the actual logic of TimeSyncClient.
# Since we can't easily import them without a full environment setup in this script,
# we will import them using the PYTHONPATH.

import sys
import os

# Add src to path
sys.path.append('/home/us2st/ieee20305-ai-maintaner/ieee2030.5-cold-client/src')

from bms_2030_5_client.core.time_client import TimeSyncClient
from bms_2030_5_client.runtime_config import TimeSyncConfig
from bms_2030_5_client.models.ieee2030_5_models import Time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("E2E_TimeSync")

class MockSepClient:
    """Mocks the SepClient used by TimeSyncClient."""
    def __init__(self, server_url):
        self.server_url = server_url

    async def get(self, path):
        # We use httpx to actually make the call to our mock server
        import httpx
        async with httpx.AsyncClient(base_url=self.server_url, verify=False) as client:
            response = await client.get(path)
            # Wrap httpx.Response to match what TimeSyncClient expects (it calls .text and .raise_for_status())
            return response

class TimeSyncMockServer(BaseHTTPRequestHandler):
    """Mock IEEE 2030.5 Server providing the /tm resource."""
    
    def do_GET(self):
        if self.path == "/tm":
            # Simulate server time (current time + a small offset for testing)
            server_time = int(time.time()) + 10 
            # IEEE 2030.5 Time resource XML response
            # Based on typical IEEE 2030.5 Time model
            xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Time xmlns="http://www.ieee.org/upnp/devices/0/time">
                <currentTime>{server_time}</currentTime>
            </Time>
            """
            self.send_response(200)
            self.send_header("Content-Type", "application/sep+xml")
            self.end_headers()
            self.wfile.write(xml_response.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_mock_server(port=7443):
    server = HTTPServer(('localhost', port), TimeSyncMockServer)
    # In a real E2E we'd use SSL, but for a local integration test, HTTP is sufficient 
    # if we mock the client to not require SSL or use a self-signed cert.
    # To keep it simple and focused on the TimeSyncClient logic, we use HTTP.
    server.serve_forever()

async def main():
    port = 7443
    server_thread = threading.Thread(target=run_mock_server, args=(port,), daemon=True)
    server_thread.start()
    await asyncio.sleep(1) # Wait for server to start

    # Configuration
    config = TimeSyncConfig(enabled=True, interval_seconds=60)
    client = MockSepClient(f"http://localhost:{port}")
    ts_client = TimeSyncClient(client=client, config=config)

    print("\n--- Starting E2E Time Sync Test ---")
    
    # Trigger a manual sync
    # Note: TimeSyncClient.sync_and_log_time() logs to the logger.
    # We'll capture the result by calling get_server_time directly and then the sync method.
    
    server_time = await ts_client.get_server_time()
    print(f"Step 1: Server Time Received -> {server_time}")
    
    if server_time is None:
        print("FAILED: Could not receive server time")
        return

    # Use a custom logger to capture the output of sync_and_log_time
    import logging
    log_capture = []
    class CaptureHandler(logging.Handler):
        def emit(self, record):
            log_capture.append(record.getMessage())
    
    logger_ts = logging.getLogger("bms_2030_5_client.core.time_client")
    logger_ts.addHandler(CaptureHandler())
    logger_ts.setLevel(logging.INFO)

    await ts_client.sync_and_log_time()
    
    print("Step 2: Executed sync_and_log_time()")
    
    for msg in log_capture:
        print(f"Log Output: {msg}")

    # Validation
    success = any("Time synchronized with server" in msg for msg in log_capture)
    if success:
        print("\nRESULT: SUCCESS - TimeSyncClient correctly connected, parsed time, and calculated offset.")
    else:
        print("\nRESULT: FAILED - Expected synchronization log not found.")

if __name__ == "__main__":
    asyncio.run(main())
