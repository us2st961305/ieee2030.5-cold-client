"""
Subscription management module for IEEE 2030.5.

Provides subscription lifecycle management:
- Create/Delete subscriptions
- Automatic renewal
- Enable/Disable control
- Reconnection handling
"""

from bms_2030_5_client.subs.manager import (
    SubscriptionManager,
    TrackedSubscription,
    SubscriptionState,
    SubscriptionXMLBuilder,
    create_subscription_manager,
    ENCODING_XML,
    ENCODING_EXI,
    MIN_RENEWAL_INTERVAL_HOURS,
    DEFAULT_RENEWAL_INTERVAL_HOURS,
)

__all__ = [
    "SubscriptionManager",
    "TrackedSubscription",
    "SubscriptionState",
    "SubscriptionXMLBuilder",
    "create_subscription_manager",
    "ENCODING_XML",
    "ENCODING_EXI",
    "MIN_RENEWAL_INTERVAL_HOURS",
    "DEFAULT_RENEWAL_INTERVAL_HOURS",
]
