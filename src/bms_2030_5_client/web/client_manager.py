"""
Client Manager - Shared state between Web UI and BMSClient.

Provides a singleton that manages the BMSClient lifecycle,
allowing the web UI to control and monitor the automation client.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bms_2030_5_client.client import BMSClient
    from bms_2030_5_client.models import BMSSnapshot

# Import notification server manager for dynamic mode selection
from bms_2030_5_client.web.notification_server import get_notification_manager

logger = logging.getLogger(__name__)


class ClientState(Enum):
    """BMSClient states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ClientStatus:
    """Current status of the BMSClient."""
    state: ClientState = ClientState.STOPPED
    started_at: Optional[datetime] = None
    last_report_at: Optional[datetime] = None
    last_error: Optional[str] = None
    
    # Connection status
    modbus_connected: bool = False
    ieee2030_5_connected: bool = False
    
    # Modbus health (populated from BMSDataCollector)
    modbus_health: Optional[Dict[str, Any]] = None
    
    # Registration status
    edev_href: Optional[str] = None
    der_path: Optional[str] = None
    mup_href: Optional[str] = None
    
    # DER Control mode: "polling" or "subscription"
    control_mode: str = "polling"
    
    # Stats
    report_count: int = 0
    meter_upload_count: int = 0
    der_control_count: int = 0
    
    # DER Control stats (from DERClient)
    der_control_stats: Optional[Dict[str, Any]] = None
    
    # Latest data
    latest_snapshot: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_report_at": self.last_report_at.isoformat() if self.last_report_at else None,
            "last_error": self.last_error,
            "modbus_connected": self.modbus_connected,
            "sep_connected": self.ieee2030_5_connected,  # Alias for JS
            "ieee2030_5_connected": self.ieee2030_5_connected,
            "edev_href": self.edev_href,
            "der_path": self.der_path,
            "mup_href": self.mup_href,
            "control_mode": self.control_mode,
            "poll_count": self.report_count,  # Alias for JS
            "upload_count": self.meter_upload_count,  # Alias for JS
            "report_count": self.report_count,
            "meter_upload_count": self.meter_upload_count,
            "der_control_count": self.der_control_count,
            "der_control_stats": self.der_control_stats,
            "latest_snapshot": self.latest_snapshot,
            "modbus_health": self.modbus_health,
        }


