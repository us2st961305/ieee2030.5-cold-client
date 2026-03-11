"""
Polling Worker for IEEE 2030.5 Resources.

Background worker that polls configured poll targets at specified intervals,
parses responses, applies transformations, and writes to Modbus registers.

Features:
- Background thread with async event loop
- Configurable poll targets with individual intervals
- XPath/field_path parsing for XML responses
- Value transformation (scale, offset, clamp)
- Modbus register writing
- In-memory log buffer for monitoring
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from xml.etree import ElementTree as ET

from bms_2030_5_client.core.sep_client import SepClient, SepClientError, SepResponse
from bms_2030_5_client.modbus.register_writer import ModbusRegisterWriter, WriteResult
from bms_2030_5_client.runtime_config import (
    RuntimeConfig,
    ProfileConfig,
    PollTargetConfig,
    ParseConfig,
    TransformConfig,
    ModbusWriteConfig,
)
from bms_2030_5_client.web.log_buffer import log_buffer

logger = logging.getLogger(__name__)


# ============================================
# Poll Result Types
# ============================================

class PollStatus(str, Enum):
    """Status of a poll operation."""
    SUCCESS = "success"
    PARSE_ERROR = "parse_error"
    HTTP_ERROR = "http_error"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    DISABLED = "disabled"
    WRITE_ERROR = "write_error"


@dataclass
class PollResult:
    """Result of a single poll operation."""
    target_id: str
    target_name: str
    status: PollStatus
    timestamp: datetime = field(default_factory=datetime.now)
    
    # HTTP response info
    http_status: Optional[int] = None
    http_latency_ms: float = 0.0
    
    # Parsed value
    raw_value: Optional[str] = None
    parsed_value: Optional[float] = None
    transformed_value: Optional[float] = None
    
    # Modbus write result
    modbus_written: bool = False
    modbus_address: Optional[int] = None
    modbus_error: Optional[str] = None
    
    # Error info
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "http_status": self.http_status,
            "http_latency_ms": self.http_latency_ms,
            "raw_value": self.raw_value,
            "parsed_value": self.parsed_value,
            "transformed_value": self.transformed_value,
            "modbus_written": self.modbus_written,
            "modbus_address": self.modbus_address,
            "modbus_error": self.modbus_error,
            "error_message": self.error_message,
        }
    
    def to_log_message(self) -> str:
        """Convert to log message."""
        if self.status == PollStatus.SUCCESS:
            msg = f"[{self.target_name}] OK: {self.transformed_value}"
            if self.modbus_written:
                msg += f" -> Modbus[{self.modbus_address}]"
            msg += f" ({self.http_latency_ms:.0f}ms)"
            return msg
        else:
            return f"[{self.target_name}] {self.status.value}: {self.error_message}"


@dataclass
class TargetState:
    """Runtime state for a poll target."""
    target: PollTargetConfig
    profile: ProfileConfig
    last_poll_time: Optional[float] = None
    last_result: Optional[PollResult] = None
    poll_count: int = 0
    error_count: int = 0
    
    @property
    def next_poll_time(self) -> float:
        """Calculate next poll time."""
        if self.last_poll_time is None:
            return 0  # Poll immediately
        return self.last_poll_time + (self.target.interval_ms / 1000.0)
    
    @property
    def should_poll(self) -> bool:
        """Check if target should be polled now."""
        if not self.target.enabled:
            return False
        return time.time() >= self.next_poll_time


# ============================================
# XML Parser
# ============================================

class XPathParser:
    """
    XPath parser for IEEE 2030.5 XML responses.
    
    Handles namespaces commonly used in SEP XML by:
    1. Stripping namespace declarations from XML before parsing
    2. Converting XPath to namespace-aware format using {ns} prefix
    3. Using local-name() for robust element matching
    
    Example XPath inputs:
        - "//opModFixedW/value" -> finds element regardless of namespace
        - "DERControlBase/opModFixedW/value" -> relative path
        - ".//value" -> any descendant named 'value'
    """
    
    # IEEE 2030.5 namespace
    SEP_NAMESPACE = "urn:ieee:std:2030.5:ns"
    
    # Common namespaces in IEEE 2030.5
    NAMESPACES = {
        "sep": SEP_NAMESPACE,
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    }
    
    @classmethod
    def parse(cls, xml_text: str, xpath: str) -> Optional[str]:
        """
        Parse XML and extract value using XPath.
        
        Automatically handles IEEE 2030.5 namespaces by stripping them
        before parsing, making XPath expressions simpler.
        
        Args:
            xml_text: XML document text
            xpath: XPath expression (namespace-free, e.g., "//opModFixedW/value")
            
        Returns:
            Extracted text value or None if not found
        """
        try:
            # Strip namespaces from XML for easier XPath matching
            clean_xml = cls._strip_namespaces(xml_text)
            root = ET.fromstring(clean_xml)
            
            # Normalize xpath: remove leading slashes for ElementTree
            # ElementTree uses relative paths from root
            normalized_xpath = cls._normalize_xpath(xpath)
            
            # Try to find element
            element = root.find(normalized_xpath)
            if element is not None and element.text:
                return element.text.strip()
            
            # Try findall for // patterns
            elements = root.findall(normalized_xpath)
            if elements:
                for elem in elements:
                    if elem.text:
                        return elem.text.strip()
            
            # Try alternative: convert // to .//*
            if xpath.startswith('//'):
                alt_xpath = cls._convert_descendant_xpath(xpath)
                elements = root.findall(alt_xpath)
                if elements:
                    for elem in elements:
                        if elem.text:
                            return elem.text.strip()
            
            logger.warning(f"XPath '{xpath}' not found in XML")
            return None
            
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"XPath extraction error: {e}")
            return None
    
    @classmethod
    def parse_all(cls, xml_text: str, xpath: str) -> List[str]:
        """
        Parse XML and extract all matching values using XPath.
        
        Args:
            xml_text: XML document text
            xpath: XPath expression
            
        Returns:
            List of extracted text values
        """
        try:
            clean_xml = cls._strip_namespaces(xml_text)
            root = ET.fromstring(clean_xml)
            normalized_xpath = cls._normalize_xpath(xpath)
            
            results = []
            elements = root.findall(normalized_xpath)
            
            # Also try descendant pattern
            if not elements and xpath.startswith('//'):
                alt_xpath = cls._convert_descendant_xpath(xpath)
                elements = root.findall(alt_xpath)
            
            for elem in elements:
                if elem.text:
                    results.append(elem.text.strip())
            
            return results
            
        except Exception as e:
            logger.error(f"XPath parse_all error: {e}")
            return []
    
    @classmethod
    def _strip_namespaces(cls, xml_text: str) -> str:
        """
        Strip namespace declarations and prefixes from XML.
        
        This makes XPath matching much simpler as we don't need to
        deal with namespace prefixes in element names.
        
        Args:
            xml_text: Original XML with namespaces
            
        Returns:
            XML with namespaces stripped
        """
        # Remove namespace declarations: xmlns="..." and xmlns:prefix="..."
        xml_text = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_text)
        
        # Remove namespace prefixes from tags: <prefix:Element> -> <Element>
        xml_text = re.sub(r'<(\/?)\w+:', r'<\1', xml_text)
        
        return xml_text
    
    @classmethod
    def _normalize_xpath(cls, xpath: str) -> str:
        """
        Normalize XPath for ElementTree compatibility.
        
        ElementTree has limited XPath support:
        - No absolute paths (/ at start)
        - Limited // support
        - No predicates like [@attr='value'] (limited)
        
        Args:
            xpath: Original XPath expression
            
        Returns:
            Normalized XPath for ElementTree
        """
        # Strip leading slashes - ElementTree uses relative paths
        normalized = xpath.lstrip('/')
        
        # Handle // at start -> .//
        if xpath.startswith('//'):
            normalized = './/' + xpath[2:]
        
        return normalized
    
    @classmethod
    def _convert_descendant_xpath(cls, xpath: str) -> str:
        """
        Convert //element/path to .//* pattern for ElementTree.
        
        ElementTree's // support is limited, so we convert patterns like:
        //opModFixedW/value -> .//opModFixedW/value
        
        For nested paths, we may need to find the last element:
        //a/b/c -> .//*[last element match]
        
        Args:
            xpath: XPath starting with //
            
        Returns:
            ElementTree-compatible pattern
        """
        if xpath.startswith('//'):
            # Remove // and prepend .//
            path = xpath[2:]
            return './/' + path
        return xpath


class FieldPathParser:
    """
    Field path parser for nested object access.
    
    Parses paths like "DERControl.DERControlBase.opModFixedW.value"
    """
    
    @classmethod
    def parse(cls, xml_text: str, field_path: str) -> Optional[str]:
        """
        Parse XML and extract value using field path.
        
        Converts field path to XPath and extracts value.
        
        Args:
            xml_text: XML document text
            field_path: Dot-separated field path
            
        Returns:
            Extracted text value or None if not found
        """
        # Convert field path to XPath
        # "DERControl.DERControlBase.opModFixedW.value"
        # -> ".//DERControl/DERControlBase/opModFixedW/value"
        parts = field_path.split('.')
        xpath = ".//" + "/".join(parts)
        
        return XPathParser.parse(xml_text, xpath)


# ============================================
# Polling Worker
# ============================================

class PollingWorkerState(str, Enum):
    """Worker state."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


