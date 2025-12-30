"""
BMS to IEEE 2030.5 data adapter.

Transforms CUBE BMS data to IEEE 2030.5 DER models.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List

from bms_2030_5_client.models import (
    # BMS models
    RackData,
    RackStatus,
    SystemData,
    BMSSnapshot,
    # IEEE 2030.5 models
    DERStatus,
    DERAvailability,
    DERSettings,
    DERCapability,
    DERType,
    ActivePower,
    ReactivePower,
    Voltage,
    Current,
    StateOfCharge,
    ConnectStatusType,
    OperationalModeStatusType,
    ConnectStatusValue,
    OperationalModeStatusValue,
    # Metering models
    MirrorUsagePoint,
    MirrorMeterReading,
    MeterReading,
    MirrorReadingSet,
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


class BMSAdapter:
    """
    Adapter to convert BMS data to IEEE 2030.5 DER models.
    
    Maps CUBE battery rack data to IEEE 2030.5 DERStatus,
    DERAvailability, and other DER resources.
    """

    def __init__(
        self,
        nominal_voltage: float = 750.0,  # V
        max_power: float = 100000.0,  # W (100 kW)
        max_current: float = 150.0,  # A
    ):
        """
        Initialize adapter with system ratings.
        
        Args:
            nominal_voltage: Nominal system voltage in V
            max_power: Maximum power rating in W
            max_current: Maximum current rating in A
        """
        self.nominal_voltage = nominal_voltage
        self.max_power = max_power
        self.max_current = max_current

    def _to_active_power(self, watts: float) -> ActivePower:
        """Convert watts to ActivePower with appropriate multiplier."""
        # Use multiplier for scaling
        if abs(watts) >= 1000000:
            return ActivePower(multiplier=6, value=int(watts / 1000000))
        elif abs(watts) >= 1000:
            return ActivePower(multiplier=3, value=int(watts / 1000))
        else:
            return ActivePower(multiplier=0, value=int(watts))

    def _to_voltage(self, volts: float) -> Voltage:
        """Convert volts to Voltage."""
        # Store as 0.1V units
        return Voltage(multiplier=-1, value=int(volts * 10))

    def _to_current(self, amps: float) -> Current:
        """Convert amps to Current."""
        # Store as 0.1A units
        return Current(multiplier=-1, value=int(amps * 10))

    def _to_soc(self, percent: float) -> StateOfCharge:
        """Convert percentage to StateOfCharge (0-10000)."""
    def _to_soc(self, percent: float) -> StateOfCharge:
        """Convert percentage to StateOfCharge."""
        return StateOfCharge(
            dateTime=int(datetime.now().timestamp()),
            value=int(percent * 100)
        )

    def snapshot_to_der_status(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERStatus:
        """
        Convert BMS snapshot to DERStatus.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the status resource
            
        Returns:
            DERStatus object
        """
        # Determine connection status
        connect_status = ConnectStatusType.CONNECTED
        if snapshot.system.active_rack_count > 0:
            connect_status |= ConnectStatusType.AVAILABLE
            
        # Check if any rack is operating
        operating = any(
            r.status in (RackStatus.CHARGING, RackStatus.DISCHARGING)
            for r in snapshot.racks
        )
        if operating:
            connect_status |= ConnectStatusType.OPERATING

        # Check for faults
        if snapshot.has_alarms or any(r.status == RackStatus.FAULT for r in snapshot.racks):
            connect_status |= ConnectStatusType.FAULT

        # Determine operational mode - use OPERATING for any active state
        op_mode = OperationalModeStatusType.OPERATING
        
        ts = int(datetime.now().timestamp())

        return DERStatus(
            href=href,
            readingTime=ts,
            genConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
            operationalModeStatus=OperationalModeStatusValue(dateTime=ts, value=f"{int(op_mode):02X}"),
            stateOfChargeStatus=self._to_soc(snapshot.average_soc),
            storConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
        )

    def snapshot_to_der_availability(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERAvailability:
        """
        Convert BMS snapshot to DERAvailability.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the availability resource
            
        Returns:
            DERAvailability object
        """
        # Calculate available power based on SOC and system limits
        avg_soc = snapshot.average_soc
        
        # Available discharge power (depends on SOC)
        # Lower SOC = less available discharge power
        discharge_factor = avg_soc / 100.0
        avail_discharge_w = self.max_power * discharge_factor
        
        # Available charge power (depends on remaining capacity)
        charge_factor = (100.0 - avg_soc) / 100.0
        avail_charge_w = self.max_power * charge_factor

        # Calculate max charge/discharge from rack limits
        if snapshot.active_racks:
            max_charge_current = min(r.max_charge_current for r in snapshot.active_racks)
            max_discharge_current = min(r.max_discharge_current for r in snapshot.active_racks)
            avg_voltage = sum(r.voltage for r in snapshot.active_racks) / len(snapshot.active_racks)
            
            # Limit by current capabilities
            avail_charge_w = min(avail_charge_w, max_charge_current * avg_voltage)
            avail_discharge_w = min(avail_discharge_w, max_discharge_current * avg_voltage)

        return DERAvailability(
            href=href,
            readingTime=int(datetime.now().timestamp()),
            reserveChargePercent=int(avg_soc * 100),  # 0-10000
            reservePercent=int(avg_soc * 100),
            statWAvail=self._to_active_power(avail_discharge_w),
        )

    def snapshot_to_der_settings(
        self,
        snapshot: BMSSnapshot,
        href: Optional[str] = None,
    ) -> DERSettings:
        """
        Convert BMS snapshot to DERSettings.
        
        Args:
            snapshot: BMS system snapshot
            href: Optional href for the settings resource
            
        Returns:
            DERSettings object
        """
        # Get limits from active racks
        if snapshot.active_racks:
            max_charge_current = max(r.max_charge_current for r in snapshot.active_racks)
            max_discharge_current = max(r.max_discharge_current for r in snapshot.active_racks)
            max_voltage = max(r.max_charge_voltage for r in snapshot.active_racks)
            avg_voltage = sum(r.voltage for r in snapshot.active_racks) / len(snapshot.active_racks)
            
            max_charge_w = max_charge_current * avg_voltage
            max_discharge_w = max_discharge_current * avg_voltage
        else:
            max_charge_w = self.max_power
            max_discharge_w = self.max_power
            max_voltage = self.nominal_voltage

        return DERSettings(
            href=href,
            setMaxW=self._to_active_power(max_discharge_w),
            setMaxChargeRateW=self._to_active_power(max_charge_w),
            setMaxDischargeRateW=self._to_active_power(max_discharge_w),
            setVRef=self._to_voltage(self.nominal_voltage),
            updatedTime=int(datetime.now().timestamp()),
        )

    def create_der_capability(
        self,
        href: Optional[str] = None,
    ) -> DERCapability:
        """
        Create DERCapability for the BMS.
        
        Args:
            href: Optional href for the capability resource
            
        Returns:
            DERCapability object
        """
        return DERCapability(
            href=href,
            modesSupported=0x0F,  # Support basic modes
            rtgMaxW=self._to_active_power(self.max_power),
            rtgMaxChargeRateW=self._to_active_power(self.max_power),
            rtgMaxDischargeRateW=self._to_active_power(self.max_power),
            rtgVNom=self._to_voltage(self.nominal_voltage),
            rtgAMax=self._to_current(self.max_current),
            type_=DERType.BATTERY_STORAGE,
        )

    def rack_to_der_status(
        self,
        rack: RackData,
        href: Optional[str] = None,
    ) -> DERStatus:
        """
        Convert single rack data to DERStatus.
        
        Args:
            rack: Single rack data
            href: Optional href
            
        Returns:
            DERStatus for the rack
        """
        # Connection status
        connect_status = ConnectStatusType.CONNECTED
        if rack.status != RackStatus.OFFLINE:
            connect_status |= ConnectStatusType.AVAILABLE
        if rack.status in (RackStatus.CHARGING, RackStatus.DISCHARGING):
            connect_status |= ConnectStatusType.OPERATING
        if rack.status == RackStatus.FAULT or rack.alarm_status != 0:
            connect_status |= ConnectStatusType.FAULT

        # Operational mode - use OPERATING for active state
        if rack.status == RackStatus.STANDBY:
            op_mode = OperationalModeStatusType.OPERATING
        elif rack.status in (RackStatus.CHARGING, RackStatus.DISCHARGING):
            op_mode = OperationalModeStatusType.OPERATING
        else:
            op_mode = OperationalModeStatusType.OFF

        ts = int(rack.timestamp.timestamp())

        return DERStatus(
            href=href,
            readingTime=ts,
            genConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
            operationalModeStatus=OperationalModeStatusValue(dateTime=ts, value=f"{int(op_mode):02X}"),
            stateOfChargeStatus=self._to_soc(rack.soc),
            storConnectStatus=ConnectStatusValue(dateTime=ts, value=f"{int(connect_status):02X}"),
        )

    # =========================================================================
    # Metering / MirrorUsagePoint Conversion Methods
    # =========================================================================

    def _generate_mrid(self) -> str:
        """Generate a unique mRID for meter resources."""
        return uuid.uuid4().hex[:32].upper()

    def create_bms_mirror_usage_point(
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
                self._create_soc_reading_type(),
                self._create_current_reading_type(),
                self._create_power_reading_type(),
                self._create_charge_energy_reading_type(),
                self._create_discharge_energy_reading_type(),
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
        
        # SOC Reading (0.1% units from CUBE, store as 0.1%)
        # Register 4005: SOC_avg (0.1%)
        soc_value = int(snapshot.system.total_soc * 10)  # Convert % to 0.1% units
        readings.append(self._create_meter_reading(
            name="soc",
            description="Battery SOC",
            value=soc_value,
            timestamp=ts,
            reading_type=self._create_soc_reading_type().ReadingType,
            mrid=reading_mrids.get("soc") if reading_mrids else None,
        ))
        
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

    def container_to_meter_readings(
        self,
        vol_avg: float,
        total_curr: float,
        total_power: float,
        soc_avg: float,
        charge_energy: float,
        discharge_energy: float,
        reading_mrids: Optional[dict] = None,
    ) -> List[MirrorMeterReading]:
        """
        Convert CUBE container-level register values directly to meter readings.
        
        This method uses raw values from CUBE 4000-series registers:
        - 4000: Vol_avg (0.1V)
        - 4001: total_curr (0.1A)
        - 4002: total_power (0.1kW)
        - 4003: deliy_CHG (0.1kWh)
        - 4004: deliy_DSC (0.1kWh)
        - 4005: SOC_avg (0.1%)
        
        Args:
            vol_avg: Average voltage in V
            total_curr: Total current in A (positive=charge)
            total_power: Total power in kW (positive=charge)
            soc_avg: Average SOC in %
            charge_energy: Charge energy in kWh
            discharge_energy: Discharge energy in kWh
            reading_mrids: Optional dict mapping reading names to mRIDs
            
        Returns:
            List of MirrorMeterReading objects
        """
        ts = int(datetime.now().timestamp())
        readings = []
        
        # SOC (0.1% units)
        readings.append(self._create_meter_reading(
            name="soc",
            description="Battery SOC",
            value=int(soc_avg * 10),
            timestamp=ts,
            reading_type=self._create_soc_reading_type().ReadingType,
            mrid=reading_mrids.get("soc") if reading_mrids else None,
        ))
        
        # Current (0.1A units)
        readings.append(self._create_meter_reading(
            name="current",
            description="Battery Total Current",
            value=int(total_curr * 10),
            timestamp=ts,
            reading_type=self._create_current_reading_type().ReadingType,
            mrid=reading_mrids.get("current") if reading_mrids else None,
        ))
        
        # Power (0.1kW units)
        readings.append(self._create_meter_reading(
            name="power",
            description="Battery Total Power",
            value=int(total_power * 10),
            timestamp=ts,
            reading_type=self._create_power_reading_type().ReadingType,
            mrid=reading_mrids.get("power") if reading_mrids else None,
        ))
        
        # Charge Energy (0.1kWh units)
        readings.append(self._create_meter_reading(
            name="charge_energy",
            description="Battery Charge Energy",
            value=int(charge_energy * 10),
            timestamp=ts,
            reading_type=self._create_charge_energy_reading_type().ReadingType,
            mrid=reading_mrids.get("charge_energy") if reading_mrids else None,
        ))
        
        # Discharge Energy (0.1kWh units)
        readings.append(self._create_meter_reading(
            name="discharge_energy",
            description="Battery Discharge Energy",
            value=int(discharge_energy * 10),
            timestamp=ts,
            reading_type=self._create_discharge_energy_reading_type().ReadingType,
            mrid=reading_mrids.get("discharge_energy") if reading_mrids else None,
        ))
        
        logger.debug(
            f"Created meter readings: SOC={soc_avg}%, Current={total_curr}A, "
            f"Power={total_power}kW, CHG={charge_energy}kWh, DSC={discharge_energy}kWh"
        )
        
        return readings
