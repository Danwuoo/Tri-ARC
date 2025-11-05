from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from .context import ModuleContext, ModuleTaskContext
from .results import ModuleResult, ModuleSolveStatus, ModuleTelemetry

LOGGER = logging.getLogger("arc.core.module_base")


class ModuleLifecycleState(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    SHUTDOWN = "shutdown"


class ModuleEventType(str, Enum):
    START = "module_start"
    STOP = "module_stop"
    ERROR = "module_error"


@dataclass(frozen=True)
class ModuleCapabilities:
    supports_partial_results: bool = False
    supports_resume: bool = False
    requires_gpu: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "supports_partial_results": self.supports_partial_results,
            "supports_resume": self.supports_resume,
            "requires_gpu": self.requires_gpu,
        }
        if self.extras:
            payload.update(self.extras)
        return payload


@dataclass
class ModuleEvent:
    module: str
    stage: str
    event_type: ModuleEventType
    status: str
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)


class ModuleError(RuntimeError):
    """Raised when lifecycle expectations are violated."""


StageCallable = TypeVar("StageCallable", bound=Callable[..., Any])


class SolverModule:
    """Base contract for solver lanes orchestrated by the scheduler."""

    module_name: str = "solver_module"
    capabilities: ModuleCapabilities = ModuleCapabilities()

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self._context: Optional[ModuleContext] = None
        self._logger = logger or logging.getLogger(f"arc.module.{self.module_name}")
        self._state = ModuleLifecycleState.CREATED
        self._last_telemetry: Optional[ModuleTelemetry] = None
        self._event_history: list[ModuleEvent] = []

    # ------------------------------------------------------------------ #
    # Public lifecycle
    # ------------------------------------------------------------------ #
    def initialize(self, context: ModuleContext) -> None:
        if self._state != ModuleLifecycleState.CREATED:
            raise ModuleError(f"{self.module_name} cannot initialise from state {self._state}.")
        self._context = context
        self._logger = context.logger if context.logger else self._logger
        self._logger.debug("Initialising module with capabilities=%s", self.capabilities.to_dict())
        self._run_stage("initialize", self._on_initialize, context)
        self._state = ModuleLifecycleState.READY

    def prepare_task(self, task_payload: Dict[str, Any]) -> ModuleTaskContext:
        self._ensure_ready(stage="prepare_task")
        assert self._context is not None
        task_id = str(task_payload.get("task_id", "unknown_task"))
        task_context = ModuleTaskContext(
            task_id=task_id,
            task_payload=task_payload,
            module_context=self._context,
        )
        prepared, telemetry = self._run_stage("prepare_task", self._on_prepare_task, task_context)
        if prepared is None:
            prepared = task_context
        elif not isinstance(prepared, ModuleTaskContext):
            raise ModuleError(f"{self.module_name} prepare_task must return ModuleTaskContext, got {type(prepared)!r}.")
        prepared.metadata.setdefault("task_id", task_id)
        if telemetry:
            prepared.metadata.setdefault("telemetry", {})["prepare_task"] = {
                "started_at": telemetry.started_at,
                "duration_s": telemetry.duration_s,
                "status": telemetry.status,
            }
        return prepared

    def solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        self._ensure_ready(stage="solve")
        self._state = ModuleLifecycleState.RUNNING
        try:
            result, telemetry = self._run_stage("solve", self._on_solve, task_context)
        finally:
            self._state = ModuleLifecycleState.READY

        if not isinstance(result, ModuleResult):
            raise ModuleError(f"{self.module_name} solve must return ModuleResult, got {type(result)!r}.")

        if telemetry and result.telemetry is None:
            result.telemetry = telemetry
        self._last_telemetry = result.telemetry
        return result

    def shutdown(self) -> None:
        if self._state == ModuleLifecycleState.SHUTDOWN:
            return
        if self._context is None:
            raise ModuleError(f"{self.module_name} shutdown called before initialise.")
        self._run_stage("shutdown", self._on_shutdown, self._context)
        self._state = ModuleLifecycleState.SHUTDOWN

    # ------------------------------------------------------------------ #
    # Introspection helpers
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> ModuleLifecycleState:
        return self._state

    @property
    def last_telemetry(self) -> Optional[ModuleTelemetry]:
        return self._last_telemetry

    @property
    def events(self) -> Tuple[ModuleEvent, ...]:
        return tuple(self._event_history)

    # ------------------------------------------------------------------ #
    # Overridable hooks
    # ------------------------------------------------------------------ #
    def _on_initialize(self, context: ModuleContext) -> None:
        """Optional setup hook."""

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        """Transform or enrich task context before solving."""
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        raise NotImplementedError(f"{self.module_name} must implement _on_solve.")

    def _on_shutdown(self, context: ModuleContext) -> None:
        """Optional teardown hook."""

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_ready(self, *, stage: str) -> None:
        if self._state == ModuleLifecycleState.SHUTDOWN:
            raise ModuleError(f"{self.module_name} is already shut down; cannot {stage}.")
        if self._state == ModuleLifecycleState.CREATED:
            raise ModuleError(f"{self.module_name} has not been initialised; call initialize() before {stage}.")
        if self._context is None:
            raise ModuleError(f"{self.module_name} missing module context during {stage}.")

    def _run_stage(
        self,
        stage: str,
        handler: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Tuple[Any, Optional[ModuleTelemetry]]:
        start_time = time.time()
        telemetry = ModuleTelemetry.started(self.module_name, stage, timestamp=start_time)
        self._emit_event(ModuleEventType.START, stage, status="running", telemetry=telemetry)

        try:
            result = handler(*args, **kwargs)
        except NotImplementedError as exc:
            error_message = f"{self.module_name} has not implemented required handler for stage '{stage}'."
            telemetry = telemetry.complete(status="error", error=str(exc))
            self._emit_event(
                ModuleEventType.ERROR,
                stage,
                status="error",
                telemetry=telemetry,
                details={"error": str(exc), "message": error_message},
            )
            raise ModuleError(error_message) from exc
        except Exception as exc:  # pragma: no cover - re-raised for caller
            telemetry = telemetry.complete(status="error", error=repr(exc))
            self._emit_event(
                ModuleEventType.ERROR,
                stage,
                status="error",
                telemetry=telemetry,
                details={"error": repr(exc)},
            )
            raise
        else:
            telemetry = telemetry.complete(status="completed")
            self._emit_event(ModuleEventType.STOP, stage, status="completed", telemetry=telemetry)
            return result, telemetry

    def _emit_event(
        self,
        event_type: ModuleEventType,
        stage: str,
        *,
        status: str,
        telemetry: Optional[ModuleTelemetry] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        timestamp = telemetry.completed_at if telemetry and event_type != ModuleEventType.START else time.time()
        payload: Dict[str, Any] = {
            "module": self.module_name,
            "stage": stage,
            "status": status,
            "timestamp": timestamp,
        }
        if telemetry:
            payload.update(
                {
                    "duration_s": telemetry.duration_s,
                    "started_at": telemetry.started_at,
                    "completed_at": telemetry.completed_at,
                    "telemetry_status": telemetry.status,
                }
            )
            if telemetry.error:
                payload["error"] = telemetry.error
        if details:
            payload.update(details)

        event = ModuleEvent(
            module=self.module_name,
            stage=stage,
            event_type=event_type,
            status=status,
            timestamp=timestamp,
            payload=payload,
        )
        self._event_history.append(event)

        logger = self._logger or LOGGER
        message = f"{self.module_name}::{stage} -> {status}"
        if event_type == ModuleEventType.ERROR:
            logger.error(message, extra={"module_event": payload})
        else:
            logger.info(message, extra={"module_event": payload})

        if self._context and self._context.metrics_sink:
            metrics_payload = {
                "event": event_type.value,
                "module": self.module_name,
                "stage": stage,
                "status": status,
                "timestamp": timestamp,
            }
            if telemetry:
                metrics_payload["duration_s"] = telemetry.duration_s
                if telemetry.error:
                    metrics_payload["error"] = telemetry.error
            if details:
                metrics_payload["details"] = details
            try:
                self._context.metrics_sink(metrics_payload)
            except Exception as exc:  # pragma: no cover - telemetry sink failures should not crash modules
                logger.warning("Metrics sink failed for %s: %s", self.module_name, exc)
