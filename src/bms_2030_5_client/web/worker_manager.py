"""
Worker manager for controlling the BMS client worker process.

Handles Start/Stop/Reload operations for the polling and subscription workers.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any

from bms_2030_5_client.config import Config
from bms_2030_5_client.runtime_config import RuntimeConfig, runtime_to_legacy_config

logger = logging.getLogger(__name__)


class WorkerState(str, Enum):
    """Worker state enumeration."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class WorkerStatus:
    """Current status of the worker."""
    state: WorkerState
    started_at: Optional[datetime] = None
    last_poll_at: Optional[datetime] = None
    last_error: Optional[str] = None
    poll_count: int = 0
    subscription_active: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "last_error": self.last_error,
            "poll_count": self.poll_count,
            "subscription_active": self.subscription_active,
        }


class WorkerManager:
    """
    Manages the BMS client worker lifecycle.
    
    Provides Start/Stop/Reload functionality for the Web UI.
    The worker runs in a separate thread with its own event loop.
    """
    
    def __init__(self, config_path: str = "config/runtime.yaml"):
        """
        Initialize worker manager.
        
        Args:
            config_path: Path to the runtime configuration file
        """
        self.config_path = Path(config_path)
        self._status = WorkerStatus(state=WorkerState.STOPPED)
        self._lock = threading.RLock()
        
        # Worker thread and event loop
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        
        # BMS client instance (created in worker thread)
        self._client: Optional[Any] = None  # BMSClient
        
        # Callbacks for status updates
        self._on_status_change: Optional[Callable[[WorkerStatus], None]] = None
    
    @property
    def status(self) -> WorkerStatus:
        """Get current worker status."""
        with self._lock:
            return self._status
    
    def _set_state(self, state: WorkerState, error: Optional[str] = None) -> None:
        """Update worker state."""
        with self._lock:
            self._status.state = state
            if error:
                self._status.last_error = error
            if state == WorkerState.RUNNING and self._status.started_at is None:
                self._status.started_at = datetime.now(timezone.utc)
            elif state == WorkerState.STOPPED:
                self._status.started_at = None
                self._status.subscription_active = False
        
        logger.info(f"Worker state changed to: {state.value}")
        if self._on_status_change:
            self._on_status_change(self._status)
    
    def start(self) -> bool:
        """
        Start the worker.
        
        Returns:
            True if started successfully, False if already running
        """
        with self._lock:
            if self._status.state in (WorkerState.RUNNING, WorkerState.STARTING):
                logger.warning("Worker is already running or starting")
                return False
        
        self._set_state(WorkerState.STARTING)
        
        # Start worker thread
        self._worker_thread = threading.Thread(
            target=self._run_worker,
            name="BMSWorker",
            daemon=True,
        )
        self._worker_thread.start()
        
        return True
    
    def stop(self) -> bool:
        """
        Stop the worker.
        
        Returns:
            True if stop was initiated, False if not running
        """
        with self._lock:
            if self._status.state not in (WorkerState.RUNNING, WorkerState.STARTING):
                logger.warning("Worker is not running")
                return False
        
        self._set_state(WorkerState.STOPPING)
        
        # Signal worker to stop
        if self._worker_loop and self._stop_event:
            self._worker_loop.call_soon_threadsafe(self._stop_event.set)
        
        # Wait for thread to finish (with timeout)
        if self._worker_thread:
            self._worker_thread.join(timeout=10.0)
            if self._worker_thread.is_alive():
                logger.warning("Worker thread did not stop gracefully")
        
        self._set_state(WorkerState.STOPPED)
        return True
    
    def reload(self) -> bool:
        """
        Reload configuration and restart worker.
        
        Stops the current worker, reloads config, and starts again.
        
        Returns:
            True if reload initiated successfully
        """
        logger.info("Reloading worker configuration...")
        
        was_running = self._status.state == WorkerState.RUNNING
        
        if was_running:
            self.stop()
        
        # Small delay to ensure clean shutdown
        import time
        time.sleep(0.5)
        
        if was_running:
            return self.start()
        
        logger.info("Configuration reloaded (worker was not running)")
        return True
    
    def _run_worker(self) -> None:
        """Run the worker in a separate thread."""
        try:
            # Create event loop for this thread
            self._worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._worker_loop)
            self._stop_event = asyncio.Event()
            
            # Run async worker
            self._worker_loop.run_until_complete(self._async_worker())
            
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            self._set_state(WorkerState.ERROR, str(e))
        finally:
            if self._worker_loop:
                self._worker_loop.close()
            self._worker_loop = None
            self._stop_event = None
    
    async def _async_worker(self) -> None:
        """Async worker main loop."""
        try:
            # Load configuration
            if not self.config_path.exists():
                raise FileNotFoundError(f"Config not found: {self.config_path}")
            
            # Try loading as new RuntimeConfig first, fall back to legacy Config
            try:
                runtime_config = RuntimeConfig.from_yaml(self.config_path)
                config = runtime_to_legacy_config(runtime_config)
                logger.info(f"Loaded runtime configuration from {self.config_path}")
            except Exception:
                # Fall back to legacy config format
                config = Config.from_yaml(self.config_path)
                runtime_config = None
                logger.info(f"Loaded legacy configuration from {self.config_path}")
            
            # Import here to avoid circular imports
            from bms_2030_5_client.client import BMSClient
            
            # Create client
            self._client = BMSClient(
                config,
                auto_register=True,
                enable_metering=True,
                enable_der_control=True,
            )
            
            # Inject runtime config for power control support
            if runtime_config:
                self._client._runtime_config = runtime_config
                logger.info(
                    f"Injected runtime config (power_control.mode="
                    f"{runtime_config.power_control.mode})"
                )
            
            # Update status
            self._set_state(WorkerState.RUNNING)
            with self._lock:
                if runtime_config:
                    self._status.subscription_active = runtime_config.notification_server.enabled
                else:
                    self._status.subscription_active = config.subscription.enabled
            
            # Run client until stop signal
            client_task = asyncio.create_task(self._client.run_forever())
            stop_task = asyncio.create_task(self._stop_event.wait())
            
            done, pending = await asyncio.wait(
                [client_task, stop_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Stop client gracefully
            if self._client:
                await self._client.stop()
            
            logger.info("Worker stopped gracefully")
            
        except Exception as e:
            logger.exception(f"Worker async error: {e}")
            raise
        finally:
            self._client = None
    
    def update_poll_status(self) -> None:
        """Update last poll timestamp (called from worker)."""
        with self._lock:
            self._status.last_poll_at = datetime.now(timezone.utc)
            self._status.poll_count += 1


# Global worker manager instance
worker_manager = WorkerManager()
