"""
IEEE 2030.5-2023 Messaging Function Set.

This module provides the complete Messaging implementation including:
- TextMessage: Individual text messages
- MessagingProgram: Container for text messages
- Priority levels and confirmation requirements

Reference: IEEE Std 2030.5-2023
- Section 10.6: Messaging Function Set
- Table 26: Priority enumeration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List
from dataclasses_json import dataclass_json


# =============================================================================
# Priority Level (Table 26)
# =============================================================================

class PriorityType(IntEnum):
    """
    Message Priority enumeration.
    
    Reference: IEEE Std 2030.5-2023 Table 26
    
    Defines the priority level for text messages.
    Lower values indicate higher priority.
    """
    # 0: Low priority - informational messages
    LOW = 0
    
    # 1: Normal priority - standard messages
    NORMAL = 1
    
    # 2: High priority - important messages
    HIGH = 2
    
    # 3: Critical priority - urgent/emergency messages
    CRITICAL = 3


# =============================================================================
# Message Status
# =============================================================================

class MessageStatus(IntEnum):
    """
    Message status for tracking delivery and read state.
    """
    # 0: Message not yet delivered
    PENDING = 0
    
    # 1: Message delivered to device
    DELIVERED = 1
    
    # 2: Message read/acknowledged by user
    READ = 2
    
    # 3: Message expired
    EXPIRED = 3
    
    # 4: Message cancelled
    CANCELLED = 4


# =============================================================================
# Text Message
# =============================================================================

@dataclass_json
@dataclass
class TextMessage:
    """
    Text Message resource.
    
    Reference: IEEE Std 2030.5-2023 Section 10.6
    
    Represents a text message that can be sent to an end device
    for display to users. Messages can require confirmation.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier (UInt128 as hex)
        description: Human-readable description
        version: Version number for tracking updates
        
        # Message content
        textMessage: The actual message text (max 2048 characters)
        
        # Timing
        creationTime: When the message was created (POSIX seconds)
        interval: DateTimeInterval with start/duration for display
        
        # Priority and confirmation
        priority: Message priority level (0-3)
        responseRequired: Whether user confirmation is required
        
        # Status tracking
        EventStatus: Current status of the message
        
        # Reply URI for confirmation
        replyTo: URI for sending confirmation
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Message content (max 2048 chars)
    textMessage: str = ""
    
    # Timing
    creationTime: Optional[int] = None
    interval: Optional[dict] = None  # DateTimeInterval
    
    # Priority (0=Low, 1=Normal, 2=High, 3=Critical)
    priority: PriorityType = PriorityType.NORMAL
    
    # Confirmation requirement (HexBinary8 bitmap)
    # Bit 0: End device should confirm receipt
    # Bit 1: End device should confirm user acknowledgement
    responseRequired: Optional[int] = None
    
    # Event status
    EventStatus: Optional[dict] = None
    
    # Reply-To URI for confirmation
    replyTo: Optional[str] = None
    
    # Language/locale (optional)
    locale: Optional[str] = None
    
    def is_active(self, current_time: int) -> bool:
        """
        Check if the message should be displayed at current time.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            True if message is currently active
        """
        if not self.interval:
            # No interval means always active until expiry
            return True
        
        start = self.interval.get("start", 0)
        duration = self.interval.get("duration", 0)
        
        if duration == 0:
            # Duration 0 means indefinite
            return current_time >= start
        
        return start <= current_time < (start + duration)
    
    def is_expired(self, current_time: int) -> bool:
        """
        Check if the message has expired.
        
        Args:
            current_time: Current time as POSIX seconds
            
        Returns:
            True if message has expired
        """
        if not self.interval:
            return False
        
        start = self.interval.get("start", 0)
        duration = self.interval.get("duration", 0)
        
        if duration == 0:
            return False  # Never expires
        
        return current_time >= (start + duration)
    
    def requires_confirmation(self) -> bool:
        """Check if this message requires user confirmation."""
        if self.responseRequired is None:
            return False
        return (self.responseRequired & 0x02) != 0  # Bit 1
    
    def requires_receipt(self) -> bool:
        """Check if this message requires receipt confirmation."""
        if self.responseRequired is None:
            return False
        return (self.responseRequired & 0x01) != 0  # Bit 0
    
    def get_priority_name(self) -> str:
        """Get human-readable priority name."""
        return self.priority.name
    
    def truncate_message(self, max_length: int = 100) -> str:
        """Get truncated message for preview."""
        if len(self.textMessage) <= max_length:
            return self.textMessage
        return self.textMessage[:max_length-3] + "..."


