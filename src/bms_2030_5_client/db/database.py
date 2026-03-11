"""
SQLite database for IEEE 2030.5 resources.

Provides persistent storage and quick path lookup for:
- DeviceCapability (/dcap)
- EndDevice (/edev)
- DER (/der)
- DERStatus, DERCapability, DERSettings, DERAvailability
- MirrorUsagePoint (/mup)
- MirrorMeterReading
- FunctionSetAssignments (/fsa)
- DERProgram (/derp)
- Subscription (/sub)

Usage:
    from bms_2030_5_client.db import get_database, init_database
    
    # Initialize database
    db = init_database("data/ieee2030_5.db")
    
    # Or get singleton instance
    db = get_database()
    
    # Store EndDevice
    db.save_end_device(record)
    
    # Quick path lookup
    edev = db.get_end_device_by_href("/edev/1")
    der = db.get_der_by_href("/edev/1/der/1")
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from bms_2030_5_client.db.models import (
    DeviceCapabilityRecord,
    EndDeviceRecord,
    DERRecord,
    DERStatusRecord,
    DERCapabilityRecord,
    DERSettingsRecord,
    DERAvailabilityRecord,
    MirrorUsagePointRecord,
    MirrorMeterReadingRecord,
    FSARecord,
    DERProgramRecord,
    SubscriptionRecord,
    MeterTypeRecord,
    UoMRecord,
)

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "data/ieee2030_5.db"

# Singleton instance
_database: Optional["IEEE2030_5Database"] = None
_lock = threading.Lock()


def get_database() -> "IEEE2030_5Database":
    """Get the singleton database instance."""
    global _database
    if _database is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _database


def init_database(db_path: str = DEFAULT_DB_PATH) -> "IEEE2030_5Database":
    """
    Initialize the database.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        Initialized database instance
    """
    global _database
    with _lock:
        if _database is None:
            _database = IEEE2030_5Database(db_path)
        return _database


class IEEE2030_5Database:
    """
    SQLite database for IEEE 2030.5 resources.
    
    Provides:
    - Persistent storage of all IEEE 2030.5 resources
    - Quick path (href) lookup
    - Automatic table creation
    - Thread-safe operations
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-local storage for connections
        self._local = threading.local()
        
        # Initialize schema
        self._init_schema()
        
        logger.info(f"IEEE2030_5Database initialized: {self.db_path}")
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
        
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise
    
    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # DeviceCapability table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_capability (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_url TEXT NOT NULL,
                    href TEXT NOT NULL DEFAULT '/dcap',
                    poll_rate INTEGER DEFAULT 900,
                    end_device_list_link TEXT,
                    mirror_usage_point_list_link TEXT,
                    self_device_link TEXT,
                    time_link TEXT,
                    der_program_list_link TEXT,
                    response_set_list_link TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(server_url)
                )
            """)
            
            # EndDevice table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS end_device (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    href TEXT NOT NULL UNIQUE,
                    lfdi TEXT,
                    sfdi INTEGER,
                    changed_time INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    der_list_link TEXT,
                    device_information_link TEXT,
                    fsa_list_link TEXT,
                    registration_link TEXT,
                    power_status_link TEXT,
                    device_status_link TEXT,
                    log_event_list_link TEXT,
                    subscription_list_link TEXT,
                    response_set_list_link TEXT,
                    mf_id INTEGER,
                    mf_model TEXT,
                    mf_serial_number TEXT,
                    mf_hw_ver TEXT,
                    sw_ver TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # DER table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS der (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    href TEXT NOT NULL UNIQUE,
                    mrid TEXT,
                    description TEXT,
                    version INTEGER,
                    end_device_href TEXT,
                    der_capability_link TEXT,
                    der_settings_link TEXT,
                    der_status_link TEXT,
                    der_availability_link TEXT,
                    associated_der_program_list_link TEXT,
                    current_der_program_link TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (end_device_href) REFERENCES end_device(href)
                )
            """)
            
            # DERStatus table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS der_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    der_href TEXT NOT NULL,
                    href TEXT,
                    reading_time INTEGER DEFAULT 0,
                    alarm_status TEXT,
                    gen_connect_status TEXT,
                    inverter_status TEXT,
                    operational_mode_status TEXT,
                    state_of_charge INTEGER,
                    state_of_charge_time INTEGER,
                    stor_mode_status TEXT,
                    stor_connect_status TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (der_href) REFERENCES der(href)
                )
            """)
            
            # DERCapability table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS der_capability (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    der_href TEXT NOT NULL,
                    href TEXT,
                    modes_supported INTEGER DEFAULT 0,
                    der_type INTEGER DEFAULT 7,
                    rtg_max_w INTEGER,
                    rtg_max_w_multiplier INTEGER DEFAULT 0,
                    rtg_max_var INTEGER,
                    rtg_max_charge_rate_w INTEGER,
                    rtg_max_discharge_rate_w INTEGER,
                    rtg_max_charge_rate_va INTEGER,
                    rtg_max_discharge_rate_va INTEGER,
                    rtg_ah INTEGER,
                    rtg_wh INTEGER,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (der_href) REFERENCES der(href)
                )
            """)
            
            # DERSettings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS der_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    der_href TEXT NOT NULL,
                    href TEXT,
                    updated_time INTEGER,
                    set_grad_w INTEGER,
                    set_max_w INTEGER,
                    set_max_w_multiplier INTEGER DEFAULT 0,
                    set_max_var INTEGER,
                    set_max_charge_rate_w INTEGER,
                    set_max_discharge_rate_w INTEGER,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (der_href) REFERENCES der(href)
                )
            """)
            
            # DERAvailability table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS der_availability (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    der_href TEXT NOT NULL,
                    href TEXT,
                    reading_time INTEGER DEFAULT 0,
                    availability_duration INTEGER,
                    max_charge_duration INTEGER,
                    reserve_charge_percent INTEGER,
                    reserve_percent INTEGER,
                    stat_w_avail INTEGER,
                    stat_var_avail INTEGER,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (der_href) REFERENCES der(href)
                )
            """)
            
            # MirrorUsagePoint table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mirror_usage_point (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    href TEXT NOT NULL UNIQUE,
                    mrid TEXT,
                    description TEXT,
                    version INTEGER,
                    role_flags TEXT DEFAULT '0009',
                    service_category_kind INTEGER DEFAULT 0,
                    status INTEGER DEFAULT 1,
                    device_lfdi TEXT,
                    post_rate INTEGER DEFAULT 900,
                    meter_name TEXT,
                    meter_type TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # MirrorMeterReading table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mirror_meter_reading (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mup_href TEXT NOT NULL,
                    href TEXT,
                    mrid TEXT,
                    description TEXT,
                    reading_type_href TEXT,
                    accumulation_behaviour INTEGER DEFAULT 0,
                    commodity INTEGER DEFAULT 1,
                    data_qualifier INTEGER DEFAULT 0,
                    flow_direction INTEGER DEFAULT 0,
                    kind INTEGER DEFAULT 0,
                    phase INTEGER,
                    power_of_ten_multiplier INTEGER DEFAULT 0,
                    uom INTEGER DEFAULT 0,
                    last_value INTEGER,
                    last_reading_time INTEGER,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(mup_href, description),
                    FOREIGN KEY (mup_href) REFERENCES mirror_usage_point(href)
                )
            """)
            
            # FSA table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fsa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    href TEXT NOT NULL UNIQUE,
                    mrid TEXT,
                    description TEXT,
                    end_device_href TEXT,
                    der_program_list_link TEXT,
                    time_link TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (end_device_href) REFERENCES end_device(href)
                )
            """)
            
            # DERProgram table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS der_program (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    href TEXT NOT NULL UNIQUE,
                    mrid TEXT,
                    description TEXT,
                    version INTEGER,
                    fsa_href TEXT,
                    primacy INTEGER DEFAULT 0,
                    der_control_list_link TEXT,
                    active_der_control_list_link TEXT,
                    default_der_control_link TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (fsa_href) REFERENCES fsa(href)
                )
            """)
            
            # Subscription table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscription (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    href TEXT NOT NULL UNIQUE,
                    subscribed_resource TEXT NOT NULL,
                    notification_uri TEXT NOT NULL,
                    encoding INTEGER DEFAULT 0,
                    level TEXT DEFAULT '+S2',
                    limit_count INTEGER DEFAULT 10,
                    state TEXT DEFAULT 'disabled',
                    last_renewed_at TIMESTAMP,
                    next_renewal_at TIMESTAMP,
                    renewal_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    raw_xml TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Meter types table - stores configured meter reading types (without values)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS uom (
                    code INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT
                )
            """)
            
            # Insert IEEE 2030.5 standard UoM values
            uom_data = [
                (0, "N/A", "Not Applicable", "不適用，若未指定則為預設值", "Other"),
                (5, "A", "Amperes", "安培：電流的均方根值 (RMS)", "Current"),
                (6, "K", "Kelvin", "克耳文：絕對溫度單位", "Temperature"),
                (23, "°C", "Celsius", "攝氏度：相對溫度單位", "Temperature"),
                (29, "V", "Volts", "電壓：單位為伏特", "Voltage"),
                (31, "J", "Joules", "焦耳：能量單位", "Energy"),
                (33, "Hz", "Hertz", "赫茲：頻率單位", "Frequency"),
                (38, "W", "Watts", "瓦特：實功功率 (Real power)", "Power"),
                (42, "m³", "Cubic Meters", "立方公尺：體積單位", "Volume"),
                (61, "VA", "Volt-Amperes", "伏安：視在功率 (Apparent power)", "Power"),
                (63, "var", "Volt-Amperes Reactive", "乏：虛功功率 (Reactive power)", "Power"),
                (65, "cosθ", "Power Factor", "位移功率因數 (Displacement Power Factor)", "Power Factor"),
                (67, "V²", "Volts Squared", "伏特平方", "Voltage"),
                (69, "A²", "Amperes Squared", "安培平方", "Current"),
                (71, "VAh", "Volt-Ampere Hours", "伏安小時：視在能量", "Energy"),
                (72, "Wh", "Watt Hours", "瓦時：實功能量", "Energy"),
                (73, "varh", "Var Hours", "乏時：虛功能量", "Energy"),
                (106, "Ah", "Ampere Hours", "安培小時：可用電荷量", "Capacity"),
                (119, "ft³", "Cubic Feet", "立方英尺：體積單位", "Volume"),
                (122, "ft³/h", "Cubic Feet per Hour", "立方英尺/小時：流率單位", "Flow Rate"),
                (125, "m³/h", "Cubic Meters per Hour", "立方公尺/小時：流率單位", "Flow Rate"),
                (128, "US gal", "US Gallons", "美制加侖：用於水資源計量", "Volume"),
                (129, "US gal/h", "US Gallons per Hour", "美制加侖/小時", "Flow Rate"),
                (130, "IMP gal", "Imperial Gallons", "英制加侖", "Volume"),
                (131, "IMP gal/h", "Imperial Gallons per Hour", "英制加侖/小時", "Flow Rate"),
                (132, "BTU", "British Thermal Units", "英熱單位", "Energy"),
                (133, "BTU/h", "BTU per Hour", "英熱單位/小時", "Power"),
                (134, "L", "Liters", "公升：用於水資源計量", "Volume"),
                (137, "L/h", "Liters per Hour", "公升/小時", "Flow Rate"),
                (140, "Pa(g)", "Pascals Gauge", "表壓力：單位為帕斯卡", "Pressure"),
                (155, "Pa(a)", "Pascals Absolute", "絕對壓力：單位為帕斯卡", "Pressure"),
                (169, "thm", "Therms", "撒姆：熱量單位", "Energy"),
            ]
            cursor.executemany(
                "INSERT OR IGNORE INTO uom (code, symbol, name, description, category) VALUES (?, ?, ?, ?, ?)",
                uom_data
            )
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meter_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mup_href TEXT NOT NULL,
                    description TEXT NOT NULL,
                    mrid TEXT,
                    uom_code INTEGER DEFAULT 0,
                    kind INTEGER DEFAULT 0,
                    commodity INTEGER DEFAULT 1,
                    flow_direction INTEGER DEFAULT 0,
                    accumulation_behaviour INTEGER DEFAULT 0,
                    power_of_ten_multiplier INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(mup_href, description),
                    FOREIGN KEY (mup_href) REFERENCES mirror_usage_point(href),
                    FOREIGN KEY (uom_code) REFERENCES uom(code)
                )
            """)
            
            # Create indexes for fast path lookup
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_end_device_sfdi ON end_device(sfdi)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_end_device_lfdi ON end_device(lfdi)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_der_end_device ON der(end_device_href)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mup_lfdi ON mirror_usage_point(device_lfdi)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fsa_end_device ON fsa(end_device_href)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_derp_fsa ON der_program(fsa_href)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_meter_types_mup ON meter_types(mup_href)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mmr_mup ON mirror_meter_reading(mup_href)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mmr_mup_desc ON mirror_meter_reading(mup_href, description)")
            
            conn.commit()
            logger.debug("Database schema initialized")
        
        # Run migrations for existing databases
        self._run_migrations()
    
    def _run_migrations(self) -> None:
        """Run database migrations for schema updates."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if meter_types table needs migration (add mrid column)
            cursor.execute("PRAGMA table_info(meter_types)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if "mrid" not in columns:
                logger.info("Migrating meter_types table: adding mrid column")
                cursor.execute("ALTER TABLE meter_types ADD COLUMN mrid TEXT")
            
            if "accumulation_behaviour" not in columns:
                logger.info("Migrating meter_types table: adding accumulation_behaviour column")
                cursor.execute("ALTER TABLE meter_types ADD COLUMN accumulation_behaviour INTEGER DEFAULT 0")
            
            if "power_of_ten_multiplier" not in columns:
                logger.info("Migrating meter_types table: adding power_of_ten_multiplier column")
                cursor.execute("ALTER TABLE meter_types ADD COLUMN power_of_ten_multiplier INTEGER DEFAULT 0")
            
            conn.commit()
            logger.debug("Database migrations completed")
    
    # =========================================================================
    # DeviceCapability Operations
    # =========================================================================
    
    def save_device_capability(self, record: DeviceCapabilityRecord) -> int:
        """Save or update DeviceCapability."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO device_capability (
                    server_url, href, poll_rate, end_device_list_link,
                    mirror_usage_point_list_link, self_device_link, time_link,
                    der_program_list_link, response_set_list_link, raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(server_url) DO UPDATE SET
                    href = excluded.href,
                    poll_rate = excluded.poll_rate,
                    end_device_list_link = excluded.end_device_list_link,
                    mirror_usage_point_list_link = excluded.mirror_usage_point_list_link,
                    self_device_link = excluded.self_device_link,
                    time_link = excluded.time_link,
                    der_program_list_link = excluded.der_program_list_link,
                    response_set_list_link = excluded.response_set_list_link,
                    raw_xml = excluded.raw_xml,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.server_url, record.href, record.poll_rate,
                record.end_device_list_link, record.mirror_usage_point_list_link,
                record.self_device_link, record.time_link,
                record.der_program_list_link, record.response_set_list_link,
                record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_device_capability(self, server_url: str) -> Optional[DeviceCapabilityRecord]:
        """Get DeviceCapability by server URL."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM device_capability WHERE server_url = ?",
                (server_url,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_device_capability(row)
            return None
    
    def _row_to_device_capability(self, row: sqlite3.Row) -> DeviceCapabilityRecord:
        """Convert database row to DeviceCapabilityRecord."""
        return DeviceCapabilityRecord(
            id=row["id"],
            server_url=row["server_url"],
            href=row["href"],
            poll_rate=row["poll_rate"],
            end_device_list_link=row["end_device_list_link"],
            mirror_usage_point_list_link=row["mirror_usage_point_list_link"],
            self_device_link=row["self_device_link"],
            time_link=row["time_link"],
            der_program_list_link=row["der_program_list_link"],
            response_set_list_link=row["response_set_list_link"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # EndDevice Operations
    # =========================================================================
    
    def save_end_device(self, record: EndDeviceRecord) -> int:
        """Save or update EndDevice."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO end_device (
                    href, lfdi, sfdi, changed_time, enabled,
                    der_list_link, device_information_link, fsa_list_link,
                    registration_link, power_status_link, device_status_link,
                    log_event_list_link, subscription_list_link, response_set_list_link,
                    mf_id, mf_model, mf_serial_number, mf_hw_ver, sw_ver,
                    raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(href) DO UPDATE SET
                    lfdi = excluded.lfdi,
                    sfdi = excluded.sfdi,
                    changed_time = excluded.changed_time,
                    enabled = excluded.enabled,
                    der_list_link = excluded.der_list_link,
                    device_information_link = excluded.device_information_link,
                    fsa_list_link = excluded.fsa_list_link,
                    registration_link = excluded.registration_link,
                    power_status_link = excluded.power_status_link,
                    device_status_link = excluded.device_status_link,
                    log_event_list_link = excluded.log_event_list_link,
                    subscription_list_link = excluded.subscription_list_link,
                    response_set_list_link = excluded.response_set_list_link,
                    mf_id = excluded.mf_id,
                    mf_model = excluded.mf_model,
                    mf_serial_number = excluded.mf_serial_number,
                    mf_hw_ver = excluded.mf_hw_ver,
                    sw_ver = excluded.sw_ver,
                    raw_xml = excluded.raw_xml,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.href, record.lfdi, record.sfdi, record.changed_time,
                1 if record.enabled else 0, record.der_list_link,
                record.device_information_link, record.fsa_list_link,
                record.registration_link, record.power_status_link,
                record.device_status_link, record.log_event_list_link,
                record.subscription_list_link, record.response_set_list_link,
                record.mf_id, record.mf_model, record.mf_serial_number,
                record.mf_hw_ver, record.sw_ver, record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_end_device_by_href(self, href: str) -> Optional[EndDeviceRecord]:
        """Get EndDevice by href path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM end_device WHERE href = ?", (href,))
            row = cursor.fetchone()
            if row:
                return self._row_to_end_device(row)
            return None
    
    def get_end_device_by_sfdi(self, sfdi: int) -> Optional[EndDeviceRecord]:
        """Get EndDevice by sFDI."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM end_device WHERE sfdi = ?", (sfdi,))
            row = cursor.fetchone()
            if row:
                return self._row_to_end_device(row)
            return None
    
    def get_end_device_by_lfdi(self, lfdi: str) -> Optional[EndDeviceRecord]:
        """Get EndDevice by lFDI."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM end_device WHERE lfdi = ?", (lfdi,))
            row = cursor.fetchone()
            if row:
                return self._row_to_end_device(row)
            return None
    
    def get_all_end_devices(self) -> List[EndDeviceRecord]:
        """Get all EndDevices."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM end_device ORDER BY id")
            return [self._row_to_end_device(row) for row in cursor.fetchall()]
    
    def _row_to_end_device(self, row: sqlite3.Row) -> EndDeviceRecord:
        """Convert database row to EndDeviceRecord."""
        return EndDeviceRecord(
            id=row["id"],
            href=row["href"],
            lfdi=row["lfdi"],
            sfdi=row["sfdi"],
            changed_time=row["changed_time"],
            enabled=bool(row["enabled"]),
            der_list_link=row["der_list_link"],
            device_information_link=row["device_information_link"],
            fsa_list_link=row["fsa_list_link"],
            registration_link=row["registration_link"],
            power_status_link=row["power_status_link"],
            device_status_link=row["device_status_link"],
            log_event_list_link=row["log_event_list_link"],
            subscription_list_link=row["subscription_list_link"],
            response_set_list_link=row["response_set_list_link"],
            mf_id=row["mf_id"],
            mf_model=row["mf_model"],
            mf_serial_number=row["mf_serial_number"],
            mf_hw_ver=row["mf_hw_ver"],
            sw_ver=row["sw_ver"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # DER Operations
    # =========================================================================
    
    def save_der(self, record: DERRecord) -> int:
        """Save or update DER."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO der (
                    href, mrid, description, version, end_device_href,
                    der_capability_link, der_settings_link, der_status_link,
                    der_availability_link, associated_der_program_list_link,
                    current_der_program_link, raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(href) DO UPDATE SET
                    mrid = excluded.mrid,
                    description = excluded.description,
                    version = excluded.version,
                    end_device_href = excluded.end_device_href,
                    der_capability_link = excluded.der_capability_link,
                    der_settings_link = excluded.der_settings_link,
                    der_status_link = excluded.der_status_link,
                    der_availability_link = excluded.der_availability_link,
                    associated_der_program_list_link = excluded.associated_der_program_list_link,
                    current_der_program_link = excluded.current_der_program_link,
                    raw_xml = excluded.raw_xml,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.href, record.mrid, record.description, record.version,
                record.end_device_href, record.der_capability_link,
                record.der_settings_link, record.der_status_link,
                record.der_availability_link, record.associated_der_program_list_link,
                record.current_der_program_link, record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_der_by_href(self, href: str) -> Optional[DERRecord]:
        """Get DER by href path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM der WHERE href = ?", (href,))
            row = cursor.fetchone()
            if row:
                return self._row_to_der(row)
            return None
    
    def get_ders_by_end_device(self, end_device_href: str) -> List[DERRecord]:
        """Get all DERs for an EndDevice."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM der WHERE end_device_href = ? ORDER BY id",
                (end_device_href,)
            )
            return [self._row_to_der(row) for row in cursor.fetchall()]
    
    def get_all_ders(self) -> List[DERRecord]:
        """Get all DERs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM der ORDER BY id")
            return [self._row_to_der(row) for row in cursor.fetchall()]
    
    def _row_to_der(self, row: sqlite3.Row) -> DERRecord:
        """Convert database row to DERRecord."""
        return DERRecord(
            id=row["id"],
            href=row["href"],
            mrid=row["mrid"],
            description=row["description"],
            version=row["version"],
            end_device_href=row["end_device_href"],
            der_capability_link=row["der_capability_link"],
            der_settings_link=row["der_settings_link"],
            der_status_link=row["der_status_link"],
            der_availability_link=row["der_availability_link"],
            associated_der_program_list_link=row["associated_der_program_list_link"],
            current_der_program_link=row["current_der_program_link"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # MirrorUsagePoint Operations
    # =========================================================================
    
    def save_mirror_usage_point(self, record: MirrorUsagePointRecord) -> int:
        """Save or update MirrorUsagePoint."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO mirror_usage_point (
                    href, mrid, description, version, role_flags,
                    service_category_kind, status, device_lfdi, post_rate,
                    meter_name, meter_type, raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(href) DO UPDATE SET
                    mrid = excluded.mrid,
                    description = excluded.description,
                    version = excluded.version,
                    role_flags = excluded.role_flags,
                    service_category_kind = excluded.service_category_kind,
                    status = excluded.status,
                    device_lfdi = excluded.device_lfdi,
                    post_rate = excluded.post_rate,
                    meter_name = excluded.meter_name,
                    meter_type = excluded.meter_type,
                    raw_xml = excluded.raw_xml,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.href, record.mrid, record.description, record.version,
                record.role_flags, record.service_category_kind, record.status,
                record.device_lfdi, record.post_rate, record.meter_name,
                record.meter_type, record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_mirror_usage_point_by_href(self, href: str) -> Optional[MirrorUsagePointRecord]:
        """Get MirrorUsagePoint by href path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mirror_usage_point WHERE href = ?", (href,))
            row = cursor.fetchone()
            if row:
                return self._row_to_mup(row)
            return None
    
    def get_mirror_usage_points_by_lfdi(self, device_lfdi: str) -> List[MirrorUsagePointRecord]:
        """Get all MirrorUsagePoints for a device."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM mirror_usage_point WHERE device_lfdi = ? ORDER BY id",
                (device_lfdi,)
            )
            return [self._row_to_mup(row) for row in cursor.fetchall()]
    
    def get_all_mirror_usage_points(self) -> List[MirrorUsagePointRecord]:
        """Get all MirrorUsagePoints."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mirror_usage_point ORDER BY id")
            return [self._row_to_mup(row) for row in cursor.fetchall()]
    
    def delete_mirror_usage_point(self, href: str) -> bool:
        """Delete MirrorUsagePoint by href."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # First delete related readings
            cursor.execute("DELETE FROM mirror_meter_reading WHERE mup_href = ?", (href,))
            cursor.execute("DELETE FROM mirror_usage_point WHERE href = ?", (href,))
            conn.commit()
            return cursor.rowcount > 0
    
    def _row_to_mup(self, row: sqlite3.Row) -> MirrorUsagePointRecord:
        """Convert database row to MirrorUsagePointRecord."""
        return MirrorUsagePointRecord(
            id=row["id"],
            href=row["href"],
            mrid=row["mrid"],
            description=row["description"],
            version=row["version"],
            role_flags=row["role_flags"],
            service_category_kind=row["service_category_kind"],
            status=row["status"],
            device_lfdi=row["device_lfdi"],
            post_rate=row["post_rate"],
            meter_name=row["meter_name"],
            meter_type=row["meter_type"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # MirrorMeterReading Operations
    # =========================================================================
    
    def save_mirror_meter_reading(self, record: MirrorMeterReadingRecord) -> int:
        """Save or update MirrorMeterReading.
        
        Uses mup_href + description as unique key for upsert.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Always use mup_href + description as unique key for upsert
            cursor.execute("""
                INSERT INTO mirror_meter_reading (
                    mup_href, href, mrid, description, reading_type_href,
                    accumulation_behaviour, commodity, data_qualifier,
                    flow_direction, kind, phase, power_of_ten_multiplier,
                    uom, last_value, last_reading_time, raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(mup_href, description) DO UPDATE SET
                    href = COALESCE(excluded.href, href),
                    mrid = COALESCE(excluded.mrid, mrid),
                    reading_type_href = COALESCE(excluded.reading_type_href, reading_type_href),
                    accumulation_behaviour = excluded.accumulation_behaviour,
                    commodity = excluded.commodity,
                    data_qualifier = excluded.data_qualifier,
                    flow_direction = excluded.flow_direction,
                    kind = excluded.kind,
                    phase = excluded.phase,
                    power_of_ten_multiplier = excluded.power_of_ten_multiplier,
                    uom = excluded.uom,
                    last_value = COALESCE(excluded.last_value, last_value),
                    last_reading_time = COALESCE(excluded.last_reading_time, last_reading_time),
                    raw_xml = COALESCE(excluded.raw_xml, raw_xml),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.mup_href, record.href, record.mrid, record.description,
                record.reading_type_href, record.accumulation_behaviour,
                record.commodity, record.data_qualifier, record.flow_direction,
                record.kind, record.phase, record.power_of_ten_multiplier,
                record.uom, record.last_value, record.last_reading_time, record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_reading_by_description(self, mup_href: str, description: str) -> Optional[MirrorMeterReadingRecord]:
        """Get MirrorMeterReading by mup_href and description."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM mirror_meter_reading WHERE mup_href = ? AND description = ?",
                (mup_href, description)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_mmr(row)
            return None
    
    def get_readings_by_mup(self, mup_href: str) -> List[MirrorMeterReadingRecord]:
        """Get all readings for a MirrorUsagePoint."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM mirror_meter_reading WHERE mup_href = ? ORDER BY id",
                (mup_href,)
            )
            return [self._row_to_mmr(row) for row in cursor.fetchall()]
    
    def _row_to_mmr(self, row: sqlite3.Row) -> MirrorMeterReadingRecord:
        """Convert database row to MirrorMeterReadingRecord."""
        return MirrorMeterReadingRecord(
            id=row["id"],
            mup_href=row["mup_href"],
            href=row["href"],
            mrid=row["mrid"],
            description=row["description"],
            reading_type_href=row["reading_type_href"],
            accumulation_behaviour=row["accumulation_behaviour"],
            commodity=row["commodity"],
            data_qualifier=row["data_qualifier"],
            flow_direction=row["flow_direction"],
            kind=row["kind"],
            phase=row["phase"],
            power_of_ten_multiplier=row["power_of_ten_multiplier"],
            uom=row["uom"],
            last_value=row["last_value"],
            last_reading_time=row["last_reading_time"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # FSA Operations
    # =========================================================================
    
    def save_fsa(self, record: FSARecord) -> int:
        """Save or update FSA."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO fsa (
                    href, mrid, description, end_device_href,
                    der_program_list_link, time_link, raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(href) DO UPDATE SET
                    mrid = excluded.mrid,
                    description = excluded.description,
                    end_device_href = excluded.end_device_href,
                    der_program_list_link = excluded.der_program_list_link,
                    time_link = excluded.time_link,
                    raw_xml = excluded.raw_xml,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.href, record.mrid, record.description,
                record.end_device_href, record.der_program_list_link,
                record.time_link, record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_fsa_by_href(self, href: str) -> Optional[FSARecord]:
        """Get FSA by href path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM fsa WHERE href = ?", (href,))
            row = cursor.fetchone()
            if row:
                return self._row_to_fsa(row)
            return None
    
    def get_fsas_by_end_device(self, end_device_href: str) -> List[FSARecord]:
        """Get all FSAs for an EndDevice."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM fsa WHERE end_device_href = ? ORDER BY id",
                (end_device_href,)
            )
            return [self._row_to_fsa(row) for row in cursor.fetchall()]
    
    def _row_to_fsa(self, row: sqlite3.Row) -> FSARecord:
        """Convert database row to FSARecord."""
        return FSARecord(
            id=row["id"],
            href=row["href"],
            mrid=row["mrid"],
            description=row["description"],
            end_device_href=row["end_device_href"],
            der_program_list_link=row["der_program_list_link"],
            time_link=row["time_link"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # DERProgram Operations
    # =========================================================================
    
    def save_der_program(self, record: DERProgramRecord) -> int:
        """Save or update DERProgram."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO der_program (
                    href, mrid, description, version, fsa_href, primacy,
                    der_control_list_link, active_der_control_list_link,
                    default_der_control_link, raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(href) DO UPDATE SET
                    mrid = excluded.mrid,
                    description = excluded.description,
                    version = excluded.version,
                    fsa_href = excluded.fsa_href,
                    primacy = excluded.primacy,
                    der_control_list_link = excluded.der_control_list_link,
                    active_der_control_list_link = excluded.active_der_control_list_link,
                    default_der_control_link = excluded.default_der_control_link,
                    raw_xml = excluded.raw_xml,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.href, record.mrid, record.description, record.version,
                record.fsa_href, record.primacy, record.der_control_list_link,
                record.active_der_control_list_link, record.default_der_control_link,
                record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_der_program_by_href(self, href: str) -> Optional[DERProgramRecord]:
        """Get DERProgram by href path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM der_program WHERE href = ?", (href,))
            row = cursor.fetchone()
            if row:
                return self._row_to_derp(row)
            return None
    
    def get_der_programs_by_fsa(self, fsa_href: str) -> List[DERProgramRecord]:
        """Get all DERPrograms for an FSA."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM der_program WHERE fsa_href = ? ORDER BY primacy",
                (fsa_href,)
            )
            return [self._row_to_derp(row) for row in cursor.fetchall()]
    
    def _row_to_derp(self, row: sqlite3.Row) -> DERProgramRecord:
        """Convert database row to DERProgramRecord."""
        return DERProgramRecord(
            id=row["id"],
            href=row["href"],
            mrid=row["mrid"],
            description=row["description"],
            version=row["version"],
            fsa_href=row["fsa_href"],
            primacy=row["primacy"],
            der_control_list_link=row["der_control_list_link"],
            active_der_control_list_link=row["active_der_control_list_link"],
            default_der_control_link=row["default_der_control_link"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # Subscription Operations
    # =========================================================================
    
    def save_subscription(self, record: SubscriptionRecord) -> int:
        """Save or update Subscription."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO subscription (
                    href, subscribed_resource, notification_uri, encoding,
                    level, limit_count, state, last_renewed_at, next_renewal_at,
                    renewal_count, failure_count, last_error, raw_xml, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(href) DO UPDATE SET
                    subscribed_resource = excluded.subscribed_resource,
                    notification_uri = excluded.notification_uri,
                    encoding = excluded.encoding,
                    level = excluded.level,
                    limit_count = excluded.limit_count,
                    state = excluded.state,
                    last_renewed_at = excluded.last_renewed_at,
                    next_renewal_at = excluded.next_renewal_at,
                    renewal_count = excluded.renewal_count,
                    failure_count = excluded.failure_count,
                    last_error = excluded.last_error,
                    raw_xml = excluded.raw_xml,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.href, record.subscribed_resource, record.notification_uri,
                record.encoding, record.level, record.limit, record.state,
                record.last_renewed_at, record.next_renewal_at, record.renewal_count,
                record.failure_count, record.last_error, record.raw_xml,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_subscription_by_href(self, href: str) -> Optional[SubscriptionRecord]:
        """Get Subscription by href path."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscription WHERE href = ?", (href,))
            row = cursor.fetchone()
            if row:
                return self._row_to_sub(row)
            return None
    
    def get_all_subscriptions(self) -> List[SubscriptionRecord]:
        """Get all Subscriptions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscription ORDER BY id")
            return [self._row_to_sub(row) for row in cursor.fetchall()]
    
    def _row_to_sub(self, row: sqlite3.Row) -> SubscriptionRecord:
        """Convert database row to SubscriptionRecord."""
        return SubscriptionRecord(
            id=row["id"],
            href=row["href"],
            subscribed_resource=row["subscribed_resource"],
            notification_uri=row["notification_uri"],
            encoding=row["encoding"],
            level=row["level"],
            limit=row["limit_count"],
            state=row["state"],
            renewal_count=row["renewal_count"],
            failure_count=row["failure_count"],
            last_error=row["last_error"],
            raw_xml=row["raw_xml"],
        )
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_resource_by_path(self, path: str) -> Optional[dict]:
        """
        Get any resource by its path (quick lookup).
        
        This is the main method for fast path-based access.
        
        Args:
            path: Resource path (e.g., /edev/1, /edev/1/der/1)
            
        Returns:
            Resource dict or None if not found
        """
        # Try each resource type
        if path.startswith("/dcap"):
            # Device capability doesn't have unique href, need server_url
            return None
        
        # EndDevice
        if "/der/" not in path and "/fsa/" not in path and path.startswith("/edev/"):
            edev = self.get_end_device_by_href(path)
            if edev:
                return edev.to_dict()
        
        # DER
        if "/der/" in path:
            der = self.get_der_by_href(path)
            if der:
                return der.to_dict()
        
        # MirrorUsagePoint
        if path.startswith("/mup/"):
            mup = self.get_mirror_usage_point_by_href(path)
            if mup:
                return mup.to_dict()
        
        # FSA
        if "/fsa/" in path and "/derp/" not in path:
            fsa = self.get_fsa_by_href(path)
            if fsa:
                return fsa.to_dict()
        
        # DERProgram
        if "/derp/" in path:
            derp = self.get_der_program_by_href(path)
            if derp:
                return derp.to_dict()
        
        # Subscription
        if "/sub/" in path:
            sub = self.get_subscription_by_href(path)
            if sub:
                return sub.to_dict()
        
        return None
    
    # =========================================================================
    # UoM (Unit of Measure) Operations
    # =========================================================================
    
    def get_uom(self, code: int) -> Optional[UoMRecord]:
        """Get a UoM record by code."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM uom WHERE code = ?", (code,))
            row = cursor.fetchone()
            if row:
                return UoMRecord(
                    code=row["code"],
                    symbol=row["symbol"],
                    name=row["name"],
                    description=row["description"],
                    category=row["category"],
                )
            return None
    
    def get_all_uom(self) -> List[UoMRecord]:
        """Get all UoM records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM uom ORDER BY code")
            rows = cursor.fetchall()
            return [
                UoMRecord(
                    code=row["code"],
                    symbol=row["symbol"],
                    name=row["name"],
                    description=row["description"],
                    category=row["category"],
                )
                for row in rows
            ]
    
    def get_uom_by_category(self, category: str) -> List[UoMRecord]:
        """Get all UoM records in a category."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM uom WHERE category = ? ORDER BY code", (category,))
            rows = cursor.fetchall()
            return [
                UoMRecord(
                    code=row["code"],
                    symbol=row["symbol"],
                    name=row["name"],
                    description=row["description"],
                    category=row["category"],
                )
                for row in rows
            ]
    
    # =========================================================================
    # Meter Types Operations
    # =========================================================================
    
    def save_meter_type(self, record: MeterTypeRecord) -> int:
        """Save or update a meter type record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO meter_types (
                    mup_href, description, mrid, uom_code, kind,
                    commodity, flow_direction, accumulation_behaviour,
                    power_of_ten_multiplier, is_active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(mup_href, description) DO UPDATE SET
                    mrid = excluded.mrid,
                    uom_code = excluded.uom_code,
                    kind = excluded.kind,
                    commodity = excluded.commodity,
                    flow_direction = excluded.flow_direction,
                    accumulation_behaviour = excluded.accumulation_behaviour,
                    power_of_ten_multiplier = excluded.power_of_ten_multiplier,
                    is_active = excluded.is_active,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record.mup_href, record.description, record.mrid,
                record.uom_code, record.kind, record.commodity,
                record.flow_direction, record.accumulation_behaviour,
                record.power_of_ten_multiplier, 1 if record.is_active else 0,
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_meter_types(self, mup_href: Optional[str] = None) -> List[MeterTypeRecord]:
        """Get meter types with joined UoM data, optionally filtered by MUP href."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT mt.*, u.symbol as uom_symbol, u.name as uom_name
                FROM meter_types mt
                LEFT JOIN uom u ON mt.uom_code = u.code
            """
            
            if mup_href:
                query += " WHERE mt.mup_href = ? ORDER BY mt.description"
                cursor.execute(query, (mup_href,))
            else:
                query += " ORDER BY mt.mup_href, mt.description"
                cursor.execute(query)
            
            rows = cursor.fetchall()
            return [self._row_to_meter_type(row) for row in rows]
    
    def get_active_meter_types(self, mup_href: str) -> List[MeterTypeRecord]:
        """Get active meter types for a MUP with joined UoM data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT mt.*, u.symbol as uom_symbol, u.name as uom_name
                FROM meter_types mt
                LEFT JOIN uom u ON mt.uom_code = u.code
                WHERE mt.mup_href = ? AND mt.is_active = 1
                ORDER BY mt.description
            """, (mup_href,))
            rows = cursor.fetchall()
            return [self._row_to_meter_type(row) for row in rows]
    
    def update_meter_types_from_readings(self, mup_href: str, readings: List[dict]) -> int:
        """
        Update meter types based on readings from an upload.
        
        This extracts the meter type info (description, uom, etc.) from readings
        and saves them to the meter_types table.
        
        Args:
            mup_href: MirrorUsagePoint href
            readings: List of reading dicts with 'description', 'uom', 'uom_code', 
                      'mrid', 'accumulation_behaviour', 'power_of_ten_multiplier', etc.
            
        Returns:
            Number of meter types updated/inserted
        """
        count = 0
        for reading in readings:
            description = reading.get("description") or reading.get("type")
            if not description:
                continue
            
            record = MeterTypeRecord(
                mup_href=mup_href,
                description=description,
                mrid=reading.get("mrid"),
                uom_code=reading.get("uom_code", 0) or 0,
                kind=reading.get("kind", 0) or 0,
                commodity=reading.get("commodity", 1) or 1,
                flow_direction=reading.get("flow_direction", 0) or 0,
                accumulation_behaviour=reading.get("accumulation_behaviour", 0) or 0,
                power_of_ten_multiplier=reading.get("power_of_ten_multiplier", 0) or 0,
                is_active=True,
            )
            self.save_meter_type(record)
            count += 1
        
        return count
    
    def delete_meter_type(self, mup_href: str, description: str) -> bool:
        """Delete a meter type by MUP href and description."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM meter_types WHERE mup_href = ? AND description = ?",
                (mup_href, description)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def clear_meter_types(self, mup_href: Optional[str] = None) -> int:
        """Clear meter types, optionally for a specific MUP."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if mup_href:
                cursor.execute("DELETE FROM meter_types WHERE mup_href = ?", (mup_href,))
            else:
                cursor.execute("DELETE FROM meter_types")
            conn.commit()
            return cursor.rowcount
    
    def initialize_default_meter_types(self, mup_href: str) -> int:
        """
        Initialize default meter types for a MirrorUsagePoint.
        
        This creates all the standard meter types that will be uploaded,
        including their mRIDs and configuration. Based on MirrorUsagePointAdapter.
        
        Args:
            mup_href: MirrorUsagePoint href
            
        Returns:
            Number of meter types created/updated
        """
        # Default meter types based on MirrorUsagePointAdapter
        # Values from bms_2030_5_client/mup/adapter.py
        # UOM codes: 5=A, 38=W, 72=Wh, 23=°C, 0=N/A
        # Kind: 0=N/A, 3=current, 4=energy, 5=power, 11=temperature
        # FlowDirection: 0=N/A, 1=Forward, 19=Reverse
        # AccumulationBehaviour: 0=N/A, 3=Cumulative, 12=Instantaneous
        # Commodity: 7=Electricity Storage
        
        default_types = [
            # (description, mrid, uom_code, kind, commodity, flow_direction, accum, multiplier)
            ("Battery Total Current", "00000000000000000000000000000001", 5, 3, 7, 0, 12, -1),     # A, 0.1A
            ("Battery Total Power", "00000000000000000000000000000002", 38, 5, 7, 0, 12, 2),       # W, 100W
            ("Battery Charge Energy", "00000000000000000000000000000003", 72, 4, 7, 1, 3, 2),      # Wh, 100Wh
            ("Battery Discharge Energy", "00000000000000000000000000000004", 72, 4, 7, 19, 3, 2),  # Wh, 100Wh
            ("Battery Max Temperature", "00000000000000000000000000000005", 23, 11, 7, 0, 12, 0),  # °C
            ("Battery Min Temperature", "00000000000000000000000000000006", 23, 11, 7, 0, 12, 0),  # °C
            ("Battery Avg Temperature", "00000000000000000000000000000007", 23, 11, 7, 0, 12, 0),  # °C
            ("Battery SOH", "00000000000000000000000000000008", 0, 0, 7, 0, 12, -1),               # 0.1%
            ("Battery Cycle Count", "00000000000000000000000000000009", 0, 0, 7, 0, 3, 0),         # count
            ("BMS Timestamp", "0000000000000000000000000000000B", 0, 0, 0, 0, 12, 0),              # seconds
        ]
        
        count = 0
        for desc, mrid, uom, kind, comm, flow, accum, mult in default_types:
            record = MeterTypeRecord(
                mup_href=mup_href,
                description=desc,
                mrid=mrid,
                uom_code=uom,
                kind=kind,
                commodity=comm,
                flow_direction=flow,
                accumulation_behaviour=accum,
                power_of_ten_multiplier=mult,
                is_active=True,
            )
            self.save_meter_type(record)
            count += 1
        
        logger.info(f"Initialized {count} default meter types for {mup_href}")
        return count
    
    def _row_to_meter_type(self, row: sqlite3.Row) -> MeterTypeRecord:
        """Convert database row to MeterTypeRecord."""
        # Handle both simple and joined queries
        uom_symbol = row["uom_symbol"] if "uom_symbol" in row.keys() else None
        uom_name = row["uom_name"] if "uom_name" in row.keys() else None
        
        return MeterTypeRecord(
            id=row["id"],
            mup_href=row["mup_href"],
            description=row["description"],
            mrid=row["mrid"] if "mrid" in row.keys() else None,
            uom_code=row["uom_code"],
            uom_symbol=uom_symbol,
            uom_name=uom_name,
            kind=row["kind"],
            commodity=row["commodity"],
            flow_direction=row["flow_direction"],
            accumulation_behaviour=row["accumulation_behaviour"] if "accumulation_behaviour" in row.keys() else 0,
            power_of_ten_multiplier=row["power_of_ten_multiplier"] if "power_of_ten_multiplier" in row.keys() else 0,
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    
    # =========================================================================
    # Database Summary & Utilities
    # =========================================================================
    
    def get_summary(self) -> dict:
        """Get summary of stored resources."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            summary = {}
            for table in [
                "device_capability", "end_device", "der", "der_status",
                "der_capability", "mirror_usage_point", "mirror_meter_reading",
                "fsa", "der_program", "subscription", "meter_types", "uom"
            ]:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                summary[table] = cursor.fetchone()[0]
            
            return summary
    
    def clear_all(self) -> None:
        """Clear all data from database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            tables = [
                "subscription", "der_program", "fsa",
                "mirror_meter_reading", "mirror_usage_point",
                "der_availability", "der_settings", "der_capability",
                "der_status", "der", "end_device", "device_capability",
                "meter_types"
            ]
            
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")
            
            conn.commit()
            logger.info("All database data cleared")