class ClientManager:
    """
    Singleton manager for BMSClient.
    
    Provides:
    - Client lifecycle management (start/stop/restart)
    - Status monitoring
    - Configuration management
    - Event callbacks for UI updates
    """
    
    _instance: Optional["ClientManager"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "ClientManager":
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize manager (only once)."""
        if getattr(self, "_initialized", False):
            return
        
        self._client: Optional["BMSClient"] = None
        self._status = ClientStatus()
        self._config_path: Optional[Path] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client_thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[ClientStatus], None]] = []
        
        # Settings
        self._auto_register = True
        self._enable_metering = True
        self._enable_der_control = True
        self._enable_subscription = False
        
        self._initialized = True
    
    @property
    def status(self) -> ClientStatus:
        """Get current client status."""
        return self._status
    
    @property
    def client(self) -> Optional["BMSClient"]:
        """Get the BMSClient instance."""
        return self._client
    
    @property
    def is_running(self) -> bool:
        """Check if client is running."""
        return self._status.state == ClientState.RUNNING
    
    def configure(
        self,
        config_path: str = "config/config.yaml",
        auto_register: bool = True,
        enable_metering: bool = True,
        enable_der_control: bool = True,
        enable_subscription: bool = False,
    ) -> None:
        """
        Configure the client manager.
        
        Args:
            config_path: Path to config.yaml
            auto_register: Auto-register with IEEE 2030.5 server
            enable_metering: Enable MirrorUsagePoint metering
            enable_der_control: Enable DER control polling/subscription
            enable_subscription: Use push-based subscription (vs polling)
        """
        self._config_path = Path(config_path)
        self._auto_register = auto_register
        self._enable_metering = enable_metering
        self._enable_der_control = enable_der_control
        self._enable_subscription = enable_subscription
        
        logger.info(f"ClientManager configured with: {config_path}")
    
    def add_status_callback(self, callback: Callable[[ClientStatus], None]) -> None:
        """Add callback for status updates."""
        self._callbacks.append(callback)
    
    def _notify_callbacks(self) -> None:
        """Notify all callbacks of status update."""
        for callback in self._callbacks:
            try:
                callback(self._status)
            except Exception as e:
                logger.warning(f"Status callback error: {e}")
    
    def _on_modbus_health_change(self, health) -> None:
        """Callback when Modbus connection health state changes."""
        from bms_2030_5_client.modbus.modbus_client import ModbusConnectionState
        self._status.modbus_connected = (
            health.state == ModbusConnectionState.CONNECTED
        )
        self._status.modbus_health = health.to_dict()
        self._notify_callbacks()

    def _on_bms_snapshot(self, snapshot: "BMSSnapshot") -> None:
        """Callback when new BMS snapshot is available."""
        from bms_2030_5_client.web.data_recorder import get_data_recorder
        
        self._status.last_report_at = datetime.now(timezone.utc)
        self._status.report_count += 1
        
        # Store snapshot as dict
        if hasattr(snapshot, "to_dict"):
            self._status.latest_snapshot = snapshot.to_dict()
        else:
            self._status.latest_snapshot = {
                "voltage": getattr(snapshot, "voltage", None),
                "current": getattr(snapshot, "current", None),
                "soc": getattr(snapshot, "soc", None),
                "power": getattr(snapshot, "power", None),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        # Record to data recorder
        try:
            recorder = get_data_recorder()
            recorder.record_bms_snapshot(snapshot)
        except Exception as e:
            logger.warning(f"Failed to record BMS snapshot: {e}")
        
        self._notify_callbacks()
    
    async def _run_client(self) -> None:
        """Run the BMSClient in async context."""
        from bms_2030_5_client.client import BMSClient
        from bms_2030_5_client.config import Config
        
        try:
            self._status.state = ClientState.STARTING
            self._notify_callbacks()
            
            # Load config
            config = Config.from_yaml(str(self._config_path))
            
            # Determine subscription mode based on notification server status
            # If notification server is running -> use subscription (push-based)
            # If notification server is not running -> use polling
            notification_manager = get_notification_manager()
            use_subscription = notification_manager.is_running
            
            if use_subscription:
                logger.info(
                    "Notification Server is running - using Subscription mode (push-based)"
                )
            else:
                logger.info(
                    "Notification Server is not running - using Polling mode"
                )
            
            # Create client
            self._client = BMSClient(
                config,
                auto_register=self._auto_register,
                enable_metering=self._enable_metering,
                enable_der_control=self._enable_der_control,
                enable_subscription=use_subscription,
            )
            
            # Inject runtime config for power control support
            try:
                from bms_2030_5_client.runtime_config import RuntimeConfig
                rt_config_path = self._config_path.parent / "runtime.yaml"
                if rt_config_path.exists():
                    self._client._runtime_config = RuntimeConfig.from_yaml(rt_config_path)
                    logger.info(
                        f"Injected runtime config (power_control.mode="
                        f"{self._client._runtime_config.power_control.mode})"
                    )
            except Exception as e:
                logger.warning(f"Could not load runtime config for power control: {e}")
            
            # Add snapshot callback
            self._client.add_callback(self._on_bms_snapshot)
            
            # Register Modbus health state callback for real-time status updates
            self._client.data_collector.add_state_callback(self._on_modbus_health_change)

            # Start client
            await self._client.start()
            
            # Update status
            self._status.state = ClientState.RUNNING
            self._status.started_at = datetime.now(timezone.utc)
            self._status.modbus_connected = True
            self._status.ieee2030_5_connected = True
            self._status.edev_href = self._client._edev_href
            self._status.der_path = self._client._der_path
            self._status.mup_href = self._client._mup_href
            self._status.control_mode = "subscription" if use_subscription else "polling"
            self._status.last_error = None
            self._notify_callbacks()
            
            logger.info(
                f"BMSClient started successfully (control_mode={self._status.control_mode})"
            )
            
            # Run forever
            while self._status.state == ClientState.RUNNING:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.exception(f"BMSClient error: {e}")
            self._status.state = ClientState.ERROR
            self._status.last_error = str(e)
            self._notify_callbacks()
        finally:
            if self._client:
                try:
                    await self._client.stop()
                except Exception as e:
                    logger.warning(f"Error stopping client: {e}")
            
            self._status.state = ClientState.STOPPED
            self._status.modbus_connected = False
            self._status.ieee2030_5_connected = False
            self._notify_callbacks()
    
    def _run_event_loop(self) -> None:
        """Run event loop in thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._run_client())
        finally:
            self._loop.close()
            self._loop = None
    
    def start(self) -> bool:
        """
        Start the BMSClient in a background thread.
        
        Returns:
            True if started successfully
        """
        if self._status.state in (ClientState.RUNNING, ClientState.STARTING):
            logger.warning("Client already running or starting")
            return False
        
        if not self._config_path or not self._config_path.exists():
            self._status.last_error = f"Config file not found: {self._config_path}"
            logger.error(self._status.last_error)
            return False
        
        # Start client in background thread
        self._client_thread = threading.Thread(
            target=self._run_event_loop,
            name="bms-client",
            daemon=True,
        )
        self._client_thread.start()
        
        logger.info("BMSClient thread started")
        return True
    
    def stop(self) -> bool:
        """
        Stop the BMSClient.
        
        Returns:
            True if stop initiated
        """
        if self._status.state not in (ClientState.RUNNING, ClientState.STARTING):
            logger.warning("Client not running")
            return False
        
        self._status.state = ClientState.STOPPING
        self._notify_callbacks()
        
        # The _run_client loop will detect state change and exit
        # Wait for thread to finish
        if self._client_thread:
            self._client_thread.join(timeout=10)
            if self._client_thread.is_alive():
                logger.warning("Client thread did not stop gracefully")
            self._client_thread = None
        
        logger.info("BMSClient stopped")
        return True
    
    def restart(self) -> bool:
        """Restart the BMSClient."""
        if self.is_running:
            self.stop()
        return self.start()
    
    # ==========================================
    # Resource Access Methods
    # ==========================================
    
    def get_edev_href(self) -> Optional[str]:
        """Get EndDevice href."""
        return self._status.edev_href
    
    def get_der_path(self) -> Optional[str]:
        """Get DER path."""
        return self._status.der_path
    
    def get_mup_href(self) -> Optional[str]:
        """Get MirrorUsagePoint href."""
        return self._status.mup_href
    
    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """Get latest BMS snapshot."""
        return self._status.latest_snapshot
    
    async def fetch_resource(self, path: str) -> Optional[str]:
        """
        Fetch a resource from IEEE 2030.5 server using client connection.
        
        Args:
            path: Resource path (e.g., "/dcap")
            
        Returns:
            XML response body or None
        """
        if not self._client or not self._client.ieee2030_5_client:
            logger.warning("IEEE 2030.5 client not connected")
            return None
        
        try:
            response = await self._client.ieee2030_5_client.get(path)
            return response
        except Exception as e:
            logger.error(f"Failed to fetch {path}: {e}")
            return None
    
    async def create_meter(
        self,
        description: str = "BMS Meter",
        device_category: int = 7,
    ) -> Optional[str]:
        """
        Create a MirrorUsagePoint (meter) using the client.
        
        Args:
            description: Meter description
            device_category: Device category (7 = Battery Storage)
            
        Returns:
            MirrorUsagePoint href or None
        """
        if not self._client:
            logger.warning("BMSClient not running")
            return None
        
        try:
            # Use client's register_meter method
            await self._client._register_meter()
            href = self._client._mup_href
            self._status.mup_href = href
            return href
        except Exception as e:
            logger.error(f"Failed to create meter: {e}")
            return None


    def get_der_control_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get DER control statistics from the running client.
        
        Returns detailed stats including:
        - FSA/Program/Control poll counts
        - Active controls
        - Tracked programs
        - Simulation mode status
        """
        if not self._client:
            return None
        
        stats = {
            "is_running": False,
            "simulation_mode": True,
            "fsa_polls": 0,
            "program_polls": 0,
            "control_polls": 0,
            "controls_executed": 0,
            "responses_sent": 0,
            "errors": 0,
            "tracked_fsa_count": 0,
            "tracked_programs_count": 0,
            "tracked_controls_count": 0,
            "active_control": None,
        }
        
        try:
            # Get DERClient stats if available
            der_client = getattr(self._client, '_der_client', None)
            if der_client:
                stats["is_running"] = der_client.is_running
                der_stats = der_client.stats
                stats.update({
                    "fsa_polls": der_stats.get("fsa_polls", 0),
                    "program_polls": der_stats.get("program_polls", 0),
                    "control_polls": der_stats.get("control_polls", 0),
                    "controls_executed": der_stats.get("controls_executed", 0),
                    "responses_sent": der_stats.get("responses_sent", 0),
                    "errors": der_stats.get("errors", 0),
                    "tracked_fsa_count": len(der_client._tracked_fsa),
                    "tracked_programs_count": len(der_client._tracked_programs),
                    "tracked_controls_count": len(der_client._tracked_controls),
                })
            
            # Get PowerController status
            power_controller = getattr(self._client, '_power_controller', None)
            if power_controller:
                stats["simulation_mode"] = power_controller.simulation_mode
                stats["power_control_mode"] = power_controller.control_mode.value
            
            # Get SubscriptionManager stats if using subscription mode
            sub_manager = getattr(self._client, '_subscription_manager', None)
            if sub_manager:
                sub_stats = sub_manager.stats
                stats["subscriptions"] = {
                    "created": sub_stats.get("subscriptions_created", 0),
                    "renewed": sub_stats.get("subscriptions_renewed", 0),
                    "failed": sub_stats.get("subscriptions_failed", 0),
                    "active_count": len(sub_manager.subscriptions),
                }
        
        except Exception as e:
            logger.warning(f"Failed to get DER control stats: {e}")
        
        return stats
    
    def update_der_control_stats(self) -> None:
        """Update DER control stats in status."""
        stats = self.get_der_control_stats()
        if stats:
            self._status.der_control_stats = stats
            self._status.der_control_count = stats.get("controls_executed", 0)


# Global singleton instance
client_manager = ClientManager()


def get_client_manager() -> ClientManager:
    """Get the global ClientManager instance."""
    return client_manager
