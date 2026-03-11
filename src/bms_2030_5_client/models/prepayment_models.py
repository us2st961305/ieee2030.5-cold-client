"""
IEEE 2030.5-2023 Prepayment Function Set.

This module provides the complete Prepayment implementation including:
- PrepayAccount: Prepayment account information
- PrepayOperationStatus: Current account status
- AccountBalance: Balance tracking
- CreditRegister: Credit transactions
- SupplyInterruptionOverride: Override functionality

Reference: IEEE Std 2030.5-2023
- Section 10.13: Prepayment Function Set
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List
from dataclasses_json import dataclass_json

from bms_2030_5_client.models.pricing_models import CurrencyType, PriceValue


# =============================================================================
# Account Status Type
# =============================================================================

class AccountStatusType(IntEnum):
    """
    Prepayment Account Status enumeration.
    """
    # 0: Account is normal/active
    NORMAL = 0
    
    # 1: Low balance warning
    LOW_BALANCE = 1
    
    # 2: Very low balance (critical warning)
    VERY_LOW_BALANCE = 2
    
    # 3: Zero balance (service may be interrupted)
    ZERO_BALANCE = 3
    
    # 4: Negative balance (debt)
    NEGATIVE_BALANCE = 4
    
    # 5: Service disconnected due to non-payment
    DISCONNECTED = 5
    
    # 6: Account suspended
    SUSPENDED = 6
    
    # 7: Account closed
    CLOSED = 7


# =============================================================================
# Credit Type
# =============================================================================

class CreditTypeType(IntEnum):
    """
    Credit Type enumeration.
    
    Indicates the type of credit transaction.
    """
    # 0: Regular credit (payment)
    REGULAR = 0
    
    # 1: Emergency credit
    EMERGENCY = 1
    
    # 2: Utility grant/assistance
    GRANT = 2
    
    # 3: Promotional credit
    PROMOTIONAL = 3
    
    # 4: Compensation/adjustment
    ADJUSTMENT = 4
    
    # 5: Refund
    REFUND = 5


# =============================================================================
# Service Status Type
# =============================================================================

class ServiceStatusType(IntEnum):
    """
    Service Status enumeration.
    
    Indicates the current service delivery status.
    """
    # 0: Service connected and active
    CONNECTED = 0
    
    # 1: Service disconnected
    DISCONNECTED = 1
    
    # 2: Armed for disconnection (pending disconnect)
    ARMED = 2
    
    # 3: Load limited (reduced service)
    LOAD_LIMITED = 3


# =============================================================================
# Account Balance
# =============================================================================

@dataclass_json
@dataclass
class AccountBalance:
    """
    Account Balance information.
    
    Reference: IEEE Std 2030.5-2023
    
    Represents the current balance of a prepayment account.
    
    Attributes:
        href: URI of this resource
        availableCredit: Current available credit
        creditStatus: Credit status indicator
        emergencyCreditUsed: Emergency credit used
        emergencyCreditRemaining: Emergency credit remaining
        emergencyCreditEnabled: Whether emergency credit is enabled
    """
    href: Optional[str] = None
    
    # Available credit (can be negative for debt)
    availableCredit: Optional[PriceValue] = None
    
    # Credit status
    creditStatus: AccountStatusType = AccountStatusType.NORMAL
    
    # Emergency credit
    emergencyCreditUsed: Optional[PriceValue] = None
    emergencyCreditRemaining: Optional[PriceValue] = None
    emergencyCreditEnabled: bool = False
    
    def get_available_credit(self) -> float:
        """Get available credit in currency units."""
        if self.availableCredit is None:
            return 0.0
        return self.availableCredit.to_currency_units()
    
    def get_emergency_credit_remaining(self) -> float:
        """Get remaining emergency credit."""
        if self.emergencyCreditRemaining is None:
            return 0.0
        return self.emergencyCreditRemaining.to_currency_units()
    
    def is_low_balance(self) -> bool:
        """Check if balance is low or critical."""
        return self.creditStatus in (
            AccountStatusType.LOW_BALANCE,
            AccountStatusType.VERY_LOW_BALANCE,
            AccountStatusType.ZERO_BALANCE,
            AccountStatusType.NEGATIVE_BALANCE,
        )
    
    def is_disconnected(self) -> bool:
        """Check if service is disconnected due to balance."""
        return self.creditStatus == AccountStatusType.DISCONNECTED


@dataclass_json
@dataclass
class AccountBalanceList:
    """List of AccountBalance resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    AccountBalance: List[AccountBalance] = field(default_factory=list)


