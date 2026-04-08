"""
Time Synchronization module for IEEE 2030.5 compliance.

This module provides time synchronization functionality as required by
IEEE 2030.5-2018 Section 5.10: Time Function Set.
"""

from .client import TimeSyncClient

__all__ = ["TimeSyncClient"]