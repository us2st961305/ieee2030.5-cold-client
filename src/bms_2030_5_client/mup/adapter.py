"""
MirrorUsagePoint adapter for converting BMS data to meter readings.
"""

import logging
from datetime import datetime
from typing import Optional, List

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

logger = logging.getLogger(__name__)


class MirrorUsagePointAdapter:
    """
    Adapter to convert BMS data to MirrorUsagePoint and meter readings.
    
    Focuses on single DER meter representation.
    """

    def __init__(self):
        """Initialize adapter."""
        self._mrid_counter = 0  # Counter for sequential MRID generation

    def _generate_mrid(self) -> str:
        """
        Generate a unique mRID for meter resources.
        Uses sequential numbering starting from 1, incrementing for each registration.
        """
        self._mrid_counter += 1
        # Generate 32-character hex string with sequential number
        # Format: zero-padded to 32 hex characters
        return f"{self._mrid_counter:032X}"

    def create_mirror_usage_point(
        self,
        device_lfdi: str,
        description: str = "BMS Battery Storage Meter",
        post_rate: int = 60,
        include_readings: bool = False,
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
            ]
        
        mup = MirrorUsagePoint(
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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
            mRID=self._generate_mrid(),
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

    def snapshot_to_meter_readings(
        self,
        snapshot: BMSSnapshot,
        reading_mrids: Optional[dict] = None,
    ) -> List[MirrorMeterReading]:
        """
        Convert BMS snapshot to meter readings for upload.
        
        Creates readings for:
        - Total SOC (from register 4005: SOC_avg, 0.1%)
        - Total Current (from register 4001: total_curr, 0.1A)
        - Total Power (from register 4002: total_power, 0.1kW)
        - Charge Energy (from register 4003: deliy_CHG, 0.1kWh)
        - Discharge Energy (from register 4004: deliy_DSC, 0.1kWh)
        
        Args:
            snapshot: BMS system snapshot
            reading_mrids: Optional dict mapping reading names to mRIDs
                          for updating existing readings
            
        Returns:
            List of MirrorMeterReading objects ready for upload
        """
        ts = int(snapshot.timestamp.timestamp())
        readings = []
        
        # Current Reading (0.1A units from CUBE)
        # Register 4001: total_curr (0.1A) - signed, positive=charge
        current_value = int(snapshot.system.total_current * 10)  # Convert A to 0.1A
        readings.append(self._create_meter_reading(
            name="current",
            description="Battery Total Current",
            value=current_value,
            timestamp=ts,
            reading_type=self._create_current_reading_type().ReadingType,
            mrid=reading_mrids.get("current") if reading_mrids else None,
        ))
        
        # Power Reading (0.1kW = 100W units from CUBE)
        # Register 4002: total_power (0.1kW)
        power_value = int(snapshot.system.total_power * 10)  # Convert kW to 0.1kW
        readings.append(self._create_meter_reading(
            name="power",
            description="Battery Total Power",
            value=power_value,
            timestamp=ts,
            reading_type=self._create_power_reading_type().ReadingType,
            mrid=reading_mrids.get("power") if reading_mrids else None,
        ))
        
        # Charge Energy Reading (0.1kWh = 100Wh units)
        # Register 4003: deliy_CHG (0.1kWh) - daily charge energy
        # Note: Need to get this from ContainerData if available
        charge_energy = getattr(snapshot.system, 'charge_energy', 0)
        charge_value = int(charge_energy * 10)  # Convert kWh to 0.1kWh
        readings.append(self._create_meter_reading(
            name="charge_energy",
            description="Battery Charge Energy",
            value=charge_value,
            timestamp=ts,
            reading_type=self._create_charge_energy_reading_type().ReadingType,
            mrid=reading_mrids.get("charge_energy") if reading_mrids else None,
        ))
        
        # Discharge Energy Reading (0.1kWh = 100Wh units)
        # Register 4004: deliy_DSC (0.1kWh) - daily discharge energy
        discharge_energy = getattr(snapshot.system, 'discharge_energy', 0)
        discharge_value = int(discharge_energy * 10)  # Convert kWh to 0.1kWh
        readings.append(self._create_meter_reading(
            name="discharge_energy",
            description="Battery Discharge Energy",
            value=discharge_value,
            timestamp=ts,
            reading_type=self._create_discharge_energy_reading_type().ReadingType,
            mrid=reading_mrids.get("discharge_energy") if reading_mrids else None,
        ))
        
        # Max Temperature Reading (1°C units)
        # Register 4016: all_max_t (1°C)
        max_temp = getattr(snapshot.system, 'max_temperature', 0)
        max_temp_value = int(max_temp)  # 1°C units
        readings.append(self._create_meter_reading(
            name="max_temperature",
            description="Battery Max Temperature",
            value=max_temp_value,
            timestamp=ts,
            reading_type=self._create_max_temperature_reading_type().ReadingType,
            mrid=reading_mrids.get("max_temperature") if reading_mrids else None,
        ))
        
        # Min Temperature Reading (1°C units)
        # Register 4017: all_min_t (1°C)
        min_temp = getattr(snapshot.system, 'min_temperature', 0)
        min_temp_value = int(min_temp)  # 1°C units
        readings.append(self._create_meter_reading(
            name="min_temperature",
            description="Battery Min Temperature",
            value=min_temp_value,
            timestamp=ts,
            reading_type=self._create_min_temperature_reading_type().ReadingType,
            mrid=reading_mrids.get("min_temperature") if reading_mrids else None,
        ))
        
        # Average Temperature Reading (1°C units)
        # Calculated from max and min temperature
        avg_temp = (max_temp + min_temp) / 2
        avg_temp_value = int(avg_temp)  # 1°C units
        readings.append(self._create_meter_reading(
            name="avg_temperature",
            description="Battery Avg Temperature",
            value=avg_temp_value,
            timestamp=ts,
            reading_type=self._create_avg_temperature_reading_type().ReadingType,
            mrid=reading_mrids.get("avg_temperature") if reading_mrids else None,
        ))
        
        return readings

    def _create_meter_reading(
        self,
        name: str,
        description: str,
        value: int,
        timestamp: int,
        reading_type: ReadingType,
        mrid: Optional[str] = None,
    ) -> MirrorMeterReading:
        """
        Create a MirrorMeterReading with a single reading value.
        
        Args:
            name: Reading name for logging
            description: Human-readable description
            value: The reading value (already scaled)
            timestamp: Unix timestamp
            reading_type: ReadingType for this reading
            mrid: Optional existing mRID
            
        Returns:
            MirrorMeterReading ready for upload
        """
        return MirrorMeterReading(
            mRID=mrid or self._generate_mrid(),
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
