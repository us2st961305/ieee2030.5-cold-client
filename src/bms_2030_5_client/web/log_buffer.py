"""
In-memory ring buffer for log storage.

Provides thread-safe log storage with configurable max size.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, List, Optional


@dataclass
class LogEntry:
    """A single log entry."""
    timestamp: datetime
    level: str
    logger_name: str
    message: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "logger": self.logger_name,
            "message": self.message,
        }


class LogBuffer:
    """
    Thread-safe in-memory ring buffer for logs.
    
    Stores the most recent N log entries, discarding older ones
    when the buffer is full.
    """
    
    def __init__(self, max_size: int = 500):
        """
        Initialize log buffer.
        
        Args:
            max_size: Maximum number of log entries to store
        """
        self._buffer: Deque[LogEntry] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._max_size = max_size
    
    def add(
        self,
        message: str,
        level: str = "INFO",
        logger_name: str = "app",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Add a log entry to the buffer.
        
        Args:
            message: Log message
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            logger_name: Name of the logger
            timestamp: Entry timestamp (defaults to now)
        """
        entry = LogEntry(
            timestamp=timestamp or datetime.now(timezone.utc),
            level=level.upper(),
            logger_name=logger_name,
            message=message,
        )
        
        with self._lock:
            self._buffer.append(entry)
    
    def get_all(self) -> List[LogEntry]:
        """Get all log entries (oldest first)."""
        with self._lock:
            return list(self._buffer)
    
    def get_recent(self, n: int = 100) -> List[LogEntry]:
        """
        Get the most recent N log entries.
        
        Args:
            n: Number of entries to return
            
        Returns:
            List of log entries (newest first)
        """
        with self._lock:
            entries = list(self._buffer)
        
        # Return newest first, limited to n entries
        return list(reversed(entries[-n:]))
    
    def clear(self) -> None:
        """Clear all log entries."""
        with self._lock:
            self._buffer.clear()
    
    def __len__(self) -> int:
        """Return number of entries in buffer."""
        with self._lock:
            return len(self._buffer)


class LogBufferHandler(logging.Handler):
    """
    Logging handler that writes to a LogBuffer.
    
    Attach this handler to capture logs into the ring buffer.
    """
    
    def __init__(self, buffer: LogBuffer):
        """
        Initialize handler.
        
        Args:
            buffer: LogBuffer instance to write to
        """
        super().__init__()
        self.buffer = buffer
    
    def emit(self, record: logging.LogRecord) -> None:
        """Write a log record to the buffer."""
        try:
            message = self.format(record)
            self.buffer.add(
                message=message,
                level=record.levelname,
                logger_name=record.name,
                timestamp=datetime.fromtimestamp(record.created),
            )
        except Exception:
            # Don't let logging errors crash the app
            self.handleError(record)


# Global log buffer instance
log_buffer = LogBuffer(max_size=500)


def setup_log_capture(level: int = logging.INFO) -> LogBufferHandler:
    """
    Set up log capture to the global buffer.
    
    Call this during app initialization to capture all logs.
    
    Args:
        level: Minimum log level to capture
        
    Returns:
        The created handler (can be used to remove later)
    """
    handler = LogBufferHandler(log_buffer)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    
    # Add to root logger to capture all logs
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    return handler
