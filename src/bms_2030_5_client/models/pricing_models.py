"""
IEEE 2030.5-2023 Tariff Profile and Pricing Function Set.

This module provides the complete Pricing implementation including:
- TariffProfile: Container for rate information
- RateComponent: Individual rate periods/tiers
- TimeTariffInterval: Time-based pricing intervals
- ConsumptionTariffInterval: Consumption-based pricing tiers
- PrimacyType: Priority enumeration for overlapping tariffs

Reference: IEEE Std 2030.5-2023
- Section 10.12: Pricing Function Set
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List, Dict
from dataclasses_json import dataclass_json


# =============================================================================
# Currency Type
# =============================================================================

class CurrencyType(IntEnum):
    """
    ISO 4217 Currency Codes.
    
    Common currency codes used in pricing information.
    """
    USD = 840  # United States Dollar
    EUR = 978  # Euro
    GBP = 826  # British Pound
    JPY = 392  # Japanese Yen
    CNY = 156  # Chinese Yuan
    TWD = 901  # Taiwan Dollar
    CAD = 124  # Canadian Dollar
    AUD = 36   # Australian Dollar
    NZD = 554  # New Zealand Dollar
    KRW = 410  # South Korean Won
    HKD = 344  # Hong Kong Dollar
    SGD = 702  # Singapore Dollar
    CHF = 756  # Swiss Franc
    INR = 356  # Indian Rupee
    BRL = 986  # Brazilian Real
    MXN = 484  # Mexican Peso


# =============================================================================
# Tariff Type
# =============================================================================

class TariffType(IntEnum):
    """
    Tariff Type enumeration.
    
    Defines the type of tariff/rate schedule.
    """
    # 0: Time of Use (TOU)
    TIME_OF_USE = 0
    
    # 1: Tiered (block) pricing
    TIERED = 1
    
    # 2: Real-time pricing (RTP)
    REAL_TIME = 2
    
    # 3: Critical peak pricing (CPP)
    CRITICAL_PEAK = 3
    
    # 4: Variable peak pricing (VPP)
    VARIABLE_PEAK = 4
    
    # 5: Dynamic pricing
    DYNAMIC = 5
    
    # 6: Flat rate
    FLAT = 6
    
    # 7: Demand-based
    DEMAND = 7


# =============================================================================
# Consumption Block Type
# =============================================================================

class ConsumptionBlockType(IntEnum):
    """
    Consumption block/tier type.
    
    Indicates which tier a consumption falls into.
    """
    # 0: Not applicable
    NOT_APPLICABLE = 0
    
    # 1: Block 1 (typically lowest/first tier)
    BLOCK_1 = 1
    
    # 2: Block 2
    BLOCK_2 = 2
    
    # 3: Block 3
    BLOCK_3 = 3
    
    # 4: Block 4
    BLOCK_4 = 4
    
    # 5: Block 5
    BLOCK_5 = 5
    
    # 6-15: Additional blocks
    BLOCK_6 = 6
    BLOCK_7 = 7
    BLOCK_8 = 8
    BLOCK_9 = 9
    BLOCK_10 = 10


# =============================================================================
# TOU Tier Type
# =============================================================================

class TOUTierType(IntEnum):
    """
    Time of Use tier type.
    
    Standard TOU period classifications.
    """
    # 0: Not applicable
    NOT_APPLICABLE = 0
    
    # 1: Off-peak
    OFF_PEAK = 1
    
    # 2: Mid-peak (shoulder)
    MID_PEAK = 2
    
    # 3: On-peak
    ON_PEAK = 3
    
    # 4: Critical peak
    CRITICAL_PEAK = 4
    
    # 5: Super off-peak
    SUPER_OFF_PEAK = 5


# =============================================================================
# Price Value Type
# =============================================================================

@dataclass_json
@dataclass
class PriceValue:
    """
    Price value with currency and multiplier.
    
    value × 10^powerOfTenMultiplier = price in currency units
    
    Example:
        value=1234, powerOfTenMultiplier=-4 → $0.1234
    """
    value: int = 0
    powerOfTenMultiplier: int = -4  # Default for sub-cent precision
    currency: CurrencyType = CurrencyType.USD
    
    def to_currency_units(self) -> float:
        """Convert to currency units (e.g., dollars)."""
        return self.value * (10 ** self.powerOfTenMultiplier)
    
    def to_cents(self) -> float:
        """Convert to cents (assumes USD-like currency)."""
        return self.to_currency_units() * 100
    
    @classmethod
    def from_cents(cls, cents: float, currency: CurrencyType = CurrencyType.USD) -> "PriceValue":
        """
        Create from cents value.
        
        Args:
            cents: Price in cents (e.g., 12.5 for $0.125)
            currency: Currency code
        """
        # Store with 4 decimal places precision
        return cls(
            value=int(cents * 100),
            powerOfTenMultiplier=-4,
            currency=currency
        )
    
    @classmethod
    def from_currency(cls, amount: float, currency: CurrencyType = CurrencyType.USD) -> "PriceValue":
        """
        Create from currency units (e.g., dollars).
        
        Args:
            amount: Price in currency units
            currency: Currency code
        """
        return cls.from_cents(amount * 100, currency)
    
    def format_price(self) -> str:
        """Format price as string with currency symbol."""
        symbols = {
            CurrencyType.USD: "$",
            CurrencyType.EUR: "€",
            CurrencyType.GBP: "£",
            CurrencyType.JPY: "¥",
            CurrencyType.CNY: "¥",
            CurrencyType.TWD: "NT$",
        }
        symbol = symbols.get(self.currency, "")
        return f"{symbol}{self.to_currency_units():.4f}"


# =============================================================================
# Consumption Tariff Interval
# =============================================================================

@dataclass_json
@dataclass
class ConsumptionTariffInterval:
    """
    Consumption-based tariff interval (tier/block).
    
    Reference: IEEE Std 2030.5-2023
    
    Defines pricing for a consumption tier/block.
    
    Attributes:
        href: URI of this resource
        consumptionBlock: Block/tier number
        price: Price per unit of consumption
        startValue: Start of consumption range (Wh)
        environmentalCost: Additional environmental cost per unit
    """
    href: Optional[str] = None
    consumptionBlock: ConsumptionBlockType = ConsumptionBlockType.BLOCK_1
    price: Optional[PriceValue] = None
    startValue: int = 0  # Wh threshold for this tier
    environmentalCost: Optional[PriceValue] = None
    
    def get_price_per_kwh(self) -> float:
        """Get price per kWh in currency units."""
        if self.price is None:
            return 0.0
        # Price is per Wh, convert to per kWh
        return self.price.to_currency_units() * 1000
    
    def is_in_tier(self, consumption_wh: int) -> bool:
        """Check if consumption falls in this tier (at or above start)."""
        return consumption_wh >= self.startValue


@dataclass_json
@dataclass
class ConsumptionTariffIntervalList:
    """List of ConsumptionTariffInterval resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    ConsumptionTariffInterval: List[ConsumptionTariffInterval] = field(default_factory=list)