@dataclass_json
@dataclass
class TextMessageList:
    """List of TextMessage resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    TextMessage: List[TextMessage] = field(default_factory=list)
    
    def get_active_messages(self, current_time: int) -> List[TextMessage]:
        """Get all currently active messages."""
        return [m for m in self.TextMessage if m.is_active(current_time)]
    
    def get_by_priority(self, priority: PriorityType) -> List[TextMessage]:
        """Get messages with specific priority."""
        return [m for m in self.TextMessage if m.priority == priority]
    
    def get_critical_messages(self) -> List[TextMessage]:
        """Get all critical priority messages."""
        return self.get_by_priority(PriorityType.CRITICAL)
    
    def sort_by_priority(self) -> None:
        """Sort messages by priority (critical first)."""
        self.TextMessage.sort(key=lambda m: -m.priority)


# =============================================================================
# Active Text Message List
# =============================================================================

@dataclass_json
@dataclass
class ActiveTextMessageList:
    """
    List of active TextMessage resources.
    
    Contains only messages that are currently active (within their
    display interval).
    """
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    TextMessage: List[TextMessage] = field(default_factory=list)


# =============================================================================
# Messaging Program
# =============================================================================

@dataclass_json
@dataclass
class MessagingProgram:
    """
    Messaging Program container.
    
    Reference: IEEE Std 2030.5-2023 Section 10.6
    
    A MessagingProgram contains text messages and manages
    message delivery to enrolled devices.
    
    Attributes:
        href: URI of this resource
        mRID: Globally unique identifier (UInt128 as hex)
        description: Human-readable description
        version: Version number for tracking updates
        
        primacy: Priority relative to other programs (lower = higher)
        locale: Default language/locale for messages
        
        # Links to related resources
        ActiveTextMessageListLink: URI to active messages
        TextMessageListLink: URI to all messages
    """
    # Resource identification
    href: Optional[str] = None
    mRID: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    subscribable: Optional[int] = None
    
    # Priority (lower = higher priority, 0-255)
    primacy: int = 255
    
    # Default locale for messages
    locale: Optional[str] = None
    
    # Links to message lists
    ActiveTextMessageListLink: Optional[dict] = None
    TextMessageListLink: Optional[dict] = None
    
    def get_priority(self) -> int:
        """Get program priority (0 = highest)."""
        return self.primacy
    
    def is_higher_priority_than(self, other: "MessagingProgram") -> bool:
        """Check if this program has higher priority than another."""
        return self.primacy < other.primacy


@dataclass_json
@dataclass
class MessagingProgramList:
    """List of MessagingProgram resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    subscribable: Optional[int] = None
    pollRate: Optional[int] = None
    MessagingProgram: List[MessagingProgram] = field(default_factory=list)


# =============================================================================
# Message Response
# =============================================================================

class MessageResponseStatus(IntEnum):
    """
    Message response status codes.
    
    Used when responding to messages that require confirmation.
    """
    # 0: Message received
    RECEIVED = 0
    
    # 1: Message read/displayed
    READ = 1
    
    # 2: Message acknowledged by user
    ACKNOWLEDGED = 2
    
    # 3: User dismissed message
    DISMISSED = 3
    
    # 4: Message expired before acknowledgement
    EXPIRED = 4


@dataclass_json
@dataclass
class TextMessageResponse:
    """
    Response to a TextMessage.
    
    Sent by the client to confirm receipt, reading, or acknowledgement.
    """
    href: Optional[str] = None
    createdDateTime: Optional[int] = None
    endDeviceLFDI: Optional[str] = None
    status: MessageResponseStatus = MessageResponseStatus.RECEIVED
    subject: Optional[str] = None  # URI of the message being responded to


