from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ModuleSolveStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class ModuleTelemetry:
    module_name: str
    stage: str
    status: str
    started_at: float
    completed_at: float
    duration_s: float
    error: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def started(cls, module_name: str, stage: str, *, timestamp: Optional[float] = None) -> ModuleTelemetry:
        now = time.time() if timestamp is None else timestamp
        return cls(
            module_name=module_name,
            stage=stage,
            status="running",
            started_at=now,
            completed_at=now,
            duration_s=0.0,
        )

    def complete(
        self,
        status: str,
        *,
        error: Optional[str] = None,
        timestamp: Optional[float] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> ModuleTelemetry:
        end_time = time.time() if timestamp is None else timestamp
        payload = dict(self.extras)
        if extras:
            payload.update(extras)
        return ModuleTelemetry(
            module_name=self.module_name,
            stage=self.stage,
            status=status,
            started_at=self.started_at,
            completed_at=end_time,
            duration_s=max(0.0, end_time - self.started_at),
            error=error,
            extras=payload,
        )


@dataclass
class ModuleResult:
    task_id: str
    status: ModuleSolveStatus
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    telemetry: Optional[ModuleTelemetry] = None