# =============================================================================
# Time Tariff Interval
# =============================================================================

@dataclass_json
@dataclass
class TimeTariffInterval:
    """
    Time-based tariff interval.
    
    Reference: IEEE Std 2030.5-2023
    
    Defines pricing for a time period.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier
        interval: DateTimeInterval with start/duration
        touTier: Time of Use tier type
        price: Price per unit for this interval
        ConsumptionTariffIntervalListLink: Link to consumption tiers
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Time interval
    interval: Optional[dict] = None  # DateTimeInterval
    EventStatus: Optional[dict] = None
    
    # TOU tier
    touTier: TOUTierType = TOUTierType.NOT_APPLICABLE
    
    # Pricing
    price: Optional[PriceValue] = None
    
    # Link to consumption tiers (for hybrid pricing)
    ConsumptionTariffIntervalListLink: Optional[dict] = None
    
    def is_active(self, current_time: int) -> bool:
        """
        Check if this interval is active at current time.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            True if interval is active
        """
        if not self.interval:
            return False
        
        start = self.interval.get("start", 0)
        duration = self.interval.get("duration", 0)
        
        return start <= current_time < (start + duration)
    
    def get_price_per_kwh(self) -> float:
        """Get price per kWh in currency units."""
        if self.price is None:
            return 0.0
        return self.price.to_currency_units() * 1000
    
    def get_tier_name(self) -> str:
        """Get human-readable tier name."""
        return self.touTier.name.replace("_", " ").title()


@dataclass_json
@dataclass
class TimeTariffIntervalList:
    """List of TimeTariffInterval resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    TimeTariffInterval: List[TimeTariffInterval] = field(default_factory=list)
    
    def get_active_interval(self, current_time: int) -> Optional[TimeTariffInterval]:
        """Get the currently active interval."""
        for interval in self.TimeTariffInterval:
            if interval.is_active(current_time):
                return interval
        return None
    
    def get_intervals_by_tier(self, tier: TOUTierType) -> List[TimeTariffInterval]:
        """Get all intervals for a specific TOU tier."""
        return [i for i in self.TimeTariffInterval if i.touTier == tier]


