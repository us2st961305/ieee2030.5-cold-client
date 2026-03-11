"""
IEEE 2030.5-2023 DERCurve and Related Models.

This module provides complete DERCurve implementation including:
- DERCurve: Container for curve data with type and parameters
- CurveData: Individual curve data points
- DERCurveType: All 15 curve types defined in IEEE 2030.5-2023

Reference: IEEE Std 2030.5-2023
- Section 10.9: DERCurve
- Table 31: curveType values
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List
from dataclasses_json import dataclass_json


# =============================================================================
# DERCurveType Enumeration (Table 31)
# =============================================================================

class DERCurveType(IntEnum):
    """
    DER Curve Type enumeration.
    
    Reference: IEEE Std 2030.5-2023 Table 31
    
    Defines the type of curve and its X/Y axis meanings.
    """
    # 0: Frequency-Watt (opModFreqWatt)
    #    X-axis: Frequency (Hz) → Y-axis: % setMaxW (signed)
    FREQ_WATT = 0
    
    # 1: High Frequency Ride Through - May Trip (opModHFRTMayTrip)
    #    X-axis: Time (seconds) → Y-axis: Frequency (Hz)
    HFRT_MAY_TRIP = 1
    
    # 2: High Frequency Ride Through - Must Trip (opModHFRTMustTrip)
    #    X-axis: Time (seconds) → Y-axis: Frequency (Hz)
    HFRT_MUST_TRIP = 2
    
    # 3: High Voltage Ride Through - May Trip (opModHVRTMayTrip)
    #    X-axis: Time (seconds) → Y-axis: % setVRef
    HVRT_MAY_TRIP = 3
    
    # 4: High Voltage Ride Through - Momentary Cessation (opModHVRTMomentaryCessation)
    #    X-axis: Time (seconds) → Y-axis: % setVRef
    HVRT_MOMENTARY_CESSATION = 4
    
    # 5: High Voltage Ride Through - Must Trip (opModHVRTMustTrip)
    #    X-axis: Time (seconds) → Y-axis: % setVRef
    HVRT_MUST_TRIP = 5
    
    # 6: Low Frequency Ride Through - May Trip (opModLFRTMayTrip)
    #    X-axis: Time (seconds) → Y-axis: Frequency (Hz)
    LFRT_MAY_TRIP = 6
    
    # 7: Low Frequency Ride Through - Must Trip (opModLFRTMustTrip)
    #    X-axis: Time (seconds) → Y-axis: Frequency (Hz)
    LFRT_MUST_TRIP = 7
    
    # 8: Low Voltage Ride Through - May Trip (opModLVRTMayTrip)
    #    X-axis: Time (seconds) → Y-axis: % setVRef
    LVRT_MAY_TRIP = 8
    
    # 9: Low Voltage Ride Through - Momentary Cessation (opModLVRTMomentaryCessation)
    #    X-axis: Time (seconds) → Y-axis: % setVRef
    LVRT_MOMENTARY_CESSATION = 9
    
    # 10: Low Voltage Ride Through - Must Trip (opModLVRTMustTrip)
    #     X-axis: Time (seconds) → Y-axis: % setVRef
    LVRT_MUST_TRIP = 10
    
    # 11: Volt-VAR (opModVoltVar)
    #     X-axis: % setVRef → Y-axis: % setMaxVar (signed)
    VOLT_VAR = 11
    
    # 12: Volt-Watt (opModVoltWatt)
    #     X-axis: % setVRef → Y-axis: % setMaxW (signed)
    VOLT_WATT = 12
    
    # 13: Watt-PF (opModWattPF)
    #     X-axis: % setMaxW → Y-axis: Power Factor with excitation
    WATT_PF = 13
    
    # 14: Watt-VAR (opModWattVar)
    #     X-axis: % setMaxW → Y-axis: % setMaxVar (signed)
    WATT_VAR = 14


# =============================================================================
# CurveData (Individual Data Point)
# =============================================================================

@dataclass_json
@dataclass
class CurveData:
    """
    Individual curve data point.
    
    Reference: IEEE Std 2030.5-2023
    
    Represents a single point on a DERCurve with X and optional Y values.
    The interpretation of xvalue and yvalue depends on the curveType.
    
    Attributes:
        excitation: For Watt-PF curve type only.
                   True = over-excited (leading PF)
                   False = under-excited (lagging PF)
        xvalue: X-axis value (Int32). Meaning depends on curveType:
                - Frequency curves: Hz * multiplier
                - Voltage curves: % of setVRef * 100
                - Power curves: % of setMaxW * 100
                - Time curves: seconds * 10
        yvalue: Y-axis value (Int32). Meaning depends on curveType:
                - Power curves: % of setMaxW or setMaxVar * 100 (signed)
                - PF curves: displacement * 10000
                - Voltage curves: % of setVRef * 100
                - Frequency curves: Hz * multiplier
    """
    xvalue: int = 0
    yvalue: Optional[int] = None
    excitation: Optional[bool] = None
    
    def to_x_percent(self) -> float:
        """Get X value as percentage (for percentage-based curves)."""
        return self.xvalue / 100.0
    
    def to_y_percent(self) -> float:
        """Get Y value as percentage (for percentage-based curves)."""
        return (self.yvalue or 0) / 100.0
    
    def to_x_hz(self, multiplier: int = 0) -> float:
        """Get X value as Hz (for frequency curves)."""
        return self.xvalue * (10 ** multiplier)
    
    def to_y_hz(self, multiplier: int = 0) -> float:
        """Get Y value as Hz (for frequency curves)."""
        return (self.yvalue or 0) * (10 ** multiplier)
    
    def to_x_seconds(self) -> float:
        """Get X value as seconds (for ride-through curves)."""
        return self.xvalue / 10.0
    
    def to_power_factor(self) -> tuple[float, bool]:
        """
        Get Y value as power factor with excitation (for Watt-PF).
        
        Returns:
            Tuple of (displacement, is_overexcited)
        """
        pf = (self.yvalue or 10000) / 10000.0
        return (pf, self.excitation or False)


# =============================================================================
# DERCurve (Main Curve Container)
# =============================================================================

@dataclass_json
@dataclass
class DERCurve:
    """
    IEEE 2030.5-2023 DERCurve resource.
    
    Reference: IEEE Std 2030.5-2023 Section 10.9
    
    A DERCurve defines a piece-wise linear curve used for various
    DER control functions like Volt-VAR, Freq-Watt, etc.
    
    Attributes:
        href: URI of this curve resource
        mRID: Globally unique identifier (UInt128 as hex string)
        description: User-defined description of the curve
        curveType: Type of curve (determines axis interpretation)
        CurveData: List of curve data points (at least 1 required)
        creationTime: Time when this curve was created (POSIX seconds)
        autonomousVRefEnable: Enable autonomous vRef adjustment
        autonomousVRefTimeConstant: Time constant for vRef adjustment (seconds)
        openLoopTms: Open loop response time (seconds)
        rampDecTms: Ramp down rate time constant (seconds)
        rampIncTms: Ramp up rate time constant (seconds)
        rampPT1Tms: First-order PT1 filter time constant (seconds)
        vRef: Reference voltage (Volts * multiplier)
        vRefOfs: Reference voltage offset (Volts * multiplier)
        xMultiplier: Multiplier for X-axis values (power of 10)
        yMultiplier: Multiplier for Y-axis values (power of 10)
        yRefType: Reference type for Y-axis interpretation
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None  # UInt128 as hex string
    description: Optional[str] = None
    
    # Curve type and data
    curveType: DERCurveType = DERCurveType.FREQ_WATT
    CurveData: List[CurveData] = field(default_factory=list)
    
    # Timestamps
    creationTime: Optional[int] = None
    
    # Autonomous voltage reference settings
    autonomousVRefEnable: Optional[bool] = None
    autonomousVRefTimeConstant: Optional[int] = None  # seconds
    
    # Response timing parameters
    openLoopTms: Optional[int] = None  # Open loop response time (seconds)
    rampDecTms: Optional[int] = None   # Ramp decrease time (seconds)
    rampIncTms: Optional[int] = None   # Ramp increase time (seconds)
    rampPT1Tms: Optional[int] = None   # PT1 filter time constant (seconds)
    
    # Voltage reference
    vRef: Optional[int] = None         # Reference voltage
    vRefOfs: Optional[int] = None      # Reference voltage offset
    
    # Multipliers
    xMultiplier: int = 0               # Power of 10 for X values
    yMultiplier: int = 0               # Power of 10 for Y values
    
    # Y reference type (curve-specific)
    yRefType: Optional[int] = None
    
    def add_point(self, x: int, y: Optional[int] = None, 
                  excitation: Optional[bool] = None) -> None:
        """
        Add a curve data point.
        
        Args:
            x: X-axis value
            y: Y-axis value (optional for some curve types)
            excitation: Excitation flag (only for Watt-PF curves)
        """
        point = CurveData(xvalue=x, yvalue=y, excitation=excitation)
        self.CurveData.append(point)
        # Keep sorted by X value
        self.CurveData.sort(key=lambda p: p.xvalue)
    
    def get_point_count(self) -> int:
        """Get number of data points."""
        return len(self.CurveData)
    
    def is_valid(self) -> bool:
        """
        Check if curve is valid.
        
        A valid curve must have at least one data point.
        """
        return len(self.CurveData) >= 1
    
    def interpolate_y(self, x: int) -> Optional[int]:
        """
        Linearly interpolate Y value for given X.
        
        Args:
            x: X-axis value to interpolate
            
        Returns:
            Interpolated Y value, or None if curve is empty
        """
        if not self.CurveData:
            return None
        
        # Handle edge cases
        if len(self.CurveData) == 1:
            return self.CurveData[0].yvalue
        
        # Sort by x value
        points = sorted(self.CurveData, key=lambda p: p.xvalue)
        
        # Below minimum X
        if x <= points[0].xvalue:
            return points[0].yvalue
        
        # Above maximum X
        if x >= points[-1].xvalue:
            return points[-1].yvalue
        
        # Find bracketing points
        for i in range(len(points) - 1):
            if points[i].xvalue <= x <= points[i + 1].xvalue:
                x0, y0 = points[i].xvalue, points[i].yvalue or 0
                x1, y1 = points[i + 1].xvalue, points[i + 1].yvalue or 0
                
                # Linear interpolation
                if x1 == x0:
                    return y0
                t = (x - x0) / (x1 - x0)
                return int(y0 + t * (y1 - y0))
        
        return None
    
    def get_axis_labels(self) -> tuple[str, str]:
        """
        Get human-readable axis labels based on curve type.
        
        Returns:
            Tuple of (x_label, y_label)
        """
        labels = {
            DERCurveType.FREQ_WATT: ("Frequency (Hz)", "% setMaxW"),
            DERCurveType.VOLT_VAR: ("% setVRef", "% setMaxVar"),
            DERCurveType.VOLT_WATT: ("% setVRef", "% setMaxW"),
            DERCurveType.WATT_PF: ("% setMaxW", "Power Factor"),
            DERCurveType.WATT_VAR: ("% setMaxW", "% setMaxVar"),
            DERCurveType.HFRT_MAY_TRIP: ("Time (s)", "Frequency (Hz)"),
            DERCurveType.HFRT_MUST_TRIP: ("Time (s)", "Frequency (Hz)"),
            DERCurveType.LFRT_MAY_TRIP: ("Time (s)", "Frequency (Hz)"),
            DERCurveType.LFRT_MUST_TRIP: ("Time (s)", "Frequency (Hz)"),
            DERCurveType.HVRT_MAY_TRIP: ("Time (s)", "% setVRef"),
            DERCurveType.HVRT_MOMENTARY_CESSATION: ("Time (s)", "% setVRef"),
            DERCurveType.HVRT_MUST_TRIP: ("Time (s)", "% setVRef"),
            DERCurveType.LVRT_MAY_TRIP: ("Time (s)", "% setVRef"),
            DERCurveType.LVRT_MOMENTARY_CESSATION: ("Time (s)", "% setVRef"),
            DERCurveType.LVRT_MUST_TRIP: ("Time (s)", "% setVRef"),
        }
        return labels.get(self.curveType, ("X", "Y"))


