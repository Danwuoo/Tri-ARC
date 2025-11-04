from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, TYPE_CHECKING

from arc.symbolic.dsl.types import ExecutionState, Stage

if TYPE_CHECKING:  # pragma: no cover
    from .primitives import PrimitiveResult


@dataclass(frozen=True)
class RuntimePaths:
    metrics_path: Path
    runtime_log_path: Path


@dataclass(frozen=True)
class InterpreterConfig:
    seed: int
    log_root: Path
    metrics_path: Path
    runtime_log_path: Path
    emit_metrics: bool = True
    enable_logging: bool = True

    @classmethod
    def from_config_dict(cls, config: Dict[str, Any]) -> "InterpreterConfig":
        global_cfg = config.get("global", {})
        logging_cfg = config.get("logging", {})

        log_root = Path(global_cfg.get("log_root", "logs")).resolve()
        metrics_name = logging_cfg.get("metrics_file", "metrics.jsonl")
        runtime_name = logging_cfg.get("runtime_log", "runtime.log")

        metrics_path = log_root / metrics_name
        runtime_log_path = log_root / runtime_name

        emit_metrics = bool(logging_cfg.get("emit_metrics", True))
        enable_logging = bool(logging_cfg.get("enable_runtime_log", True))

        seed = int(global_cfg.get("seed", 1337))

        return cls(
            seed=seed,
            log_root=log_root,
            metrics_path=metrics_path,
            runtime_log_path=runtime_log_path,
            emit_metrics=emit_metrics,
            enable_logging=enable_logging,
        )


@dataclass
class PrimitiveContext:
    state: ExecutionState
    config: InterpreterConfig
    stage_index: int
    operator: str
    path: Tuple[int, ...]
    logger: Logger
    metadata: Optional[Dict[str, Any]] = None
    run_stage: Optional[Callable[[Stage, ExecutionState, Tuple[int, ...]], "PrimitiveResult"]] = None

    def with_state(self, state: ExecutionState) -> "PrimitiveContext":
        return PrimitiveContext(
            state=state,
            config=self.config,
            stage_index=self.stage_index,
            operator=self.operator,
            path=self.path,
            logger=self.logger,
            metadata=dict(self.metadata or {}),
            run_stage=self.run_stage,
        )