@dataclass_json
@dataclass
class TextMessageResponseList:
    """List of TextMessageResponse resources."""
    href: Optional[str] = None
    all_: int = 0
    results: int = 0
    TextMessageResponse: List[TextMessageResponse] = field(default_factory=list)


# =============================================================================
# Helper Functions
# =============================================================================

def create_text_message(
    mRID: str,
    message: str,
    priority: PriorityType = PriorityType.NORMAL,
    start_time: Optional[int] = None,
    duration: Optional[int] = None,
    require_confirmation: bool = False,
    require_receipt: bool = False,
    locale: Optional[str] = None,
    description: Optional[str] = None
) -> TextMessage:
    """
    Create a TextMessage with common parameters.
    
    Args:
        mRID: Unique identifier for the message
        message: Message text (max 2048 characters)
        priority: Message priority level
        start_time: Display start time (POSIX seconds), None = immediate
        duration: Display duration (seconds), None/0 = indefinite
        require_confirmation: Require user acknowledgement
        require_receipt: Require receipt confirmation
        locale: Language/locale code (e.g., "en-US")
        description: Optional description
        
    Returns:
        Configured TextMessage
    """
    response_required = 0
    if require_receipt:
        response_required |= 0x01
    if require_confirmation:
        response_required |= 0x02
    
    interval = None
    if start_time is not None:
        interval = {
            "start": start_time,
            "duration": duration or 0,
        }
    
    return TextMessage(
        mRID=mRID,
        textMessage=message[:2048],  # Truncate to max length
        priority=priority,
        interval=interval,
        responseRequired=response_required if response_required else None,
        locale=locale,
        description=description or f"Message: {message[:50]}...",
    )


def create_alert_message(
    mRID: str,
    message: str,
    start_time: Optional[int] = None,
    duration: int = 3600,  # 1 hour default
) -> TextMessage:
    """
    Create a critical alert message requiring acknowledgement.
    
    Args:
        mRID: Unique identifier for the message
        message: Alert message text
        start_time: Display start time (POSIX seconds)
        duration: Display duration (seconds)
        
    Returns:
        Configured critical priority TextMessage
    """
    return create_text_message(
        mRID=mRID,
        message=message,
        priority=PriorityType.CRITICAL,
        start_time=start_time,
        duration=duration,
        require_confirmation=True,
        require_receipt=True,
        description=f"ALERT: {message[:40]}",
    )


def create_info_message(
    mRID: str,
    message: str,
    start_time: Optional[int] = None,
    duration: int = 86400,  # 24 hours default
) -> TextMessage:
    """
    Create a low priority informational message.
    
    Args:
        mRID: Unique identifier for the message
        message: Informational message text
        start_time: Display start time (POSIX seconds)
        duration: Display duration (seconds)
        
    Returns:
        Configured low priority TextMessage
    """
    return create_text_message(
        mRID=mRID,
        message=message,
        priority=PriorityType.LOW,
        start_time=start_time,
        duration=duration,
        require_confirmation=False,
        require_receipt=False,
        description=f"Info: {message[:40]}",
    )


def create_maintenance_message(
    mRID: str,
    message: str,
    start_time: int,
    duration: int,
) -> TextMessage:
    """
    Create a scheduled maintenance notification.
    
    Args:
        mRID: Unique identifier for the message
        message: Maintenance notification text
        start_time: When to start displaying (POSIX seconds)
        duration: How long to display (seconds)
        
    Returns:
        Configured high priority TextMessage
    """
    return create_text_message(
        mRID=mRID,
        message=message,
        priority=PriorityType.HIGH,
        start_time=start_time,
        duration=duration,
        require_confirmation=False,
        require_receipt=True,
        description=f"Maintenance: {message[:40]}",
    )


def filter_messages_by_locale(
    messages: List[TextMessage],
    locale: str,
    fallback_to_all: bool = True
) -> List[TextMessage]:
    """
    Filter messages by locale.
    
    Args:
        messages: List of messages to filter
        locale: Target locale (e.g., "en-US", "zh-TW")
        fallback_to_all: If True, include messages without locale
        
    Returns:
        Filtered list of messages
    """
    result = []
    for msg in messages:
        if msg.locale == locale:
            result.append(msg)
        elif fallback_to_all and msg.locale is None:
            result.append(msg)
    return result