@dataclass_json
@dataclass
class DERCurveList:
    """
    List of DERCurve resources.
    
    Reference: IEEE Std 2030.5-2023
    """
    href: Optional[str] = None
    all_: int = 0  # Total count (renamed from 'all' to avoid Python keyword)
    results: int = 0
    DERCurve: List[DERCurve] = field(default_factory=list)
    
    def get_by_index(self, index: int) -> Optional[DERCurve]:
        """Get curve by index (for opMod*Curve references)."""
        if 0 <= index < len(self.DERCurve):
            return self.DERCurve[index]
        return None
    
    def get_by_type(self, curve_type: DERCurveType) -> List[DERCurve]:
        """Get all curves of a specific type."""
        return [c for c in self.DERCurve if c.curveType == curve_type]


# =============================================================================
# Factory Functions for Common Curve Types
# =============================================================================

def create_volt_var_curve(
    points: List[tuple[float, float]],
    mRID: Optional[str] = None,
    description: str = "Volt-VAR Curve"
) -> DERCurve:
    """
    Create a Volt-VAR curve.
    
    Args:
        points: List of (voltage_percent, var_percent) tuples
                voltage_percent: % of setVRef (e.g., 90.0, 110.0)
                var_percent: % of setMaxVar (-100 to +100)
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for Volt-VAR
        
    Example:
        # Create IEEE 1547-2018 default Volt-VAR curve
        curve = create_volt_var_curve([
            (92.0, 44.0),   # At 92% voltage, inject 44% VAR
            (98.0, 0.0),    # At 98% voltage, 0% VAR
            (102.0, 0.0),   # At 102% voltage, 0% VAR
            (108.0, -44.0), # At 108% voltage, absorb 44% VAR
        ])
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=DERCurveType.VOLT_VAR,
    )
    for v_pct, var_pct in points:
        curve.add_point(int(v_pct * 100), int(var_pct * 100))
    return curve


def create_freq_watt_curve(
    points: List[tuple[float, float]],
    mRID: Optional[str] = None,
    description: str = "Frequency-Watt Curve"
) -> DERCurve:
    """
    Create a Frequency-Watt curve.
    
    Args:
        points: List of (frequency_hz, power_percent) tuples
                frequency_hz: Frequency in Hz
                power_percent: % of setMaxW (-100 to +100)
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for Freq-Watt
        
    Example:
        # Frequency droop curve
        curve = create_freq_watt_curve([
            (59.0, 100.0),  # Below 59Hz: 100% power
            (60.0, 100.0),  # At 60Hz: 100% power (nominal)
            (60.5, 0.0),    # At 60.5Hz: 0% power
        ])
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=DERCurveType.FREQ_WATT,
        xMultiplier=-1,  # Hz * 10^-1 = 0.1 Hz resolution
    )
    for freq_hz, power_pct in points:
        # Store frequency as integer * 10 for 0.1 Hz resolution
        curve.add_point(int(freq_hz * 10), int(power_pct * 100))
    return curve


