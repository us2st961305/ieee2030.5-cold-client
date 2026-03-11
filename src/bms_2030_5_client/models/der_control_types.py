"""
IEEE 2030.5-2023 DER Control Types and DERControlBase Complete Implementation.

This module provides the complete DERControlBase with all 40+ control modes
as defined in IEEE Std 2030.5-2023 Section 10.10.

Reference: IEEE Std 2030.5-2023
- Table 32: DERControlType bit definitions
- Table 33: DERControlType2 bit definitions (new in 2023)
- Section 10.10: DERControlBase element definitions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag
from typing import Optional, List
from dataclasses_json import dataclass_json


# =============================================================================
# DERControlType Bit Definitions (HexBinary32 - Table 32)
# =============================================================================

class DERControlType(IntFlag):
    """
    DER Control Type bitmap (HexBinary32).
    
    Reference: IEEE Std 2030.5-2023 Table 32
    
    Each bit indicates whether the corresponding control mode is present
    in a DERControlBase. Used for responseRequired and modesSupported fields.
    """
    # Bit 0: Connect/Disconnect
    OP_MOD_CONNECT = 0x00000001
    
    # Bit 1: Energize/De-energize
    OP_MOD_ENERGIZE = 0x00000002
    
    # Bit 2: Fixed Power Factor (Absorbing W)
    OP_MOD_FIXED_PF_ABSORB_W = 0x00000004
    
    # Bit 3: Fixed Power Factor (Injecting W)
    OP_MOD_FIXED_PF_INJECT_W = 0x00000008
    
    # Bit 4: Fixed Reactive Power (VAR)
    OP_MOD_FIXED_VAR = 0x00000010
    
    # Bit 5: Fixed Active Power (W)
    OP_MOD_FIXED_W = 0x00000020
    
    # Bit 6: Frequency Droop
    OP_MOD_FREQ_DROOP = 0x00000040
    
    # Bit 7: Frequency-Watt Curve
    OP_MOD_FREQ_WATT = 0x00000080
    
    # Bit 8: High Frequency Ride Through (May Trip)
    OP_MOD_HFRT_MAY_TRIP = 0x00000100
    
    # Bit 9: High Frequency Ride Through (Must Trip)
    OP_MOD_HFRT_MUST_TRIP = 0x00000200
    
    # Bit 10: High Voltage Ride Through (May Trip)
    OP_MOD_HVRT_MAY_TRIP = 0x00000400
    
    # Bit 11: High Voltage Ride Through (Momentary Cessation)
    OP_MOD_HVRT_MOMENTARY_CESSATION = 0x00000800
    
    # Bit 12: High Voltage Ride Through (Must Trip)
    OP_MOD_HVRT_MUST_TRIP = 0x00001000
    
    # Bit 13: Low Frequency Ride Through (May Trip)
    OP_MOD_LFRT_MAY_TRIP = 0x00002000
    
    # Bit 14: Low Frequency Ride Through (Must Trip)
    OP_MOD_LFRT_MUST_TRIP = 0x00004000
    
    # Bit 15: Low Voltage Ride Through (May Trip)
    OP_MOD_LVRT_MAY_TRIP = 0x00008000
    
    # Bit 16: Low Voltage Ride Through (Momentary Cessation)
    OP_MOD_LVRT_MOMENTARY_CESSATION = 0x00010000
    
    # Bit 17: Low Voltage Ride Through (Must Trip)
    OP_MOD_LVRT_MUST_TRIP = 0x00020000
    
    # Bit 18: Maximum Active Power Limit
    OP_MOD_MAX_LIM_W = 0x00040000
    
    # Bit 19: Target Reactive Power
    OP_MOD_TARGET_VAR = 0x00080000
    
    # Bit 20: Target Active Power
    OP_MOD_TARGET_W = 0x00100000
    
    # Bit 21: Volt-VAR Curve
    OP_MOD_VOLT_VAR = 0x00200000
    
    # Bit 22: Volt-Watt Curve
    OP_MOD_VOLT_WATT = 0x00400000
    
    # Bit 23: Watt-PF Curve
    OP_MOD_WATT_PF = 0x00800000
    
    # Bit 24: Watt-VAR Curve
    OP_MOD_WATT_VAR = 0x01000000
    
    # Bits 25-31: Reserved


class DERControlType2(IntFlag):
    """
    DER Control Type 2 bitmap (HexBinary32) - IEEE 2030.5-2023 新增.
    
    Reference: IEEE Std 2030.5-2023 Table 33
    
    Additional control modes introduced in IEEE 2030.5-2023.
    """
    # Bit 0: Delta Active Power
    OP_MOD_DELTA_W = 0x00000001
    
    # Bit 1: Delta Reactive Power
    OP_MOD_DELTA_VAR = 0x00000002
    
    # Bit 2: Grid Connect Permit
    OP_MOD_GRID_CONNECT_PERMIT = 0x00000004
    
    # Bit 3: Island Permit
    OP_MOD_ISLAND_PERMIT = 0x00000008
    
    # Bit 4: Maximum Limit Active Power Absorb
    OP_MOD_MAX_LIM_W_ABSORB = 0x00000010
    
    # Bit 5: Maximum Limit Active Power Inject
    OP_MOD_MAX_LIM_W_INJECT = 0x00000020
    
    # Bit 6: Maximum Limit Percent Active Power Absorb
    OP_MOD_MAX_LIM_PCT_W_ABSORB = 0x00000040
    
    # Bit 7: Maximum Limit Reactive Power Absorb
    OP_MOD_MAX_LIM_VAR_ABSORB = 0x00000080
    
    # Bit 8: Maximum Limit Reactive Power Inject
    OP_MOD_MAX_LIM_VAR_INJECT = 0x00000100
    
    # Bit 9: Maximum Limit Percent Reactive Power Absorb
    OP_MOD_MAX_LIM_PCT_VAR_ABSORB = 0x00000200
    
    # Bit 10: Maximum Limit Percent Reactive Power Inject
    OP_MOD_MAX_LIM_PCT_VAR_INJECT = 0x00000400
    
    # Bit 11: Maximum Apparent Power
    OP_MOD_MAX_VA = 0x00000800
    
    # Bit 12: Maximum Absorb Apparent Power
    OP_MOD_MAX_ABSORB_VA = 0x00001000
    
    # Bits 13-31: Reserved


# =============================================================================
# Control Value Types
# =============================================================================

@dataclass_json
@dataclass
class SignedPerCentControlType:
    """
    Signed percentage control type (-100.00% to +100.00%).
    
    value range: -10000 to 10000 (representing -100.00% to +100.00%)
    multiplier: power of 10 adjustment
    """
    value: int = 0
    multiplier: int = 0
    
    def to_percent(self) -> float:
        """Convert to percentage (-100.0 to +100.0)."""
        return (self.value * (10 ** self.multiplier)) / 100.0
    
    @classmethod
    def from_percent(cls, percent: float) -> "SignedPerCentControlType":
        """Create from percentage value."""
        return cls(value=int(percent * 100), multiplier=0)


@dataclass_json
@dataclass
class PerCentControlType:
    """
    Unsigned percentage control type (0.00% to 100.00%).
    
    value range: 0 to 10000 (representing 0.00% to 100.00%)
    """
    value: int = 0
    
    def to_percent(self) -> float:
        """Convert to percentage (0.0 to 100.0)."""
        return self.value / 100.0
    
    @classmethod
    def from_percent(cls, percent: float) -> "PerCentControlType":
        """Create from percentage value (0.0 to 100.0)."""
        return cls(value=int(max(0, min(100, percent)) * 100))


@dataclass_json
@dataclass
class ActivePowerControlType:
    """
    Signed active power control type (Watts).
    
    value × 10^multiplier = actual watts
    Positive = discharge/inject, Negative = charge/absorb
    """
    value: int = 0
    multiplier: int = 0
    
    def to_watts(self) -> int:
        """Convert to watts."""
        return int(self.value * (10 ** self.multiplier))
    
    @classmethod
    def from_watts(cls, watts: int) -> "ActivePowerControlType":
        """Create from watts value."""
        if abs(watts) >= 1000000:
            return cls(value=watts // 1000000, multiplier=6)
        elif abs(watts) >= 1000:
            return cls(value=watts // 1000, multiplier=3)
        return cls(value=watts, multiplier=0)


@dataclass_json
@dataclass
class UnsignedActivePowerControlType:
    """
    Unsigned active power control type (Watts >= 0).
    """
    value: int = 0
    multiplier: int = 0
    
    def to_watts(self) -> int:
        """Convert to watts."""
        return int(self.value * (10 ** self.multiplier))


@dataclass_json
@dataclass
class ActivePowerDeltaControlType:
    """
    Active power delta control type.
    
    For opModDeltaW - incremental power change.
    """
    value: int = 0
    multiplier: int = 0
    
    def to_watts(self) -> int:
        """Convert to watts delta."""
        return int(self.value * (10 ** self.multiplier))


@dataclass_json
@dataclass
class ReactivePowerControlType:
    """
    Signed reactive power control type (VAR).
    
    value × 10^multiplier = actual VAR
    Positive = capacitive, Negative = inductive
    """
    value: int = 0
    multiplier: int = 0
    
    def to_var(self) -> int:
        """Convert to VAR."""
        return int(self.value * (10 ** self.multiplier))
    
    @classmethod
    def from_var(cls, var: int) -> "ReactivePowerControlType":
        """Create from VAR value."""
        if abs(var) >= 1000000:
            return cls(value=var // 1000000, multiplier=6)
        elif abs(var) >= 1000:
            return cls(value=var // 1000, multiplier=3)
        return cls(value=var, multiplier=0)


@dataclass_json
@dataclass
class UnsignedReactivePowerControlType:
    """
    Unsigned reactive power control type (VAR >= 0).
    """
    value: int = 0
    multiplier: int = 0
    
    def to_var(self) -> int:
        """Convert to VAR."""
        return int(self.value * (10 ** self.multiplier))


@dataclass_json
@dataclass
class ReactivePowerDeltaControlType:
    """
    Reactive power delta control type.
    
    For opModDeltaVar - incremental VAR change.
    """
    value: int = 0
    multiplier: int = 0
    
    def to_var(self) -> int:
        """Convert to VAR delta."""
        return int(self.value * (10 ** self.multiplier))


@dataclass_json
@dataclass
class FixedVarControlType:
    """
    Fixed VAR control type as percentage of setMaxVar.
    
    value range: -10000 to 10000 (-100.00% to +100.00%)
    """
    value: int = 0
    
    def to_percent(self) -> float:
        """Convert to percentage of setMaxVar."""
        return self.value / 100.0


@dataclass_json
@dataclass
class UnsignedFixedVarControlType:
    """
    Unsigned fixed VAR control type (0 to 100.00%).
    """
    value: int = 0
    
    def to_percent(self) -> float:
        """Convert to percentage."""
        return self.value / 100.0


@dataclass_json
@dataclass
class PowerFactorWithExcitationControlType:
    """
    Power factor with excitation control type.
    
    displacement: Power factor as Int16 (-1.0000 to 1.0000, scaled by 10000)
    excitation: True = overexcited/leading, False = underexcited/lagging
    """
    displacement: int = 10000  # Default: 1.0 power factor
    excitation: bool = True
    
    def to_power_factor(self) -> float:
        """Get power factor value (-1.0 to 1.0)."""
        return self.displacement / 10000.0
    
    @classmethod
    def from_pf(cls, pf: float, overexcited: bool = True) -> "PowerFactorWithExcitationControlType":
        """Create from power factor and excitation."""
        return cls(
            displacement=int(max(-10000, min(10000, pf * 10000))),
            excitation=overexcited
        )


@dataclass_json
@dataclass
class ApparentPowerControlType:
    """
    Apparent power control type (VA).
    """
    value: int = 0
    multiplier: int = 0
    
    def to_va(self) -> int:
        """Convert to VA."""
        return int(self.value * (10 ** self.multiplier))


@dataclass_json
@dataclass
class FreqDroopControlType:
    """
    Frequency droop control type.
    
    For opModFreqDroop - frequency response settings.
    
    dbOF: Deadband offset frequency (Hz, scaled)
    dbUF: Deadband underfrequency (Hz, scaled)
    kOF: Slope for overfrequency (% per Hz)
    kUF: Slope for underfrequency (% per Hz)
    openLoopTms: Open loop response time (ms)
    """
    dbOF: int = 0         # Deadband offset frequency
    dbUF: int = 0         # Deadband underfrequency
    kOF: int = 0          # Overfrequency slope
    kUF: int = 0          # Underfrequency slope
    openLoopTms: int = 0  # Open loop response time (ms)


@dataclass_json
@dataclass
class VoltageControlType:
    """
    Voltage control type (Volts).
    """
    value: int = 0
    multiplier: int = 0
    
    def to_volts(self) -> float:
        """Convert to volts."""
        return self.value * (10 ** self.multiplier)


# =============================================================================
# Complete DERControlBase (IEEE 2030.5-2023)
# =============================================================================

@dataclass_json
@dataclass
class DERControlBaseComplete:
    """
    Complete IEEE 2030.5-2023 DERControlBase with all 40+ control modes.
    
    Reference: IEEE Std 2030.5-2023 Section 10.10
    
    Power Sign Convention:
        - Positive (+): Discharge/Inject (export to grid)
        - Negative (-): Charge/Absorb (import from grid)
    
    Categories:
        1. Connection Control (opModConnect, opModEnergize, etc.)
        2. Active Power Control (opModFixedW, opModDeltaW, etc.)
        3. Reactive Power Control (opModFixedVar, opModDeltaVar, etc.)
        4. Power Factor Control (opModFixedPFAbsorbW, opModFixedPFInjectW)
        5. Voltage Control (vRef, vRefOfs)
        6. Apparent Power Control (opModMaxVA, etc.)
        7. Frequency Droop Control (opModFreqDroop)
        8. Curve References (opModFreqWatt, opModVoltVar, etc.)
        9. Ride-Through Curves (HFRT, HVRT, LFRT, LVRT)
        10. Ramp Rate Settings (rampTms)
    """
    
    # =========================================================================
    # 1. Connection Control
    # =========================================================================
    
    # Connect/Disconnect from grid
    opModConnect: Optional[bool] = None
    
    # Energize/De-energize (enable output)
    opModEnergize: Optional[bool] = None
    
    # Grid connect permit (IEEE 2030.5-2023)
    opModGridConnectPermit: Optional[bool] = None
    
    # Island permit (IEEE 2030.5-2023)
    opModIslandPermit: Optional[bool] = None
    
    # =========================================================================
    # 2. Active Power Control
    # =========================================================================
    
    # Fixed active power setpoint (% of setMaxW)
    opModFixedW: Optional[SignedPerCentControlType] = None
    
    # Delta/incremental active power change (IEEE 2030.5-2023)
    opModDeltaW: Optional[ActivePowerDeltaControlType] = None
    
    # Target active power (absolute watts)
    opModTargetW: Optional[ActivePowerControlType] = None
    
    # Maximum active power limit (% of setMaxW)
    opModMaxLimW: Optional[PerCentControlType] = None
    
    # Maximum active power absorb limit (watts) - IEEE 2030.5-2023
    opModMaxLimWAbsorb: Optional[UnsignedActivePowerControlType] = None
    
    # Maximum active power inject limit (watts) - IEEE 2030.5-2023
    opModMaxLimWInject: Optional[UnsignedActivePowerControlType] = None
    
    # Maximum active power absorb limit (% of setMaxW) - IEEE 2030.5-2023
    opModMaxLimPctWAbsorb: Optional[PerCentControlType] = None
    
    # =========================================================================
    # 3. Reactive Power Control
    # =========================================================================
    
    # Fixed reactive power setpoint (% of setMaxVar)
    opModFixedVar: Optional[FixedVarControlType] = None
    
    # Delta/incremental reactive power change (IEEE 2030.5-2023)
    opModDeltaVar: Optional[ReactivePowerDeltaControlType] = None
    
    # Target reactive power (absolute VAR)
    opModTargetVar: Optional[ReactivePowerControlType] = None
    
    # Maximum reactive power absorb limit (VAR) - IEEE 2030.5-2023
    opModMaxLimVarAbsorb: Optional[UnsignedReactivePowerControlType] = None
    
    # Maximum reactive power inject limit (VAR) - IEEE 2030.5-2023
    opModMaxLimVarInject: Optional[UnsignedReactivePowerControlType] = None
    
    # Maximum reactive power absorb limit (%) - IEEE 2030.5-2023
    opModMaxLimPctVarAbsorb: Optional[UnsignedFixedVarControlType] = None
    
    # Maximum reactive power inject limit (%) - IEEE 2030.5-2023
    opModMaxLimPctVarInject: Optional[UnsignedFixedVarControlType] = None
    
    # =========================================================================
    # 4. Power Factor Control
    # =========================================================================
    
    # Fixed power factor when absorbing W
    opModFixedPFAbsorbW: Optional[PowerFactorWithExcitationControlType] = None
    
    # Fixed power factor when injecting W
    opModFixedPFInjectW: Optional[PowerFactorWithExcitationControlType] = None
    
    # =========================================================================
    # 5. Voltage Control
    # =========================================================================
    
    # Reference voltage for volt-var and volt-watt curves
    vRef: Optional[VoltageControlType] = None
    
    # Reference voltage offset
    vRefOfs: Optional[VoltageControlType] = None
    
    # =========================================================================
    # 6. Apparent Power Control (IEEE 2030.5-2023)
    # =========================================================================
    
    # Maximum apparent power limit (VA)
    opModMaxVA: Optional[ApparentPowerControlType] = None
    
    # Maximum apparent power absorb limit (VA)
    opModMaxAbsorbVA: Optional[ApparentPowerControlType] = None
    
    # =========================================================================
    # 7. Frequency Droop Control
    # =========================================================================
    
    # Frequency droop parameters
    opModFreqDroop: Optional[FreqDroopControlType] = None
    
    # =========================================================================
    # 8. Curve References (DERCurve index)
    # =========================================================================
    
    # Frequency-Watt curve index
    opModFreqWatt: Optional[int] = None
    
    # Volt-VAR curve index
    opModVoltVar: Optional[int] = None
    
    # Volt-Watt curve index
    opModVoltWatt: Optional[int] = None
    
    # Watt-PF curve index
    opModWattPF: Optional[int] = None
    
    # Watt-VAR curve index
    opModWattVar: Optional[int] = None
    
    # =========================================================================
    # 9. Ride-Through Curve References
    # =========================================================================
    
    # High Frequency Ride-Through curves
    opModHFRTMayTrip: Optional[int] = None       # May trip curve index
    opModHFRTMustTrip: Optional[int] = None      # Must trip curve index
    
    # High Voltage Ride-Through curves
    opModHVRTMayTrip: Optional[int] = None       # May trip curve index
    opModHVRTMomentaryCessation: Optional[int] = None  # Momentary cessation curve
    opModHVRTMustTrip: Optional[int] = None      # Must trip curve index
    
    # Low Frequency Ride-Through curves
    opModLFRTMayTrip: Optional[int] = None       # May trip curve index
    opModLFRTMustTrip: Optional[int] = None      # Must trip curve index
    
    # Low Voltage Ride-Through curves
    opModLVRTMayTrip: Optional[int] = None       # May trip curve index
    opModLVRTMomentaryCessation: Optional[int] = None  # Momentary cessation curve
    opModLVRTMustTrip: Optional[int] = None      # Must trip curve index
    
    # =========================================================================
    # 10. Ramp Rate Settings
    # =========================================================================
    
    # Ramp time for power changes (seconds)
    rampTms: Optional[int] = None
    
    def get_control_type_bitmap(self) -> int:
        """
        Get DERControlType bitmap based on which modes are set.
        
        Returns:
            int: Bitmap of active control modes
        """
        bitmap = 0
        
        if self.opModConnect is not None:
            bitmap |= DERControlType.OP_MOD_CONNECT
        if self.opModEnergize is not None:
            bitmap |= DERControlType.OP_MOD_ENERGIZE
        if self.opModFixedPFAbsorbW is not None:
            bitmap |= DERControlType.OP_MOD_FIXED_PF_ABSORB_W
        if self.opModFixedPFInjectW is not None:
            bitmap |= DERControlType.OP_MOD_FIXED_PF_INJECT_W
        if self.opModFixedVar is not None:
            bitmap |= DERControlType.OP_MOD_FIXED_VAR
        if self.opModFixedW is not None:
            bitmap |= DERControlType.OP_MOD_FIXED_W
        if self.opModFreqDroop is not None:
            bitmap |= DERControlType.OP_MOD_FREQ_DROOP
        if self.opModFreqWatt is not None:
            bitmap |= DERControlType.OP_MOD_FREQ_WATT
        if self.opModHFRTMayTrip is not None:
            bitmap |= DERControlType.OP_MOD_HFRT_MAY_TRIP
        if self.opModHFRTMustTrip is not None:
            bitmap |= DERControlType.OP_MOD_HFRT_MUST_TRIP
        if self.opModHVRTMayTrip is not None:
            bitmap |= DERControlType.OP_MOD_HVRT_MAY_TRIP
        if self.opModHVRTMomentaryCessation is not None:
            bitmap |= DERControlType.OP_MOD_HVRT_MOMENTARY_CESSATION
        if self.opModHVRTMustTrip is not None:
            bitmap |= DERControlType.OP_MOD_HVRT_MUST_TRIP
        if self.opModLFRTMayTrip is not None:
            bitmap |= DERControlType.OP_MOD_LFRT_MAY_TRIP
        if self.opModLFRTMustTrip is not None:
            bitmap |= DERControlType.OP_MOD_LFRT_MUST_TRIP
        if self.opModLVRTMayTrip is not None:
            bitmap |= DERControlType.OP_MOD_LVRT_MAY_TRIP
        if self.opModLVRTMomentaryCessation is not None:
            bitmap |= DERControlType.OP_MOD_LVRT_MOMENTARY_CESSATION
        if self.opModLVRTMustTrip is not None:
            bitmap |= DERControlType.OP_MOD_LVRT_MUST_TRIP
        if self.opModMaxLimW is not None:
            bitmap |= DERControlType.OP_MOD_MAX_LIM_W
        if self.opModTargetVar is not None:
            bitmap |= DERControlType.OP_MOD_TARGET_VAR
        if self.opModTargetW is not None:
            bitmap |= DERControlType.OP_MOD_TARGET_W
        if self.opModVoltVar is not None:
            bitmap |= DERControlType.OP_MOD_VOLT_VAR
        if self.opModVoltWatt is not None:
            bitmap |= DERControlType.OP_MOD_VOLT_WATT
        if self.opModWattPF is not None:
            bitmap |= DERControlType.OP_MOD_WATT_PF
        if self.opModWattVar is not None:
            bitmap |= DERControlType.OP_MOD_WATT_VAR
            
        return bitmap
    
    def get_control_type2_bitmap(self) -> int:
        """
        Get DERControlType2 bitmap for IEEE 2030.5-2023 modes.
        
        Returns:
            int: Bitmap of active Type2 control modes
        """
        bitmap = 0
        
        if self.opModDeltaW is not None:
            bitmap |= DERControlType2.OP_MOD_DELTA_W
        if self.opModDeltaVar is not None:
            bitmap |= DERControlType2.OP_MOD_DELTA_VAR
        if self.opModGridConnectPermit is not None:
            bitmap |= DERControlType2.OP_MOD_GRID_CONNECT_PERMIT
        if self.opModIslandPermit is not None:
            bitmap |= DERControlType2.OP_MOD_ISLAND_PERMIT
        if self.opModMaxLimWAbsorb is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_LIM_W_ABSORB
        if self.opModMaxLimWInject is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_LIM_W_INJECT
        if self.opModMaxLimPctWAbsorb is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_LIM_PCT_W_ABSORB
        if self.opModMaxLimVarAbsorb is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_LIM_VAR_ABSORB
        if self.opModMaxLimVarInject is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_LIM_VAR_INJECT
        if self.opModMaxLimPctVarAbsorb is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_LIM_PCT_VAR_ABSORB
        if self.opModMaxLimPctVarInject is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_LIM_PCT_VAR_INJECT
        if self.opModMaxVA is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_VA
        if self.opModMaxAbsorbVA is not None:
            bitmap |= DERControlType2.OP_MOD_MAX_ABSORB_VA
            
        return bitmap
    
    def to_control_type_hex(self) -> str:
        """Get DERControlType as HexBinary32 string."""
        return f"{self.get_control_type_bitmap():08X}"
    
    def to_control_type2_hex(self) -> str:
        """Get DERControlType2 as HexBinary32 string."""
        return f"{self.get_control_type2_bitmap():08X}"
    
    def get_power_setpoint_watts(self) -> Optional[int]:
        """
        Get the effective power setpoint in watts.
        
        Priority: opModFixedW > opModTargetW
        """
        if self.opModFixedW is not None:
            # opModFixedW is percentage of setMaxW
            # Caller must multiply by setMaxW
            return None  # Percentage, not absolute
        if self.opModTargetW is not None:
            return self.opModTargetW.to_watts()
        return None
    
    def is_connect_mode(self) -> bool:
        """Check if connect mode is enabled."""
        return self.opModConnect is True
    
    def is_energize_mode(self) -> bool:
        """Check if energize mode is enabled."""
        return self.opModEnergize is True


# =============================================================================
# Helper Functions
# =============================================================================

def control_type_to_mode_names(bitmap: int) -> List[str]:
    """
    Convert DERControlType bitmap to list of mode names.
    
    Args:
        bitmap: DERControlType bitmap value
        
    Returns:
        List of mode name strings
    """
    modes = []
    for mode in DERControlType:
        if bitmap & mode:
            modes.append(mode.name)
    return modes


def control_type2_to_mode_names(bitmap: int) -> List[str]:
    """
    Convert DERControlType2 bitmap to list of mode names.
    
    Args:
        bitmap: DERControlType2 bitmap value
        
    Returns:
        List of mode name strings
    """
    modes = []
    for mode in DERControlType2:
        if bitmap & mode:
            modes.append(mode.name)
    return modes
