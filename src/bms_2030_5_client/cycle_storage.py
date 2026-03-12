"""
Binary storage for cycle tracking data.

Provides persistent storage for cycle count and SOC tracking data
to survive program restarts and power failures.
"""

import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Binary file format:
# - Magic number: 4 bytes (b'CYCL')
# - Version: 2 bytes (uint16)
# - Cycle count: 4 bytes (uint32)
# - Charge accumulated: 8 bytes (float64)
# - Discharge accumulated: 8 bytes (float64)
# - Last SOC: 8 bytes (float64, NaN if not set)
# - Timestamp: 8 bytes (int64, Unix timestamp)
# - Checksum: 4 bytes (CRC32)

MAGIC_NUMBER = b'CYCL'
FORMAT_VERSION = 1
HEADER_FORMAT = '<4sHI3dqI'  # magic, version, cycle_count, charge_acc, discharge_acc, last_soc, timestamp, checksum
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def _crc32(data: bytes) -> int:
    """Calculate CRC32 checksum."""
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


@dataclass
class CycleTrackingData:
    """
    Cycle tracking state data.
    
    Attributes:
        cycle_count: Total completed charge/discharge cycles
        charge_accumulated: Accumulated charge percentage in current cycle
        discharge_accumulated: Accumulated discharge percentage in current cycle
        last_soc: Last recorded SOC value (None if not set)
        timestamp: When this data was last updated
    """
    cycle_count: int = 0
    charge_accumulated: float = 0.0
    discharge_accumulated: float = 0.0
    last_soc: Optional[float] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class CycleStorageError(Exception):
    """Exception for cycle storage operations."""
    pass