def create_volt_watt_curve(
    points: List[tuple[float, float]],
    mRID: Optional[str] = None,
    description: str = "Volt-Watt Curve"
) -> DERCurve:
    """
    Create a Volt-Watt curve.
    
    Args:
        points: List of (voltage_percent, power_percent) tuples
                voltage_percent: % of setVRef
                power_percent: % of setMaxW
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for Volt-Watt
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=DERCurveType.VOLT_WATT,
    )
    for v_pct, power_pct in points:
        curve.add_point(int(v_pct * 100), int(power_pct * 100))
    return curve


def create_watt_pf_curve(
    points: List[tuple[float, float, bool]],
    mRID: Optional[str] = None,
    description: str = "Watt-PF Curve"
) -> DERCurve:
    """
    Create a Watt-PF curve.
    
    Args:
        points: List of (power_percent, power_factor, overexcited) tuples
                power_percent: % of setMaxW
                power_factor: Power factor (0.0 to 1.0)
                overexcited: True = leading, False = lagging
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for Watt-PF
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=DERCurveType.WATT_PF,
    )
    for power_pct, pf, overexcited in points:
        curve.add_point(
            int(power_pct * 100),
            int(pf * 10000),
            overexcited
        )
    return curve


def create_lvrt_curve(
    points: List[tuple[float, float]],
    curve_type: DERCurveType = DERCurveType.LVRT_MUST_TRIP,
    mRID: Optional[str] = None,
    description: str = "LVRT Curve"
) -> DERCurve:
    """
    Create a Low Voltage Ride-Through curve.
    
    Args:
        points: List of (time_seconds, voltage_percent) tuples
                time_seconds: Time in seconds
                voltage_percent: % of setVRef
        curve_type: One of LVRT_MAY_TRIP, LVRT_MOMENTARY_CESSATION, LVRT_MUST_TRIP
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for LVRT
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=curve_type,
    )
    for time_s, v_pct in points:
        # Store time as integer * 10 for 0.1s resolution
        curve.add_point(int(time_s * 10), int(v_pct * 100))
    return curve


def create_hvrt_curve(
    points: List[tuple[float, float]],
    curve_type: DERCurveType = DERCurveType.HVRT_MUST_TRIP,
    mRID: Optional[str] = None,
    description: str = "HVRT Curve"
) -> DERCurve:
    """
    Create a High Voltage Ride-Through curve.
    
    Args:
        points: List of (time_seconds, voltage_percent) tuples
        curve_type: One of HVRT_MAY_TRIP, HVRT_MOMENTARY_CESSATION, HVRT_MUST_TRIP
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for HVRT
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=curve_type,
    )
    for time_s, v_pct in points:
        curve.add_point(int(time_s * 10), int(v_pct * 100))
    return curve