# =============================================================================
# Credit Register
# =============================================================================

@dataclass_json
@dataclass
class CreditRegister:
    """
    Credit Register (transaction record).
    
    Reference: IEEE Std 2030.5-2023
    
    Records a credit transaction on a prepayment account.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier
        creditType: Type of credit transaction
        creditAmount: Amount of credit
        effectiveTime: When the credit was applied
        token: Payment token/reference (if applicable)
        description: Human-readable description
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    
    # Credit details
    creditType: CreditTypeType = CreditTypeType.REGULAR
    creditAmount: Optional[PriceValue] = None
    
    # Timing
    effectiveTime: Optional[int] = None  # POSIX seconds
    
    # Payment reference
    token: Optional[str] = None
    
    def get_credit_amount(self) -> float:
        """Get credit amount in currency units."""
        if self.creditAmount is None:
            return 0.0
        return self.creditAmount.to_currency_units()
    
    def get_credit_type_name(self) -> str:
        """Get human-readable credit type."""
        return self.creditType.name.replace("_", " ").title()


@dataclass_json
@dataclass
class CreditRegisterList:
    """List of CreditRegister resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    CreditRegister: List[CreditRegister] = field(default_factory=list)


# =============================================================================
# Prepayment Operation Status
# =============================================================================

@dataclass_json
@dataclass
class PrepayOperationStatus:
    """
    Prepayment Operation Status.
    
    Reference: IEEE Std 2030.5-2023
    
    Current operational status of prepayment service.
    
    Attributes:
        href: URI of this resource
        creditTypeInUse: Type of credit currently being used
        serviceStatus: Current service delivery status
        creditExpiryLevel: Balance level at which credit expires
        usageBalance: Usage balance information
    """
    href: Optional[str] = None
    
    # Credit in use
    creditTypeInUse: CreditTypeType = CreditTypeType.REGULAR
    creditTypeChange: Optional[int] = None  # Time of last change
    
    # Service status
    serviceStatus: ServiceStatusType = ServiceStatusType.CONNECTED
    
    # Credit expiry
    creditExpiryLevel: Optional[PriceValue] = None
    creditExpiryTime: Optional[int] = None
    
    # Usage tracking
    usageBalance: Optional[PriceValue] = None
    usageSinceLastBilling: Optional[PriceValue] = None
    
    def is_service_active(self) -> bool:
        """Check if service is currently active."""
        return self.serviceStatus == ServiceStatusType.CONNECTED
    
    def is_using_emergency_credit(self) -> bool:
        """Check if using emergency credit."""
        return self.creditTypeInUse == CreditTypeType.EMERGENCY


@dataclass_json
@dataclass
class PrepayOperationStatusList:
    """List of PrepayOperationStatus resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    PrepayOperationStatus: List[PrepayOperationStatus] = field(default_factory=list)


# =============================================================================
# Supply Interruption Override
# =============================================================================

@dataclass_json
@dataclass
class SupplyInterruptionOverride:
    """
    Supply Interruption Override.
    
    Reference: IEEE Std 2030.5-2023
    
    Allows temporary override of supply interruption.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier
        description: Human-readable description
        interval: DateTimeInterval for override period
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    
    # Override timing
    interval: Optional[dict] = None  # DateTimeInterval
    
    def is_active(self, current_time: int) -> bool:
        """
        Check if override is currently active.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            True if override is active
        """
        if not self.interval:
            return False
        
        start = self.interval.get("start", 0)
        duration = self.interval.get("duration", 0)
        
        return start <= current_time < (start + duration)