class CycleStorage:
    """
    Binary file storage for cycle tracking data.
    
    Provides atomic read/write operations with checksum validation
    to ensure data integrity after power failures.
    
    File format (46 bytes total):
    - Magic number: 4 bytes (b'CYCL')
    - Version: 2 bytes (uint16)
    - Cycle count: 4 bytes (uint32)
    - Charge accumulated: 8 bytes (float64)
    - Discharge accumulated: 8 bytes (float64)
    - Last SOC: 8 bytes (float64, NaN if not set)
    - Timestamp: 8 bytes (int64, Unix timestamp)
    - Checksum: 4 bytes (CRC32)
    """
    
    def __init__(self, file_path: str = "data/cycle_tracking.bin"):
        """
        Initialize cycle storage.
        
        Args:
            file_path: Path to the binary storage file
        """
        self.file_path = Path(file_path)
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """Ensure the storage directory exists."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def save(self, data: CycleTrackingData) -> bool:
        """
        Save cycle tracking data to binary file.
        
        Uses atomic write (write to temp file, then rename) to prevent
        corruption from power failures during write.
        
        Args:
            data: CycleTrackingData to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert last_soc to float (use NaN for None)
            import math
            last_soc = data.last_soc if data.last_soc is not None else math.nan
            
            # Get timestamp as Unix timestamp
            timestamp = int(data.timestamp.timestamp())
            
            # Pack data without checksum first
            payload = struct.pack(
                '<4sHI3dq',
                MAGIC_NUMBER,
                FORMAT_VERSION,
                data.cycle_count,
                data.charge_accumulated,
                data.discharge_accumulated,
                last_soc,
                timestamp,
            )
            
            # Calculate checksum over payload
            checksum = _crc32(payload)
            
            # Pack complete data with checksum
            binary_data = payload + struct.pack('<I', checksum)
            
            # Atomic write: write to temp file, then rename
            temp_path = self.file_path.with_suffix('.tmp')
            with open(temp_path, 'wb') as f:
                f.write(binary_data)
                f.flush()
                # Ensure data is written to disk
                import os
                os.fsync(f.fileno())
            
            # Atomic rename
            temp_path.replace(self.file_path)
            
            # Create backup copy for fallback on future load failures
            try:
                backup_path = self.file_path.with_suffix('.bak')
                import shutil
                shutil.copy2(self.file_path, backup_path)
            except Exception as backup_err:
                logger.warning(f"Failed to create backup: {backup_err}")
            
            logger.debug(
                f"Saved cycle data: cycles={data.cycle_count}, "
                f"charge={data.charge_accumulated:.2f}%, "
                f"discharge={data.discharge_accumulated:.2f}%"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to save cycle tracking data: {e}")
            return False
    
    def load(self) -> Optional[CycleTrackingData]:
        """
        Load cycle tracking data from binary file.
        
        Returns:
            CycleTrackingData if successful, None if file doesn't exist or is invalid
        """
        if not self.file_path.exists():
            logger.info(f"Cycle storage file not found: {self.file_path}")
            return None
        
        try:
            with open(self.file_path, 'rb') as f:
                binary_data = f.read()
            
            # Validate size
            if len(binary_data) != HEADER_SIZE:
                logger.warning(
                    f"Invalid cycle storage file size: {len(binary_data)} "
                    f"(expected {HEADER_SIZE})"
                )
                return self._load_backup()
            
            # Unpack data
            (
                magic,
                version,
                cycle_count,
                charge_accumulated,
                discharge_accumulated,
                last_soc,
                timestamp,
                stored_checksum,
            ) = struct.unpack(HEADER_FORMAT, binary_data)
            
            # Validate magic number
            if magic != MAGIC_NUMBER:
                logger.warning(f"Invalid magic number in cycle storage: {magic}")
                return self._load_backup()
            
            # Validate version
            if version != FORMAT_VERSION:
                logger.warning(
                    f"Unsupported cycle storage version: {version} "
                    f"(expected {FORMAT_VERSION})"
                )
                return self._load_backup()
            
            # Validate checksum
            payload = binary_data[:-4]  # Everything except checksum
            calculated_checksum = _crc32(payload)
            if stored_checksum != calculated_checksum:
                logger.warning(
                    f"Cycle storage checksum mismatch: stored={stored_checksum:#x}, "
                    f"calculated={calculated_checksum:#x}"
                )
                return self._load_backup()
            
            # Convert NaN back to None
            import math
            if math.isnan(last_soc):
                last_soc = None
            
            data = CycleTrackingData(
                cycle_count=cycle_count,
                charge_accumulated=charge_accumulated,
                discharge_accumulated=discharge_accumulated,
                last_soc=last_soc,
                timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            )
            
            logger.info(
                f"Loaded cycle data: cycles={data.cycle_count}, "
                f"charge={data.charge_accumulated:.2f}%, "
                f"discharge={data.discharge_accumulated:.2f}%, "
                f"last_soc={data.last_soc}"
            )
            return data
            
        except struct.error as e:
            logger.error(f"Failed to parse cycle storage file: {e}")
            return self._load_backup()
        except Exception as e:
            logger.error(f"Failed to load cycle tracking data: {e}")
            return self._load_backup()
    
    def _load_backup(self) -> Optional[CycleTrackingData]:
        """
        Try loading from backup file when primary file is corrupted.

        Returns:
            CycleTrackingData if backup loaded successfully, None otherwise
        """
        backup_path = self.file_path.with_suffix('.bak')
        if not backup_path.exists():
            logger.warning("No backup file available for recovery")
            return None

        logger.info(f"Attempting to load from backup: {backup_path}")
        try:
            with open(backup_path, 'rb') as f:
                binary_data = f.read()

            if len(binary_data) != HEADER_SIZE:
                logger.warning("Backup file also has invalid size")
                return None

            (
                magic, version, cycle_count,
                charge_accumulated, discharge_accumulated, last_soc,
                timestamp, stored_checksum,
            ) = struct.unpack(HEADER_FORMAT, binary_data)

            if magic != MAGIC_NUMBER or version != FORMAT_VERSION:
                logger.warning("Backup file has invalid magic/version")
                return None

            payload = binary_data[:-4]
            if stored_checksum != _crc32(payload):
                logger.warning("Backup file checksum mismatch")
                return None

            import math
            if math.isnan(last_soc):
                last_soc = None

            data = CycleTrackingData(
                cycle_count=cycle_count,
                charge_accumulated=charge_accumulated,
                discharge_accumulated=discharge_accumulated,
                last_soc=last_soc,
                timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            )
            logger.info(
                f"Recovered cycle data from backup: cycles={data.cycle_count}, "
                f"charge={data.charge_accumulated:.2f}%"
            )
            return data

        except Exception as e:
            logger.error(f"Failed to load backup: {e}")
            return None

    def delete(self) -> bool:
        """
        Delete the storage file.
        
        Returns:
            True if deleted or didn't exist, False on error
        """
        try:
            if self.file_path.exists():
                self.file_path.unlink()
                logger.info(f"Deleted cycle storage file: {self.file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete cycle storage file: {e}")
            return False
    
    def exists(self) -> bool:
        """Check if storage file exists."""
        return self.file_path.exists()
    
    def get_info(self) -> dict:
        """
        Get storage file information.
        
        Returns:
            Dict with file info (path, exists, size, modified time)
        """
        info = {
            "path": str(self.file_path),
            "exists": self.file_path.exists(),
            "size": 0,
            "modified": None,
        }
        
        if self.file_path.exists():
            stat = self.file_path.stat()
            info["size"] = stat.st_size
            info["modified"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        
        return info


# Convenience functions
def load_cycle_data(file_path: str = "data/cycle_tracking.bin") -> Optional[CycleTrackingData]:
    """Load cycle tracking data from file."""
    storage = CycleStorage(file_path)
    return storage.load()


def save_cycle_data(
    data: CycleTrackingData,
    file_path: str = "data/cycle_tracking.bin"
) -> bool:
    """Save cycle tracking data to file."""
    storage = CycleStorage(file_path)
    return storage.save(data)