def create_lfrt_curve(
    points: List[tuple[float, float]],
    curve_type: DERCurveType = DERCurveType.LFRT_MUST_TRIP,
    mRID: Optional[str] = None,
    description: str = "LFRT Curve"
) -> DERCurve:
    """
    Create a Low Frequency Ride-Through curve.
    
    Args:
        points: List of (time_seconds, frequency_hz) tuples
        curve_type: One of LFRT_MAY_TRIP, LFRT_MUST_TRIP
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for LFRT
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=curve_type,
        xMultiplier=-1,
    )
    for time_s, freq_hz in points:
        curve.add_point(int(time_s * 10), int(freq_hz * 10))
    return curve


def create_hfrt_curve(
    points: List[tuple[float, float]],
    curve_type: DERCurveType = DERCurveType.HFRT_MUST_TRIP,
    mRID: Optional[str] = None,
    description: str = "HFRT Curve"
) -> DERCurve:
    """
    Create a High Frequency Ride-Through curve.
    
    Args:
        points: List of (time_seconds, frequency_hz) tuples
        curve_type: One of HFRT_MAY_TRIP, HFRT_MUST_TRIP
        mRID: Optional curve identifier
        description: Curve description
        
    Returns:
        Configured DERCurve for HFRT
    """
    curve = DERCurve(
        mRID=mRID,
        description=description,
        curveType=curve_type,
        xMultiplier=-1,
    )
    for time_s, freq_hz in points:
        curve.add_point(int(time_s * 10), int(freq_hz * 10))
    return curve


# =============================================================================
# IEEE 1547-2018 Default Curves (Annex Examples)
# =============================================================================

def create_ieee1547_default_volt_var() -> DERCurve:
    """
    Create IEEE 1547-2018 default Volt-VAR curve.
    
    Reference: IEEE Std 1547-2018 Table 8, Category B
    
    Returns:
        Default Volt-VAR curve per IEEE 1547-2018
    """
    return create_volt_var_curve(
        points=[
            (92.0, 44.0),    # V1=0.92 pu, Q1=44% Qmax (inject)
            (98.0, 0.0),     # V2=0.98 pu, Q2=0
            (102.0, 0.0),    # V3=1.02 pu, Q3=0
            (108.0, -44.0),  # V4=1.08 pu, Q4=-44% Qmax (absorb)
        ],
        mRID="IEEE1547-VoltVar-Default",
        description="IEEE 1547-2018 Category B Default Volt-VAR"
    )


def create_ieee1547_default_volt_watt() -> DERCurve:
    """
    Create IEEE 1547-2018 default Volt-Watt curve.
    
    Reference: IEEE Std 1547-2018 Table 10
    
    Returns:
        Default Volt-Watt curve per IEEE 1547-2018
    """
    return create_volt_watt_curve(
        points=[
            (100.0, 100.0),  # At nominal voltage, full power
            (106.0, 100.0),  # Up to 1.06 pu, full power
            (110.0, 0.0),    # At 1.10 pu, curtail to 0%
        ],
        mRID="IEEE1547-VoltWatt-Default",
        description="IEEE 1547-2018 Default Volt-Watt"
    )


def create_ieee1547_category_i_lvrt() -> DERCurve:
    """
    Create IEEE 1547-2018 Category I LVRT curve (Must Trip).
    
    Reference: IEEE Std 1547-2018 Table 5
    
    Returns:
        Category I LVRT curve
    """
    return create_lvrt_curve(
        points=[
            (0.0, 0.0),      # Immediate trip below 0%
            (0.16, 50.0),    # 160ms at 50%
            (2.0, 70.0),     # 2s at 70%
            (10.0, 88.0),    # 10s at 88%
        ],
        curve_type=DERCurveType.LVRT_MUST_TRIP,
        mRID="IEEE1547-Cat1-LVRT",
        description="IEEE 1547-2018 Category I LVRT"
    )


def create_ieee1547_category_ii_lvrt() -> DERCurve:
    """
    Create IEEE 1547-2018 Category II LVRT curve (Must Trip).
    
    Reference: IEEE Std 1547-2018 Table 5
    
    Returns:
        Category II LVRT curve
    """
    return create_lvrt_curve(
        points=[
            (0.0, 0.0),      # Immediate trip below 0%
            (0.16, 30.0),    # 160ms at 30%
            (2.0, 65.0),     # 2s at 65%
            (10.0, 88.0),    # 10s at 88%
        ],
        curve_type=DERCurveType.LVRT_MUST_TRIP,
        mRID="IEEE1547-Cat2-LVRT",
        description="IEEE 1547-2018 Category II LVRT"
    )


def create_ieee1547_category_iii_lvrt() -> DERCurve:
    """
    Create IEEE 1547-2018 Category III LVRT curve (Must Trip).
    
    Reference: IEEE Std 1547-2018 Table 5
    
    Returns:
        Category III LVRT curve (most ride-through capable)
    """
    return create_lvrt_curve(
        points=[
            (0.0, 0.0),      # Immediate trip below 0%
            (1.0, 0.0),      # 1s at 0% (momentary)
            (4.0, 50.0),     # 4s at 50%
            (10.0, 88.0),    # 10s at 88%
        ],
        curve_type=DERCurveType.LVRT_MUST_TRIP,
        mRID="IEEE1547-Cat3-LVRT",
        description="IEEE 1547-2018 Category III LVRT"
    )
