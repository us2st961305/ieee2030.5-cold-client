"""
MirrorUsagePoint adapter for converting BMS data to meter readings.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List

from bms_2030_5_client.models import (
    BMSSnapshot,
    MirrorUsagePoint,
    MirrorMeterReading,
    MeterReading,
    ReadingType,
    DateTimeInterval,
    AccumulationBehaviourType,
    CommodityType,
    FlowDirectionType,
    DataQualifierType,
    KindType,
    UomType,
    ServiceKind,
    RoleFlagsType,
)
from bms_2030_5_client.models.ieee2030_5_models import DEFAULT_IANA_PEN

logger = logging.getLogger(__name__)


class MirrorUsagePointAdapter:
    """
    Adapter to convert BMS data to MirrorUsagePoint and meter readings.
    
    Focuses on single DER meter representation.
    """

    # IANA PEN suffix (8 hex chars) appended to every mRID
    _IANA_PEN_HEX = f"{DEFAULT_IANA_PEN:08X}"

    def __init__(self, device_lfdi: str = "", time_sync_client=None):
        """Initialize adapter.

        Args:
            device_lfdi: Device LFDI for generating unique but stable mRIDs.
            time_sync_client: Optional TimeSyncClient instance. When provided,
                get_corrected_time() is used instead of int(time.time()) for all
                meter reading timestamps, ensuring server-aligned timestamps.
                This is the fix for repeated "timestamp imprecision" regressions.
        """
        self._device_lfdi = device_lfdi
        self._time_sync_client = time_sync_client
        # In-memory cache: reading_key -> mRID (stable within one run)
        self._cached_mrids: Dict[str, str] = {}

    def _get_current_timestamp(self) -> int:
        """
        Return the current timestamp, corrected by server time offset if available.

        When a TimeSyncClient is attached and has been synced, returns
        get_corrected_time() which applies the server-local offset.
        Otherwise falls back to int(time.time()).

        This is the single source of truth for all meter reading timestamps.
        """
        import time as _time
        if (self._time_sync_client is not None
                and self._time_sync_client.is_synced):
            return self._time_sync_client.get_corrected_time()
        return int(_time.time())

    def _generate_mrid(self) -> str:
        """
        Generate a new mRID conforming to IEEE 2030.5 mRIDType.

        Format: [UUID4 96-bit (24 hex chars)][IANA PEN 32-bit (8 hex chars)]
        Total: 128-bit = 32 hex characters.

        Returns:
            32-character uppercase hex string mRID
        """
        unique_id = uuid.uuid4().hex[:24].upper()
        return unique_id + self._IANA_PEN_HEX

    def _generate_stable_mrid(self, reading_key: str) -> str:
        """
        Generate or retrieve a cached mRID for a reading type.

        On first call for a given *reading_key*, a new UUID+PEN mRID is
        generated and cached in memory.  Subsequent calls within the same
        process lifetime return the same value, keeping uploads consistent
        until the server-assigned mRID is persisted to the database.

        Args:
            reading_key: Key for the reading type (e.g., 'current', 'power')

        Returns:
            32-character uppercase hex string mRID
        """
        if reading_key not in self._cached_mrids:
            self._cached_mrids[reading_key] = self._generate_mrid()
        return self._cached_mrids[reading_key]

    def create_mirror_usage_point(
        self,
        device_lfdi: str,
        description: str = "BMS Battery Storage Meter",
        post_rate: int = 60,
        include_readings: bool = False,
        mup_mrid: str | None = None,
    ) -> MirrorUsagePoint:
        """
        Create a MirrorUsagePoint for the BMS system.
        
        This creates the meter registration. If include_readings is False,
        creates without MirrorMeterReading (for initial POST).
        If include_readings is True, includes all reading types (for PUT update).
        
        Note: IEEE 2030.5 server requires two-step process:
        1. POST MirrorUsagePoint without MirrorMeterReading
        2. PUT MirrorUsagePoint with MirrorMeterReading
        
        Args:
            device_lfdi: Device LFDI (Long-Form Device Identifier)
            description: Description of the meter
            post_rate: Posting rate in seconds
            include_readings: Whether to include MirrorMeterReading
            mup_mrid: Persisted mRID from database; if provided, reuse
                instead of generating a new one (IEEE 2030.5 Section
                10.11.3(a)(4) – server returns same URI for matching mRID).
            
        Returns:
            MirrorUsagePoint ready to register with server
        """
        readings = []
        if include_readings:
            readings = [
                # self._create_soc_reading_type(),
                self._create_current_reading_type(),
                self._create_power_reading_type(),
                self._create_charge_energy_reading_type(),
                self._create_discharge_energy_reading_type(),
                self._create_max_temperature_reading_type(),
                self._create_min_temperature_reading_type(),
                self._create_avg_temperature_reading_type(),
                self._create_soh_reading_type(),
                self._create_cycle_count_reading_type(),
            ]
        
        mup = MirrorUsagePoint(
            mRID=mup_mrid or self._generate_mrid(),
            description=description,
            version=1,
            roleFlags=f"{(int(RoleFlagsType.IS_MIRROR) | int(RoleFlagsType.IS_DER)):04X}",  # HexBinary16
            serviceCategoryKind=int(ServiceKind.ELECTRICITY),
            status=1,  # On
            deviceLFDI=device_lfdi,
            postRate=post_rate,
            MirrorMeterReading=readings,
        )
        return mup

    def _create_soc_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for SOC (State of Charge)."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("soc"),
            description="Battery SOC",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.NOT_APPLICABLE),
                kind=int(KindType.NOT_APPLICABLE),
                powerOfTenMultiplier=-1,  # 0.1% units (value / 10 = %)
                uom=int(UomType.PERCENT),
            ),
        )

    def _create_current_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Total Current."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("current"),
            description="Battery Total Current",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.NET),  # Positive=charge, Negative=discharge
                kind=int(KindType.CURRENT),
                powerOfTenMultiplier=-1,  # 0.1A units (from CUBE register 4001)
                uom=int(UomType.AMPERE),
            ),
        )

    def _create_power_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Total Power."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("power"),
            description="Battery Total Power",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.NET),  # Positive=charge, Negative=discharge
                kind=int(KindType.POWER),
                powerOfTenMultiplier=2,  # 0.1kW = 100W units (from CUBE register 4002)
                uom=int(UomType.WATT),
            ),
        )

    def _create_charge_energy_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Charge Energy (kWh)."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("charge_energy"),
            description="Battery Charge Energy",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.CUMULATIVE),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.FORWARD),  # Into battery
                kind=int(KindType.ENERGY),
                powerOfTenMultiplier=2,  # 0.1kWh = 100Wh units (from CUBE register 4003)
                uom=int(UomType.WATT_HOUR),
            ),
        )

    def _create_discharge_energy_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Discharge Energy (kWh)."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("discharge_energy"),
            description="Battery Discharge Energy",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.CUMULATIVE),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.REVERSE),  # Out of battery
                kind=int(KindType.ENERGY),
                powerOfTenMultiplier=2,  # 0.1kWh = 100Wh units (from CUBE register 4004)
                uom=int(UomType.WATT_HOUR),
            ),
        )

    def _create_max_temperature_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Maximum Temperature (°C)."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("max_temperature"),
            description="Battery Max Temperature",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.MAXIMUM),
                flowDirection=int(FlowDirectionType.NOT_APPLICABLE),
                kind=int(KindType.TEMPERATURE),
                powerOfTenMultiplier=0,  # 1°C units (from CUBE register 4016)
                uom=int(UomType.CELSIUS),
            ),
        )

    def _create_min_temperature_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Minimum Temperature (°C)."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("min_temperature"),
            description="Battery Min Temperature",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.MINIMUM),
                flowDirection=int(FlowDirectionType.NOT_APPLICABLE),
                kind=int(KindType.TEMPERATURE),
                powerOfTenMultiplier=0,  # 1°C units (from CUBE register 4017)
                uom=int(UomType.CELSIUS),
            ),
        )

    def _create_avg_temperature_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Average Temperature (°C)."""
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("avg_temperature"),
            description="Battery Avg Temperature",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.AVERAGE),
                flowDirection=int(FlowDirectionType.NOT_APPLICABLE),
                kind=int(KindType.TEMPERATURE),
                powerOfTenMultiplier=0,  # 1°C units (calculated average)
                uom=int(UomType.CELSIUS),
            ),
        )

    def _create_soh_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for SOH (State of Health).
        
        SOH is reported as 0.1% units (value / 10 = %).
        Uses UOM 0 (Not Applicable) as SOH is a dimensionless ratio.
        """
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("soh"),
            description="Battery SOH",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.NOT_APPLICABLE),
                kind=int(KindType.NOT_APPLICABLE),
                powerOfTenMultiplier=-1,  # 0.1% units (value / 10 = %)
                uom=0,  # UOM 0: Not Applicable (dimensionless)
            ),
        )

    def _create_cycle_count_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Cycle Count.
        
        Cycle count is the number of complete charge/discharge cycles.
        Uses UOM 0 (Not Applicable) as cycle count is dimensionless.
        """
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("cycle_count"),
            description="Battery Cycle Count",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.CUMULATIVE),
                commodity=int(CommodityType.ELECTRICITY_STORAGE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.NOT_APPLICABLE),
                kind=int(KindType.NOT_APPLICABLE),
                powerOfTenMultiplier=0,  # 1 cycle units
                uom=0,  # UOM 0: Not Applicable (dimensionless count)
            ),
        )

    def _create_timestamp_reading_type(self) -> MirrorMeterReading:
        """Create MirrorMeterReading for Timestamp.
        
        Timestamp is reported as Unix epoch seconds.
        Uses UOM 0 (Not Applicable) as timestamp is a dimensionless value.
        """
        return MirrorMeterReading(
            mRID=self._generate_stable_mrid("timestamp"),
            description="BMS Timestamp",
            version=1,
            ReadingType=ReadingType(
                accumulationBehaviour=int(AccumulationBehaviourType.INSTANTANEOUS),
                commodity=int(CommodityType.NOT_APPLICABLE),
                dataQualifier=int(DataQualifierType.NORMAL),
                flowDirection=int(FlowDirectionType.NOT_APPLICABLE),
                kind=int(KindType.NOT_APPLICABLE),
                powerOfTenMultiplier=0,  # 1 second units
                uom=0,  # UOM 0: Not Applicable
            ),
        )

    def snapshot_to_meter_readings(
        self,
        snapshot: BMSSnapshot,
        reading_mrids: Optional[dict] = None,
        soh: Optional[float] = None,
        cycle_count: Optional[int] = None,
        include_reading_type: bool = False,
        skip_missing_mrids: bool = False,
    ) -> List[MirrorMeterReading]:
        """
        Convert BMS snapshot to meter readings for upload.
        
        Creates readings for:
        - Total Current (from register 4001: total_curr, 0.1A)
        - Total Power (from register 4002: total_power, 0.1kW)
        - Charge Energy (from register 4003: deliy_CHG, 0.1kWh)
        - Discharge Energy (from register 4004: deliy_DSC, 0.1kWh)
        - Max/Min/Avg Temperature
        - SOH (State of Health, 0.1% units, UOM=0)
        - Cycle Count (number of cycles, UOM=0)
        
        Per IEEE 2030.5 spec, ReadingType SHALL NOT be modified once registered,
        and SHOULD NOT be included in subsequent data updates. Only include
        ReadingType when registering a new mRID that the server has not seen.
        
        Args:
            snapshot: BMS system snapshot
            reading_mrids: Optional dict mapping reading names to mRIDs
                          for updating existing readings
            soh: Optional SOH value (0-100%), if None calculates from active racks
            cycle_count: Optional cycle count value, if None uses 0
            include_reading_type: Whether to include ReadingType in readings.
                                  Should be False for periodic updates (default),
                                  True only for initial registration of new mRIDs.
            skip_missing_mrids: When True, skip readings that have no mRID in
                                reading_mrids instead of generating new random mRIDs.
                                Enables partial upload (Layer 3 of mRID recovery).
            
        Returns:
            List of MirrorMeterReading objects ready for upload
        """
        # Use server-corrected timestamp when TimeSyncClient is available and synced.
        # Fall back to snapshot.timestamp for backward compatibility.
        if self._time_sync_client is not None and self._time_sync_client.is_synced:
            ts = self._get_current_timestamp()
        else:
            ts = int(snapshot.timestamp.timestamp())
        readings = []
        
        # Current Reading (0.1A units from CUBE)
        # Register 4001: total_curr (0.1A) - signed, positive=charge
        current_value = int(snapshot.system.total_current * 10)  # Convert A to 0.1A
        reading = self._create_meter_reading(
            name="current",
            description="Battery Total Current",
            value=current_value,
            timestamp=ts,
            reading_type=self._create_current_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("current") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Power Reading (0.1kW = 100W units from CUBE)
        # Register 4002: total_power (0.1kW)
        power_value = int(snapshot.system.total_power * 10)  # Convert kW to 0.1kW
        reading = self._create_meter_reading(
            name="power",
            description="Battery Total Power",
            value=power_value,
            timestamp=ts,
            reading_type=self._create_power_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("power") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Charge Energy Reading (0.1kWh = 100Wh units)
        # Register 4003: deliy_CHG (0.1kWh) - daily charge energy
        # Note: Need to get this from ContainerData if available
        charge_energy = getattr(snapshot.system, 'charge_energy', 0)
        charge_value = int(charge_energy * 10)  # Convert kWh to 0.1kWh
        reading = self._create_meter_reading(
            name="charge_energy",
            description="Battery Charge Energy",
            value=charge_value,
            timestamp=ts,
            reading_type=self._create_charge_energy_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("charge_energy") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Discharge Energy Reading (0.1kWh = 100Wh units)
        # Register 4004: deliy_DSC (0.1kWh) - daily discharge energy
        discharge_energy = getattr(snapshot.system, 'discharge_energy', 0)
        discharge_value = int(discharge_energy * 10)  # Convert kWh to 0.1kWh
        reading = self._create_meter_reading(
            name="discharge_energy",
            description="Battery Discharge Energy",
            value=discharge_value,
            timestamp=ts,
            reading_type=self._create_discharge_energy_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("discharge_energy") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Max Temperature Reading (1°C units)
        # Register 4016: all_max_t (1°C)
        max_temp = getattr(snapshot.system, 'max_temperature', 0)
        max_temp_value = int(max_temp)  # 1°C units
        reading = self._create_meter_reading(
            name="max_temperature",
            description="Battery Max Temperature",
            value=max_temp_value,
            timestamp=ts,
            reading_type=self._create_max_temperature_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("max_temperature") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Min Temperature Reading (1°C units)
        # Register 4017: all_min_t (1°C)
        min_temp = getattr(snapshot.system, 'min_temperature', 0)
        min_temp_value = int(min_temp)  # 1°C units
        reading = self._create_meter_reading(
            name="min_temperature",
            description="Battery Min Temperature",
            value=min_temp_value,
            timestamp=ts,
            reading_type=self._create_min_temperature_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("min_temperature") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Average Temperature Reading (1°C units)
        # Calculated from max and min temperature
        avg_temp = (max_temp + min_temp) / 2
        avg_temp_value = int(avg_temp)  # 1°C units
        reading = self._create_meter_reading(
            name="avg_temperature",
            description="Battery Avg Temperature",
            value=avg_temp_value,
            timestamp=ts,
            reading_type=self._create_avg_temperature_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("avg_temperature") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # SOH Reading (0.1% units, UOM=0)
        # Calculate from active racks if not provided
        if soh is None:
            active_racks = [r for r in snapshot.racks if r.status.value != 0]
            if active_racks:
                soh = sum(r.soh for r in active_racks) / len(active_racks)
            else:
                soh = 100.0  # Default if no active racks
        soh_value = int(soh * 10)  # Convert % to 0.1% units
        reading = self._create_meter_reading(
            name="soh",
            description="Battery SOH",
            value=soh_value,
            timestamp=ts,
            reading_type=self._create_soh_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("soh") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Cycle Count Reading (integer count, UOM=0)
        cycle_value = cycle_count if cycle_count is not None else 0
        reading = self._create_meter_reading(
            name="cycle_count",
            description="Battery Cycle Count",
            value=cycle_value,
            timestamp=ts,
            reading_type=self._create_cycle_count_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("cycle_count") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        # Timestamp Reading (Unix epoch seconds)
        # Reports current BMS timestamp for synchronization verification
        reading = self._create_meter_reading(
            name="timestamp",
            description="BMS Timestamp",
            value=ts,  # Unix timestamp in seconds
            timestamp=ts,
            reading_type=self._create_timestamp_reading_type().ReadingType if include_reading_type else None,
            mrid=reading_mrids.get("timestamp") if reading_mrids else None,
            skip_if_no_mrid=skip_missing_mrids,
        )
        if reading:
            readings.append(reading)
        
        return readings

    def _create_meter_reading(
        self,
        name: str,
        description: str,
        value: int,
        timestamp: int,
        reading_type: Optional[ReadingType] = None,
        mrid: Optional[str] = None,
        skip_if_no_mrid: bool = False,
    ) -> Optional[MirrorMeterReading]:
        """
        Create a MirrorMeterReading with a single reading value.
        
        Per IEEE 2030.5 spec:
        - ReadingType SHALL NOT be modified once registered.
        - ReadingType SHOULD NOT be included in subsequent data updates.
        - ReadingType MUST be included only when posting a new mRID.
        
        Args:
            name: Reading name/key (e.g., 'current', 'power')
            description: Human-readable description
            value: The reading value (already scaled)
            timestamp: Unix timestamp
            reading_type: ReadingType for this reading. Should be None for
                          periodic updates (omit after registration).
            mrid: Optional existing mRID (from cache or server)
            skip_if_no_mrid: If True and mrid is None, return None instead
                             of generating a new mRID (Layer 3 partial upload).
            
        Returns:
            MirrorMeterReading ready for upload, or None if skipped.
        """
        # Layer 3: skip this reading if mRID is missing and caller requested partial upload
        if skip_if_no_mrid and mrid is None:
            logger.debug(f"Skipping reading '{name}' — no mRID and skip_if_no_mrid=True")
            return None

        # Use provided mRID, or generate stable mRID based on name
        final_mrid = mrid or self._generate_stable_mrid(name)
        
        return MirrorMeterReading(
            mRID=final_mrid,
            description=description,
            version=1,
            lastUpdateTime=timestamp,
            nextUpdateTime=timestamp + 60,  # Next update in 60 seconds
            Reading=MeterReading(
                value=value,
                timePeriod=DateTimeInterval(
                    duration=0,  # Instantaneous
                    start=timestamp,
                ),
                qualityFlags="01",  # Valid data
            ),
            ReadingType=reading_type,
        )