# =============================================================================
# Rate Component
# =============================================================================

@dataclass_json
@dataclass
class RateComponent:
    """
    Rate Component resource.
    
    Reference: IEEE Std 2030.5-2023
    
    A component of a tariff with its own pricing structure.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier
        description: Human-readable description
        
        # Rate type
        flowRateEndLimit: Maximum flow rate for this component (W)
        flowRateStartLimit: Minimum flow rate for this component (W)
        
        # Role flags
        roleFlags: Bitmap indicating rate applicability
        
        # Links to intervals
        TimeTariffIntervalListLink: Link to time-based intervals
        ConsumptionTariffIntervalListLink: Link to consumption tiers
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Flow rate limits
    flowRateEndLimit: Optional[int] = None    # Max W
    flowRateStartLimit: Optional[int] = None  # Min W
    
    # Role flags
    roleFlags: Optional[int] = None
    
    # Links to intervals
    TimeTariffIntervalListLink: Optional[dict] = None
    ConsumptionTariffIntervalListLink: Optional[dict] = None
    ActiveTimeTariffIntervalListLink: Optional[dict] = None


@dataclass_json
@dataclass
class RateComponentList:
    """List of RateComponent resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    RateComponent: List[RateComponent] = field(default_factory=list)


# =============================================================================
# Tariff Profile
# =============================================================================

@dataclass_json
@dataclass
class TariffProfile:
    """
    Tariff Profile resource.
    
    Reference: IEEE Std 2030.5-2023 Section 10.12
    
    Container for rate information and pricing schedules.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier
        description: Human-readable description
        
        # Tariff identification
        primacy: Priority (lower = higher priority)
        currency: Currency code
        pricePowerOfTenMultiplier: Default price multiplier
        
        # Tariff type
        tariffType: Type of tariff (TOU, Tiered, etc.)
        
        # Links to components
        RateComponentListLink: Link to rate components
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Priority
    primacy: int = 255  # Lower = higher priority
    
    # Currency settings
    currency: CurrencyType = CurrencyType.USD
    pricePowerOfTenMultiplier: int = -4  # Sub-cent precision
    
    # Tariff type
    tariffType: TariffType = TariffType.TIME_OF_USE
    
    # Rate calculation
    rateCode: Optional[str] = None  # Utility rate code
    serviceCategoryKind: Optional[int] = None
    
    # Links
    RateComponentListLink: Optional[dict] = None
    
    def get_priority(self) -> int:
        """Get tariff priority (0 = highest)."""
        return self.primacy
    
    def is_higher_priority_than(self, other: "TariffProfile") -> bool:
        """Check if this tariff has higher priority."""
        return self.primacy < other.primacy
    
    def get_tariff_type_name(self) -> str:
        """Get human-readable tariff type."""
        return self.tariffType.name.replace("_", " ").title()


@dataclass_json
@dataclass
class TariffProfileList:
    """List of TariffProfile resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    TariffProfile: List[TariffProfile] = field(default_factory=list)
    
    def get_by_priority(self) -> List[TariffProfile]:
        """Get tariffs sorted by priority (highest first)."""
        return sorted(self.TariffProfile, key=lambda t: t.primacy)
    
    def get_highest_priority(self) -> Optional[TariffProfile]:
        """Get the highest priority tariff."""
        by_priority = self.get_by_priority()
        return by_priority[0] if by_priority else None


# =============================================================================
# Price Summary
# =============================================================================

@dataclass_json
@dataclass
class PriceSummary:
    """
    Summary of current pricing information.
    
    Useful for displaying current rate to users.
    """
    current_price_per_kwh: float = 0.0
    current_tier: TOUTierType = TOUTierType.NOT_APPLICABLE
    currency: CurrencyType = CurrencyType.USD
    tariff_name: str = ""
    next_tier: Optional[TOUTierType] = None
    next_tier_starts: Optional[int] = None  # POSIX seconds
    next_price_per_kwh: Optional[float] = None
    
    def format_current_price(self) -> str:
        """Format current price as string."""
        symbols = {
            CurrencyType.USD: "$",
            CurrencyType.EUR: "€",
            CurrencyType.TWD: "NT$",
        }
        symbol = symbols.get(self.currency, "")
        return f"{symbol}{self.current_price_per_kwh:.4f}/kWh"


