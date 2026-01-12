"""
IEEE 2030.5 BMS Client Package

A Python client for integrating Battery Management Systems with IEEE 2030.5 servers.
"""

from bms_2030_5_client.client import BMSClient
from bms_2030_5_client.config import Config

# Export specialized modules
from bms_2030_5_client import ders, dera, mup

__version__ = "0.1.0"
__all__ = [
    "BMSClient",
    "Config",
    "ders",
    "dera",
    "mup",
]