class PollingWorker:
    """
    Background worker for polling IEEE 2030.5 resources.
    
    Runs in a separate thread with its own event loop.
    Polls configured targets at specified intervals and writes
    results to Modbus registers.
    
    Usage:
        config = RuntimeConfig.from_yaml("config/runtime.yaml")
        worker = PollingWorker(config)
        
        worker.start()
        # ... worker runs in background ...
        worker.stop()
        
        # Reload with new config
        worker.reload(new_config)
    """
    
    # Minimum poll interval (ms)
    MIN_POLL_INTERVAL_MS = 1000
    
    # Main loop interval (seconds)
    LOOP_INTERVAL = 0.1
    
    def __init__(
        self,
        config: RuntimeConfig,
        simulation_mode: bool = True,
    ):
        """
        Initialize polling worker.
        
        Args:
            config: Runtime configuration
            simulation_mode: If True, don't actually write to Modbus
        """
        self._config = config
        self._simulation_mode = simulation_mode
        
        # State
        self._state = PollingWorkerState.STOPPED
        self._lock = threading.RLock()
        
        # Worker thread
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        
        # Target states
        self._target_states: Dict[str, TargetState] = {}
        
        # SEP clients (one per profile)
        self._clients: Dict[str, SepClient] = {}
        
        # Modbus writer
        self._modbus_writer: Optional[ModbusRegisterWriter] = None
        
        # Statistics
        self._total_polls = 0
        self._total_errors = 0
        self._started_at: Optional[datetime] = None
        
        # Callbacks
        self._on_poll_result: Optional[Callable[[PollResult], None]] = None
        
        # Initialize target states
        self._init_target_states()
    
    @property
    def state(self) -> PollingWorkerState:
        """Get current worker state."""
        with self._lock:
            return self._state
    
    @property
    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._state == PollingWorkerState.RUNNING
    
    @property
    def statistics(self) -> dict:
        """Get worker statistics."""
        with self._lock:
            return {
                "state": self._state.value,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "total_polls": self._total_polls,
                "total_errors": self._total_errors,
                "active_targets": len([s for s in self._target_states.values() if s.target.enabled]),
                "simulation_mode": self._simulation_mode,
            }
    
    def _init_target_states(self) -> None:
        """Initialize target states from config."""
        self._target_states.clear()
        
        for target in self._config.poll_targets:
            profile = self._config.get_profile(target.profile_name)
            if profile is None:
                logger.warning(f"Profile '{target.profile_name}' not found for target '{target.id}'")
                continue
            
            self._target_states[target.id] = TargetState(
                target=target,
                profile=profile,
            )
            
            if target.enabled:
                logger.info(f"Poll target '{target.id}' initialized (interval: {target.interval_ms}ms)")
    
    def start(self) -> bool:
        """
        Start the polling worker.
        
        Returns:
            True if started successfully
        """
        with self._lock:
            if self._state in (PollingWorkerState.RUNNING, PollingWorkerState.STARTING):
                logger.warning("Worker is already running or starting")
                return False
            
            self._state = PollingWorkerState.STARTING
        
        # Start worker thread
        self._thread = threading.Thread(
            target=self._run_worker,
            name="PollingWorker",
            daemon=True,
        )
        self._thread.start()
        
        log_buffer.add(
            "Polling worker started",
            level="INFO",
            logger_name="polling.worker",
        )
        
        return True
    
    def stop(self) -> bool:
        """
        Stop the polling worker.
        
        Returns:
            True if stopped successfully
        """
        with self._lock:
            if self._state not in (PollingWorkerState.RUNNING, PollingWorkerState.STARTING):
                logger.warning("Worker is not running")
                return False
            
            self._state = PollingWorkerState.STOPPING
        
        # Signal stop
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        
        # Wait for thread
        if self._thread:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                logger.warning("Worker thread did not stop gracefully")
        
        with self._lock:
            self._state = PollingWorkerState.STOPPED
        
        log_buffer.add(
            "Polling worker stopped",
            level="INFO",
            logger_name="polling.worker",
        )
        
        return True
    
    def reload(self, new_config: RuntimeConfig) -> bool:
        """
        Reload worker with new configuration.
        
        Stops the worker, updates config, and restarts.
        
        Args:
            new_config: New runtime configuration
            
        Returns:
            True if reload successful
        """
        was_running = self.is_running
        
        if was_running:
            self.stop()
        
        # Update config
        self._config = new_config
        self._init_target_states()
        
        # Small delay
        time.sleep(0.5)
        
        if was_running:
            return self.start()
        
        log_buffer.add(
            "Polling worker configuration reloaded",
            level="INFO",
            logger_name="polling.worker",
        )
        
        return True
    
    def _run_worker(self) -> None:
        """Run worker in thread."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._stop_event = asyncio.Event()
            
            self._loop.run_until_complete(self._async_main())
            
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            log_buffer.add(
                f"Polling worker error: {e}",
                level="ERROR",
                logger_name="polling.worker",
            )
        finally:
            # Cleanup
            if self._loop:
                self._loop.run_until_complete(self._cleanup())
                self._loop.close()
            self._loop = None
            self._stop_event = None
            
            with self._lock:
                self._state = PollingWorkerState.STOPPED
    
    async def _async_main(self) -> None:
        """Async main loop."""
        # Initialize
        await self._init_clients()
        await self._init_modbus_writer()
        
        with self._lock:
            self._state = PollingWorkerState.RUNNING
            self._started_at = datetime.now()
        
        logger.info(f"Polling worker running with {len(self._target_states)} targets")
        
        # Main polling loop
        while not self._stop_event.is_set():
            try:
                await self._poll_cycle()
                await asyncio.sleep(self.LOOP_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Poll cycle error: {e}")
                await asyncio.sleep(1.0)
    
    async def _init_clients(self) -> None:
        """Initialize SEP clients for each profile."""
        self._clients.clear()
        
        for profile in self._config.profiles:
            try:
                client = SepClient(profile)
                await client.connect()
                self._clients[profile.name] = client
                logger.info(f"SEP client '{profile.name}' connected to {profile.server_base_url}")
            except SepClientError as e:
                logger.error(f"Failed to connect SEP client '{profile.name}': {e}")
                log_buffer.add(
                    f"SEP client '{profile.name}' connection failed: {e.user_message}",
                    level="ERROR",
                    logger_name="polling.worker",
                )
    
    async def _init_modbus_writer(self) -> None:
        """Initialize Modbus writer."""
        self._modbus_writer = ModbusRegisterWriter(
            host=self._config.modbus.host,
            port=self._config.modbus.port,
            unit_id=self._config.modbus.unit_id,
            timeout=self._config.modbus.timeout,
            simulation_mode=self._simulation_mode,
        )
        await self._modbus_writer.connect()
    
    async def _cleanup(self) -> None:
        """Cleanup resources."""
        # Close SEP clients
        for name, client in self._clients.items():
            try:
                await client.close()
            except Exception as e:
                logger.error(f"Error closing client '{name}': {e}")
        self._clients.clear()
        
        # Close Modbus writer
        if self._modbus_writer:
            await self._modbus_writer.close()
            self._modbus_writer = None
    
    async def _poll_cycle(self) -> None:
        """Execute one poll cycle."""
        now = time.time()
        
        for target_id, state in self._target_states.items():
            if state.should_poll:
                result = await self._poll_target(state)
                
                # Update state
                state.last_poll_time = now
                state.last_result = result
                state.poll_count += 1
                
                if result.status != PollStatus.SUCCESS:
                    state.error_count += 1
                
                # Update statistics
                with self._lock:
                    self._total_polls += 1
                    if result.status != PollStatus.SUCCESS:
                        self._total_errors += 1
                
                # Log result
                log_buffer.add(
                    result.to_log_message(),
                    level="INFO" if result.status == PollStatus.SUCCESS else "WARNING",
                    logger_name="polling.worker",
                )
                
                # Callback
                if self._on_poll_result:
                    self._on_poll_result(result)
    
    async def _poll_target(self, state: TargetState) -> PollResult:
        """
        Poll a single target.
        
        Args:
            state: Target state
            
        Returns:
            PollResult
        """
        target = state.target
        profile = state.profile
        
        # Check if target is enabled
        if not target.enabled:
            return PollResult(
                target_id=target.id,
                target_name=target.name,
                status=PollStatus.DISABLED,
            )
        
        # Get client
        client = self._clients.get(profile.name)
        if client is None:
            return PollResult(
                target_id=target.id,
                target_name=target.name,
                status=PollStatus.CONNECTION_ERROR,
                error_message=f"SEP client '{profile.name}' not available",
            )
        
        # Perform HTTP request
        try:
            response = await client.get(target.uri)
            
            # Check HTTP status
            if not response.is_success:
                return PollResult(
                    target_id=target.id,
                    target_name=target.name,
                    status=PollStatus.HTTP_ERROR,
                    http_status=response.status_code,
                    http_latency_ms=response.latency_ms,
                    error_message=f"HTTP {response.status_code}",
                )
            
            # Parse response
            raw_value = self._parse_response(response.body, target.parse)
            
            if raw_value is None:
                return PollResult(
                    target_id=target.id,
                    target_name=target.name,
                    status=PollStatus.PARSE_ERROR,
                    http_status=response.status_code,
                    http_latency_ms=response.latency_ms,
                    error_message="Failed to parse value from response",
                )
            
            # Convert to float
            try:
                parsed_value = float(raw_value)
            except (ValueError, TypeError):
                return PollResult(
                    target_id=target.id,
                    target_name=target.name,
                    status=PollStatus.PARSE_ERROR,
                    http_status=response.status_code,
                    http_latency_ms=response.latency_ms,
                    raw_value=raw_value,
                    error_message=f"Cannot convert '{raw_value}' to number",
                )
            
            # Apply transformation
            transformed_value = target.transform.apply(parsed_value)
            
            # Write to Modbus if configured
            modbus_written = False
            modbus_address = None
            modbus_error = None
            
            if target.modbus_write and self._modbus_writer:
                write_result = await self._modbus_writer.write_from_config(
                    target.modbus_write,
                    transformed_value,
                )
                modbus_written = write_result.success
                modbus_address = write_result.address
                if not write_result.success:
                    modbus_error = write_result.error
            
            # Check for write errors
            if target.modbus_write and not modbus_written:
                return PollResult(
                    target_id=target.id,
                    target_name=target.name,
                    status=PollStatus.WRITE_ERROR,
                    http_status=response.status_code,
                    http_latency_ms=response.latency_ms,
                    raw_value=raw_value,
                    parsed_value=parsed_value,
                    transformed_value=transformed_value,
                    modbus_written=False,
                    modbus_address=modbus_address,
                    modbus_error=modbus_error,
                    error_message=f"Modbus write failed: {modbus_error}",
                )
            
            # Success
            return PollResult(
                target_id=target.id,
                target_name=target.name,
                status=PollStatus.SUCCESS,
                http_status=response.status_code,
                http_latency_ms=response.latency_ms,
                raw_value=raw_value,
                parsed_value=parsed_value,
                transformed_value=transformed_value,
                modbus_written=modbus_written,
                modbus_address=modbus_address,
            )
            
        except SepClientError as e:
            # Determine error type
            from bms_2030_5_client.core.sep_client import TimeoutError as SepTimeout
            from bms_2030_5_client.core.sep_client import ConnectionError as SepConnError
            
            if isinstance(e, SepTimeout):
                status = PollStatus.TIMEOUT
            elif isinstance(e, SepConnError):
                status = PollStatus.CONNECTION_ERROR
            else:
                status = PollStatus.HTTP_ERROR
            
            return PollResult(
                target_id=target.id,
                target_name=target.name,
                status=status,
                error_message=e.user_message,
            )
        
        except Exception as e:
            logger.exception(f"Unexpected error polling {target.id}: {e}")
            return PollResult(
                target_id=target.id,
                target_name=target.name,
                status=PollStatus.HTTP_ERROR,
                error_message=str(e),
            )
    
    def _parse_response(self, body: str, parse_config: ParseConfig) -> Optional[str]:
        """
        Parse response body to extract value.
        
        Args:
            body: Response body
            parse_config: Parse configuration
            
        Returns:
            Extracted value or None
        """
        if parse_config.format != "sep_xml":
            logger.warning(f"Unsupported parse format: {parse_config.format}")
            return None
        
        # Try xpath first
        if parse_config.xpath:
            return XPathParser.parse(body, parse_config.xpath)
        
        # Try field_path
        if parse_config.field_path:
            return FieldPathParser.parse(body, parse_config.field_path)
        
        logger.warning("No xpath or field_path configured for parsing")
        return None
    
    def get_target_states(self) -> Dict[str, dict]:
        """Get current state of all targets."""
        result = {}
        for target_id, state in self._target_states.items():
            result[target_id] = {
                "id": target_id,
                "name": state.target.name,
                "enabled": state.target.enabled,
                "interval_ms": state.target.interval_ms,
                "poll_count": state.poll_count,
                "error_count": state.error_count,
                "last_poll": state.last_poll_time,
                "last_result": state.last_result.to_dict() if state.last_result else None,
            }
        return result
    
    def set_target_enabled(self, target_id: str, enabled: bool) -> bool:
        """
        Enable or disable a target.
        
        Args:
            target_id: Target ID
            enabled: Enable state
            
        Returns:
            True if target was found and updated
        """
        if target_id not in self._target_states:
            return False
        
        state = self._target_states[target_id]
        state.target.enabled = enabled
        
        log_buffer.add(
            f"Poll target '{target_id}' {'enabled' if enabled else 'disabled'}",
            level="INFO",
            logger_name="polling.worker",
        )
        
        return True


# Global polling worker instance
polling_worker: Optional[PollingWorker] = None


def get_polling_worker() -> Optional[PollingWorker]:
    """Get the global polling worker instance."""
    return polling_worker


def create_polling_worker(config: RuntimeConfig, simulation_mode: bool = True) -> PollingWorker:
    """Create and set the global polling worker."""
    global polling_worker
    polling_worker = PollingWorker(config, simulation_mode=simulation_mode)
    return polling_worker