@dataclass_json
@dataclass
class SupplyInterruptionOverrideList:
    """List of SupplyInterruptionOverride resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    SupplyInterruptionOverride: List[SupplyInterruptionOverride] = field(default_factory=list)


# =============================================================================
# Prepayment Account
# =============================================================================

@dataclass_json
@dataclass
class PrepayAccount:
    """
    Prepayment Account.
    
    Reference: IEEE Std 2030.5-2023 Section 10.13
    
    Container for prepayment account information.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier
        description: Human-readable description
        
        # Account settings
        lowCreditWarningLevel: Balance for low credit warning
        lowEmergencyCreditWarningLevel: Emergency credit warning level
        creditExpiryWarningTime: Warning time before credit expires
        
        # Consumption tracking
        presetMaximumConsumption: Maximum consumption limit
        
        # Links
        AccountBalanceLink: Link to balance information
        PrepayOperationStatusLink: Link to operation status
        CreditRegisterListLink: Link to credit transactions
        SupplyInterruptionOverrideListLink: Link to overrides
    """
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Warning levels
    lowCreditWarningLevel: Optional[PriceValue] = None
    lowEmergencyCreditWarningLevel: Optional[PriceValue] = None
    creditExpiryWarningTime: Optional[int] = None  # seconds before expiry
    
    # Consumption limits
    presetMaximumConsumption: Optional[int] = None  # Wh
    
    # Currency
    currency: CurrencyType = CurrencyType.USD
    
    # Links
    AccountBalanceLink: Optional[dict] = None
    PrepayOperationStatusLink: Optional[dict] = None
    CreditRegisterListLink: Optional[dict] = None
    ActiveCreditRegisterListLink: Optional[dict] = None
    SupplyInterruptionOverrideListLink: Optional[dict] = None
    ActiveSupplyInterruptionOverrideListLink: Optional[dict] = None
    
    def get_low_credit_warning(self) -> float:
        """Get low credit warning level in currency units."""
        if self.lowCreditWarningLevel is None:
            return 0.0
        return self.lowCreditWarningLevel.to_currency_units()


@dataclass_json
@dataclass
class PrepayAccountList:
    """List of PrepayAccount resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    PrepayAccount: List[PrepayAccount] = field(default_factory=list)


# =============================================================================
# Prepayment Summary
# =============================================================================

@dataclass_json
@dataclass
class PrepaymentSummary:
    """
    Summary of prepayment account for display.
    
    Consolidates key prepayment information for UI.
    """
    account_id: str = ""
    available_credit: float = 0.0
    emergency_credit_remaining: float = 0.0
    using_emergency_credit: bool = False
    account_status: AccountStatusType = AccountStatusType.NORMAL
    service_status: ServiceStatusType = ServiceStatusType.CONNECTED
    low_balance_warning: bool = False
    currency: CurrencyType = CurrencyType.USD
    
    def format_balance(self) -> str:
        """Format balance as string with currency symbol."""
        symbols = {
            CurrencyType.USD: "$",
            CurrencyType.EUR: "€",
            CurrencyType.TWD: "NT$",
        }
        symbol = symbols.get(self.currency, "")
        return f"{symbol}{self.available_credit:.2f}"
    
    def get_status_message(self) -> str:
        """Get human-readable status message."""
        if self.service_status == ServiceStatusType.DISCONNECTED:
            return "Service Disconnected"
        if self.using_emergency_credit:
            return "Using Emergency Credit"
        if self.account_status == AccountStatusType.VERY_LOW_BALANCE:
            return "Critical Low Balance"
        if self.account_status == AccountStatusType.LOW_BALANCE:
            return "Low Balance Warning"
        return "Normal"


# =============================================================================
# Helper Functions
# =============================================================================