# =============================================================================
# Helper Functions
# =============================================================================

def create_tou_tariff(
    mRID: str,
    description: str,
    currency: CurrencyType = CurrencyType.USD,
    primacy: int = 1,
) -> TariffProfile:
    """
    Create a Time of Use tariff profile.
    
    Args:
        mRID: Unique identifier
        description: Human-readable description
        currency: Currency code
        primacy: Priority level
        
    Returns:
        Configured TariffProfile
    """
    return TariffProfile(
        mRID=mRID,
        description=description,
        currency=currency,
        primacy=primacy,
        tariffType=TariffType.TIME_OF_USE,
    )


def create_time_interval(
    mRID: str,
    start_time: int,
    duration: int,
    tier: TOUTierType,
    price_per_kwh: float,
    currency: CurrencyType = CurrencyType.USD,
) -> TimeTariffInterval:
    """
    Create a time tariff interval.
    
    Args:
        mRID: Unique identifier
        start_time: Start time (POSIX seconds)
        duration: Duration in seconds
        tier: TOU tier type
        price_per_kwh: Price per kWh in currency units
        currency: Currency code
        
    Returns:
        Configured TimeTariffInterval
    """
    # Convert $/kWh to $/Wh
    price_per_wh = price_per_kwh / 1000
    
    return TimeTariffInterval(
        mRID=mRID,
        interval={
            "start": start_time,
            "duration": duration,
        },
        touTier=tier,
        price=PriceValue.from_currency(price_per_wh, currency),
    )


def create_consumption_tier(
    block: ConsumptionBlockType,
    start_kwh: float,
    price_per_kwh: float,
    currency: CurrencyType = CurrencyType.USD,
) -> ConsumptionTariffInterval:
    """
    Create a consumption tier.
    
    Args:
        block: Block/tier number
        start_kwh: Start of tier in kWh
        price_per_kwh: Price per kWh
        currency: Currency code
        
    Returns:
        Configured ConsumptionTariffInterval
    """
    price_per_wh = price_per_kwh / 1000
    
    return ConsumptionTariffInterval(
        consumptionBlock=block,
        startValue=int(start_kwh * 1000),  # Convert to Wh
        price=PriceValue.from_currency(price_per_wh, currency),
    )


def calculate_cost(
    energy_wh: int,
    price_per_kwh: float,
    currency: CurrencyType = CurrencyType.USD,
) -> PriceValue:
    """
    Calculate cost for energy consumption.
    
    Args:
        energy_wh: Energy in Watt-hours
        price_per_kwh: Price per kWh
        currency: Currency code
        
    Returns:
        Total cost as PriceValue
    """
    energy_kwh = energy_wh / 1000
    total = energy_kwh * price_per_kwh
    return PriceValue.from_currency(total, currency)


def get_current_price_summary(
    tariff: TariffProfile,
    intervals: List[TimeTariffInterval],
    current_time: int,
) -> PriceSummary:
    """
    Get current pricing summary.
    
    Args:
        tariff: Active tariff profile
        intervals: List of time tariff intervals
        current_time: Current time as POSIX seconds
        
    Returns:
        PriceSummary with current pricing info
    """
    # Find current interval
    current_interval = None
    for interval in intervals:
        if interval.is_active(current_time):
            current_interval = interval
            break
    
    # Find next interval
    future_intervals = []
    for interval in intervals:
        if interval.interval:
            start = interval.interval.get("start", 0)
            if start > current_time:
                future_intervals.append(interval)
    
    future_intervals.sort(key=lambda i: i.interval.get("start", 0) if i.interval else 0)
    next_interval = future_intervals[0] if future_intervals else None
    
    summary = PriceSummary(
        tariff_name=tariff.description or tariff.mRID or "Unknown",
        currency=tariff.currency,
    )
    
    if current_interval:
        summary.current_price_per_kwh = current_interval.get_price_per_kwh()
        summary.current_tier = current_interval.touTier
    
    if next_interval:
        summary.next_tier = next_interval.touTier
        summary.next_price_per_kwh = next_interval.get_price_per_kwh()
        if next_interval.interval:
            summary.next_tier_starts = next_interval.interval.get("start")
    
    return summary
