"""
Task Supervisor for background asyncio tasks.

Monitors registered tasks and automatically restarts them on failure
with exponential backoff. Provides unified health status reporting.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """State of a managed task."""
    PENDING = "pending"
    RUNNING = "running"
    RESTARTING = "restarting"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ManagedTask:
    """A task managed by the supervisor."""
    name: str
    coro_factory: Callable[[], Coroutine[Any, Any, None]]
    task: asyncio.Task | None = None
    state: TaskState = TaskState.PENDING
    restart_count: int = 0
    max_restarts: int = 10
    backoff_base: float = 1.0
    backoff_max: float = 300.0
    last_start_time: float = 0.0
    last_failure_time: float = 0.0
    last_error: str | None = None

    @property
    def is_alive(self) -> bool:
        """Check if the task is currently running."""
        return self.task is not None and not self.task.done()

    def to_dict(self) -> dict:
        """Convert to dictionary for status reporting."""
        return {
            "name": self.name,
            "state": self.state.value,
            "alive": self.is_alive,
            "restart_count": self.restart_count,
            "max_restarts": self.max_restarts,
            "last_error": self.last_error,
        }


class TaskSupervisor:
    """
    Unified supervisor for background asyncio tasks.

    Monitors all registered tasks and restarts them on failure
    with exponential backoff. Provides a single health query endpoint.

    Usage:
        supervisor = TaskSupervisor()
        supervisor.register("reporting", lambda: client._reporting_loop())
        supervisor.register("metering", lambda: client._metering_loop())
        await supervisor.start_all()
        ...
        await supervisor.stop_all()
    """

    MONITOR_INTERVAL: float = 10.0  # seconds between health checks

    def __init__(self) -> None:
        self._tasks: dict[str, ManagedTask] = {}
        self._running = False
        self._monitor_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        coro_factory: Callable[[], Coroutine[Any, Any, None]],
        *,
        max_restarts: int = 10,
        backoff_base: float = 1.0,
        backoff_max: float = 300.0,
    ) -> None:
        """
        Register a background task to be supervised.

        Args:
            name: Unique task name.
            coro_factory: Callable that returns a new coroutine each time.
            max_restarts: Maximum number of automatic restarts.
            backoff_base: Initial backoff delay in seconds.
            backoff_max: Maximum backoff delay in seconds.
        """
        if name in self._tasks:
            logger.warning(f"Task '{name}' already registered — replacing")
        self._tasks[name] = ManagedTask(
            name=name,
            coro_factory=coro_factory,
            max_restarts=max_restarts,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
        )

    async def start_all(self) -> None:
        """Start all registered tasks and the monitor loop."""
        if self._running:
            return
        self._running = True
        for mt in self._tasks.values():
            self._launch(mt)
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(), name="task-supervisor-monitor"
        )
        logger.info(
            f"TaskSupervisor started — monitoring {len(self._tasks)} task(s): "
            f"{list(self._tasks.keys())}"
        )

    async def stop_all(self) -> None:
        """Cancel all monitored tasks and the monitor loop."""
        self._running = False

        # Stop monitor first
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        # Cancel all managed tasks
        for mt in self._tasks.values():
            if mt.task and not mt.task.done():
                mt.task.cancel()
                try:
                    await mt.task
                except asyncio.CancelledError:
                    pass
            mt.task = None
            mt.state = TaskState.STOPPED

        logger.info("TaskSupervisor stopped — all tasks cancelled")

    def get_health(self) -> dict[str, Any]:
        """
        Get health status of all managed tasks.

        Returns:
            Dictionary with per-task health info.
        """
        return {
            "running": self._running,
            "tasks": {
                name: mt.to_dict() for name, mt in self._tasks.items()
            },
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _launch(self, mt: ManagedTask) -> None:
        """Create and start an asyncio task for a ManagedTask."""
        mt.task = asyncio.create_task(
            self._run_wrapper(mt), name=f"supervised:{mt.name}"
        )
        mt.state = TaskState.RUNNING
        mt.last_start_time = time.monotonic()

    async def _run_wrapper(self, mt: ManagedTask) -> None:
        """Wrap coroutine execution so exceptions are recorded, not lost."""
        try:
            await mt.coro_factory()
        except asyncio.CancelledError:
            raise  # propagate cancellation normally
        except Exception as exc:
            mt.last_error = str(exc)
            mt.last_failure_time = time.monotonic()
            logger.error(
                f"Supervised task '{mt.name}' crashed: {exc}", exc_info=True
            )
            # Task is now done; the monitor loop will handle restart.

    async def _monitor_loop(self) -> None:
        """Periodically check task health and restart dead tasks."""
        while self._running:
            try:
                await asyncio.sleep(self.MONITOR_INTERVAL)
            except asyncio.CancelledError:
                break

            for mt in self._tasks.values():
                if not self._running:
                    break
                if mt.state == TaskState.STOPPED:
                    continue
                if mt.task is None or not mt.task.done():
                    continue

                # Check whether the task crashed or finished normally.
                # _run_wrapper sets last_failure_time when an exception occurs.
                # If the task completed without updating last_failure_time since
                # it was last started, it finished cleanly.
                crashed = mt.last_failure_time > mt.last_start_time
                if not crashed:
                    # Task finished cleanly — do not restart
                    mt.state = TaskState.STOPPED
                    logger.info(f"Task '{mt.name}' completed normally — not restarting")
                    continue

                # Task crashed — decide whether to restart
                if mt.restart_count >= mt.max_restarts:
                    if mt.state != TaskState.FAILED:
                        mt.state = TaskState.FAILED
                        logger.critical(
                            f"Task '{mt.name}' exceeded max restarts "
                            f"({mt.max_restarts}) — entering FAILED state. "
                            f"Last error: {mt.last_error}"
                        )
                    continue

                # Exponential backoff
                delay = min(
                    mt.backoff_base * (2 ** mt.restart_count),
                    mt.backoff_max,
                )
                mt.state = TaskState.RESTARTING
                mt.restart_count += 1
                logger.warning(
                    f"Restarting task '{mt.name}' "
                    f"(attempt {mt.restart_count}/{mt.max_restarts}) "
                    f"after {delay:.1f}s backoff"
                )
                await asyncio.sleep(delay)

                if not self._running:
                    break
                self._launch(mt)
                logger.info(f"Task '{mt.name}' restarted successfully")