def create_prepay_account(
    mRID: str,
    description: str = "Prepayment Account",
    low_credit_warning: float = 10.0,
    currency: CurrencyType = CurrencyType.USD,
) -> PrepayAccount:
    """
    Create a prepayment account.
    
    Args:
        mRID: Unique identifier
        description: Account description
        low_credit_warning: Low credit warning level
        currency: Currency code
        
    Returns:
        Configured PrepayAccount
    """
    return PrepayAccount(
        mRID=mRID,
        description=description,
        currency=currency,
        lowCreditWarningLevel=PriceValue.from_currency(low_credit_warning, currency),
    )


def create_credit_register(
    mRID: str,
    amount: float,
    credit_type: CreditTypeType = CreditTypeType.REGULAR,
    effective_time: Optional[int] = None,
    currency: CurrencyType = CurrencyType.USD,
    token: Optional[str] = None,
    description: Optional[str] = None,
) -> CreditRegister:
    """
    Create a credit register (transaction).
    
    Args:
        mRID: Unique identifier
        amount: Credit amount in currency units
        credit_type: Type of credit
        effective_time: When credit takes effect (POSIX seconds)
        currency: Currency code
        token: Payment token/reference
        description: Transaction description
        
    Returns:
        Configured CreditRegister
    """
    return CreditRegister(
        mRID=mRID,
        creditType=credit_type,
        creditAmount=PriceValue.from_currency(amount, currency),
        effectiveTime=effective_time,
        token=token,
        description=description or f"Credit: {amount:.2f}",
    )


def create_supply_override(
    mRID: str,
    start_time: int,
    duration: int,
    description: str = "Supply Interruption Override",
) -> SupplyInterruptionOverride:
    """
    Create a supply interruption override.
    
    Args:
        mRID: Unique identifier
        start_time: Override start time (POSIX seconds)
        duration: Override duration in seconds
        description: Override description
        
    Returns:
        Configured SupplyInterruptionOverride
    """
    return SupplyInterruptionOverride(
        mRID=mRID,
        description=description,
        interval={
            "start": start_time,
            "duration": duration,
        },
    )


def get_prepayment_summary(
    account: PrepayAccount,
    balance: AccountBalance,
    status: PrepayOperationStatus,
) -> PrepaymentSummary:
    """
    Get prepayment summary from account components.
    
    Args:
        account: PrepayAccount resource
        balance: AccountBalance resource
        status: PrepayOperationStatus resource
        
    Returns:
        PrepaymentSummary for display
    """
    return PrepaymentSummary(
        account_id=account.mRID or "",
        available_credit=balance.get_available_credit(),
        emergency_credit_remaining=balance.get_emergency_credit_remaining(),
        using_emergency_credit=status.is_using_emergency_credit(),
        account_status=balance.creditStatus,
        service_status=status.serviceStatus,
        low_balance_warning=balance.is_low_balance(),
        currency=account.currency,
    )


def estimate_remaining_usage(
    balance: float,
    rate_per_kwh: float,
    daily_usage_kwh: float,
) -> dict:
    """
    Estimate remaining usage based on current balance.
    
    Args:
        balance: Current balance in currency units
        rate_per_kwh: Current rate per kWh
        daily_usage_kwh: Average daily usage in kWh
        
    Returns:
        Dictionary with estimates:
        - remaining_kwh: Energy remaining
        - remaining_days: Days of usage remaining
        - remaining_hours: Hours of usage remaining
    """
    if rate_per_kwh <= 0:
        return {"remaining_kwh": 0, "remaining_days": 0, "remaining_hours": 0}
    
    remaining_kwh = balance / rate_per_kwh
    
    if daily_usage_kwh <= 0:
        remaining_days = 0
        remaining_hours = 0
    else:
        remaining_days = remaining_kwh / daily_usage_kwh
        remaining_hours = remaining_days * 24
    
    return {
        "remaining_kwh": remaining_kwh,
        "remaining_days": remaining_days,
        "remaining_hours": remaining_hours,
    }
