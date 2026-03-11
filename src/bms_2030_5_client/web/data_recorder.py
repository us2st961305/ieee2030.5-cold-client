"""
Data Recorder - Records and stores Modbus data and Meter uploads.

Provides history tracking for:
- Modbus register reads (BMS data)
- IEEE 2030.5 meter uploads (MirrorMeterReading)
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


class DataType(Enum):
    """Type of recorded data."""
    MODBUS_SYSTEM = "modbus_system"
    MODBUS_RACK = "modbus_rack"
    METER_UPLOAD = "meter_upload"
    DER_STATUS = "der_status"


@dataclass
class ModbusRecord:
    """A single Modbus data record."""
    timestamp: datetime
    source: str  # "system" or "rack_N"
    data: Dict[str, Any]
    raw_registers: Optional[List[int]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.data,
            "raw_registers": self.raw_registers,
        }


@dataclass 
class MeterUploadRecord:
    """A single meter upload record."""
    timestamp: datetime
    mup_href: str
    description: str
    readings: List[Dict[str, Any]]
    status_code: int
    success: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "mup_href": self.mup_href,
            "description": self.description,
            "readings": self.readings,
            "status_code": self.status_code,
            "success": self.success,
        }


@dataclass
class DERStatusRecord:
    """A single DER status record."""
    timestamp: datetime
    der_path: str
    status: Dict[str, Any]
    status_code: int
    success: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "der_path": self.der_path,
            "status": self.status,
            "status_code": self.status_code,
            "success": self.success,
        }


class DataRecorder:
    """
    Singleton recorder for Modbus and Meter data.
    
    Maintains a fixed-size history buffer for each data type.
    """
    
    _instance: Optional["DataRecorder"] = None
    
    def __new__(cls) -> "DataRecorder":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_records: int = 100):
        if getattr(self, "_initialized", False):
            return
        
        self._max_records = max_records
        
        # Modbus data history
        self._modbus_system: Deque[ModbusRecord] = deque(maxlen=max_records)
        self._modbus_racks: Dict[int, Deque[ModbusRecord]] = {}
        
        # Meter upload history
        self._meter_uploads: Deque[MeterUploadRecord] = deque(maxlen=max_records)
        
        # DER status history
        self._der_status: Deque[DERStatusRecord] = deque(maxlen=max_records)
        
        # Latest records cache
        self._latest_system: Optional[ModbusRecord] = None
        self._latest_racks: Dict[int, ModbusRecord] = {}
        self._latest_meter: Optional[MeterUploadRecord] = None
        self._latest_der: Optional[DERStatusRecord] = None
        
        # Statistics
        self._modbus_read_count = 0
        self._meter_upload_count = 0
        self._der_upload_count = 0
        
        self._initialized = True
    
    # ========================================
    # Modbus Data Recording
    # ========================================
    
    def record_system_data(
        self,
        data: Dict[str, Any],
        raw_registers: Optional[List[int]] = None,
    ) -> None:
        """
        Record system-level Modbus data.
        
        Args:
            data: Parsed system data dict
            raw_registers: Raw register values (optional)
        """
        record = ModbusRecord(
            timestamp=datetime.now(timezone.utc),
            source="system",
            data=data,
            raw_registers=raw_registers,
        )
        self._modbus_system.append(record)
        self._latest_system = record
        self._modbus_read_count += 1
        
        logger.debug(f"Recorded system data: SOC={data.get('soc', 'N/A')}%")
    
    def record_rack_data(
        self,
        rack_id: int,
        data: Dict[str, Any],
        raw_registers: Optional[List[int]] = None,
    ) -> None:
        """
        Record rack-level Modbus data.
        
        Args:
            rack_id: Rack number (1-24)
            data: Parsed rack data dict
            raw_registers: Raw register values (optional)
        """
        record = ModbusRecord(
            timestamp=datetime.now(timezone.utc),
            source=f"rack_{rack_id}",
            data=data,
            raw_registers=raw_registers,
        )
        
        if rack_id not in self._modbus_racks:
            self._modbus_racks[rack_id] = deque(maxlen=self._max_records)
        
        self._modbus_racks[rack_id].append(record)
        self._latest_racks[rack_id] = record
        self._modbus_read_count += 1
    
    def record_bms_snapshot(self, snapshot: Any) -> None:
        """
        Record a complete BMS snapshot.
        
        Args:
            snapshot: BMSSnapshot object
        """
        # Record system data
        if hasattr(snapshot, "system"):
            system = snapshot.system
            system_data = {
                "voltage": getattr(system, "total_voltage", 0),
                "current": getattr(system, "total_current", 0),
                "soc": getattr(system, "total_soc", 0),
                "power": getattr(system, "total_power", 0),
                "charge_energy": getattr(system, "charge_energy", 0),
                "discharge_energy": getattr(system, "discharge_energy", 0),
                "remaining_capacity": getattr(system, "remaining_capacity", 0),
                "full_charge_capacity": getattr(system, "full_charge_capacity", 0),
                "active_rack_count": getattr(system, "active_rack_count", 0),
                "max_temperature": getattr(system, "max_temperature", 0),
                "min_temperature": getattr(system, "min_temperature", 0),
                "allowed_charge_power": getattr(system, "allowed_charge_power", 0),
                "allowed_discharge_power": getattr(system, "allowed_discharge_power", 0),
            }
            self.record_system_data(system_data)
        
        # Record rack data
        if hasattr(snapshot, "racks"):
            for rack in snapshot.racks:
                rack_id = getattr(rack, "rack_id", 0)
                rack_data = {
                    "voltage": getattr(rack, "voltage", 0),
                    "current": getattr(rack, "current", 0),
                    "soc": getattr(rack, "soc", 0),
                    "power": getattr(rack, "power", 0),
                    "cell_max_voltage": getattr(rack, "cell_max_voltage", 0),
                    "cell_min_voltage": getattr(rack, "cell_min_voltage", 0),
                    "cell_max_temp": getattr(rack, "cell_max_temp", 0),
                    "cell_min_temp": getattr(rack, "cell_min_temp", 0),
                    "soh": getattr(rack, "soh", 100),
                    "remaining_capacity": getattr(rack, "remaining_capacity", 0),
                    "full_charge_capacity": getattr(rack, "full_charge_capacity", 0),
                }
                self.record_rack_data(rack_id, rack_data)
    
    # ========================================
    # Meter Upload Recording
    # ========================================
    
    def record_meter_upload(
        self,
        mup_href: str,
        description: str,
        readings: List[Dict[str, Any]],
        status_code: int,
        success: bool,
    ) -> None:
        """
        Record a meter upload (MirrorMeterReading).
        
        Args:
            mup_href: MirrorUsagePoint href
            description: Description of the meter
            readings: List of reading values
            status_code: HTTP status code
            success: Whether the upload was successful
        """
        record = MeterUploadRecord(
            timestamp=datetime.now(timezone.utc),
            mup_href=mup_href,
            description=description,
            readings=readings,
            status_code=status_code,
            success=success,
        )
        self._meter_uploads.append(record)
        self._latest_meter = record
        self._meter_upload_count += 1
        
        logger.debug(f"Recorded meter upload to {mup_href}: {len(readings)} readings")
    
    # ========================================
    # DER Status Recording
    # ========================================
    
    def record_der_status(
        self,
        der_path: str,
        status: Dict[str, Any],
        status_code: int,
        success: bool,
    ) -> None:
        """
        Record a DER status upload.
        
        Args:
            der_path: DER path (e.g., /edev/1/der/1)
            status: DER status data
            status_code: HTTP status code
            success: Whether the upload was successful
        """
        record = DERStatusRecord(
            timestamp=datetime.now(timezone.utc),
            der_path=der_path,
            status=status,
            status_code=status_code,
            success=success,
        )
        self._der_status.append(record)
        self._latest_der = record
        self._der_upload_count += 1
        
        logger.debug(f"Recorded DER status to {der_path}")
    
    # ========================================
    # Data Retrieval
    # ========================================
    
    def get_latest_system(self) -> Optional[Dict[str, Any]]:
        """Get the latest system data record."""
        if self._latest_system:
            return self._latest_system.to_dict()
        return None
    
    def get_latest_rack(self, rack_id: int) -> Optional[Dict[str, Any]]:
        """Get the latest data for a specific rack."""
        if rack_id in self._latest_racks:
            return self._latest_racks[rack_id].to_dict()
        return None
    
    def get_latest_racks(self) -> Dict[int, Dict[str, Any]]:
        """Get the latest data for all racks."""
        return {
            rack_id: record.to_dict()
            for rack_id, record in self._latest_racks.items()
        }
    
    def get_latest_meter(self) -> Optional[Dict[str, Any]]:
        """Get the latest meter upload record."""
        if self._latest_meter:
            return self._latest_meter.to_dict()
        return None
    
    def get_latest_der(self) -> Optional[Dict[str, Any]]:
        """Get the latest DER status record."""
        if self._latest_der:
            return self._latest_der.to_dict()
        return None
    
    def get_system_history(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get system data history."""
        records = list(self._modbus_system)[-count:]
        return [r.to_dict() for r in records]
    
    def get_rack_history(self, rack_id: int, count: int = 10) -> List[Dict[str, Any]]:
        """Get rack data history."""
        if rack_id not in self._modbus_racks:
            return []
        records = list(self._modbus_racks[rack_id])[-count:]
        return [r.to_dict() for r in records]
    
    def get_meter_history(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get meter upload history."""
        records = list(self._meter_uploads)[-count:]
        return [r.to_dict() for r in records]
    
    def get_der_history(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get DER status history."""
        records = list(self._der_status)[-count:]
        return [r.to_dict() for r in records]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get data recording statistics."""
        return {
            "modbus_read_count": self._modbus_read_count,
            "meter_upload_count": self._meter_upload_count,
            "der_upload_count": self._der_upload_count,
            "system_records": len(self._modbus_system),
            "rack_count": len(self._modbus_racks),
            "meter_records": len(self._meter_uploads),
            "der_records": len(self._der_status),
            "has_latest_system": self._latest_system is not None,
            "has_latest_meter": self._latest_meter is not None,
            "has_latest_der": self._latest_der is not None,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a complete data summary."""
        return {
            "statistics": self.get_statistics(),
            "latest_system": self.get_latest_system(),
            "latest_racks": self.get_latest_racks(),
            "latest_meter": self.get_latest_meter(),
            "latest_der": self.get_latest_der(),
        }
    
    def clear(self) -> None:
        """Clear all recorded data."""
        self._modbus_system.clear()
        self._modbus_racks.clear()
        self._meter_uploads.clear()
        self._der_status.clear()
        self._latest_system = None
        self._latest_racks.clear()
        self._latest_meter = None
        self._latest_der = None
        self._modbus_read_count = 0
        self._meter_upload_count = 0
        self._der_upload_count = 0
        logger.info("Data recorder cleared")


# Global singleton instance
data_recorder = DataRecorder()


def get_data_recorder() -> DataRecorder:
    """Get the global DataRecorder instance."""
    return data_recorder
