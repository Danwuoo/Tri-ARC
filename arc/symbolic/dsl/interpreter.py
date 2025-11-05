from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from arc.config import load_config
from arc.logging_utils import append_metric
from arc.scheduler.cache import LRUCache
from arc.symbolic.dsl.types import ExecutionState, ExecutionTrace, Grid, Program, Stage, StageResult

from arc.common.grid import ensure_palette, normalise_grid
from .runtime.context import InterpreterConfig, PrimitiveContext
from .runtime.evaluation import EvaluationContext, evaluate_expression
from .runtime.errors import InterpreterFailure
from .runtime.primitives import PrimitiveResult, PrimitiveSpec, build_registry

LOGGER_NAME = "arc.symbolic.dsl.interpreter"


class DSLInterpreter:
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        registry: Optional[Dict[str, PrimitiveSpec]] = None,
    ) -> None:
        raw_config = config or load_config()
        self._raw_config = raw_config
        self.config = InterpreterConfig.from_config_dict(raw_config)
        self.registry: Dict[str, PrimitiveSpec] = dict(registry or build_registry())
        self.logger = logging.getLogger(LOGGER_NAME)
        self.metrics_path = self.config.metrics_path
        self.runtime_log_path = self.config.runtime_log_path
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_log_path.parent.mkdir(parents=True, exist_ok=True)

        cache_cfg = raw_config.get("symbolic", {}).get("interpreter_cache", {}) or {}
        self._cache_enabled = bool(cache_cfg.get("enabled", True))
        self._cache_namespace = str(cache_cfg.get("namespace", "dsl_interpreter"))
        self._result_cache: Optional[LRUCache] = None
        self._cache_hits = 0
        self._cache_misses = 0
        if self._cache_enabled:
            max_items = int(cache_cfg.get("max_items", 512))
            ttl_seconds = cache_cfg.get("ttl_seconds")
            ttl_value = float(ttl_seconds) if ttl_seconds is not None else None
            self._result_cache = LRUCache(max_items, ttl_seconds=ttl_value)

    def run(
        self,
        program: Program,
        grid: Any,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> ExecutionTrace:
        issues = validate_program(program, self.registry)
        if issues:
            raise InterpreterFailure.validation(
                "Program failed static validation.",
                details={"issues": issues},
            )

        base_metadata = dict(metadata or {})
        if run_id is not None:
            base_metadata["run_id"] = run_id

        initial_grid = normalise_grid(grid).copy()
        ensure_palette(initial_grid)

        cache_key: Optional[str] = None
        if self._result_cache is not None:
            cache_key = self._build_cache_key(program, initial_grid)
            cached_payload = self._result_cache.get(cache_key)
            if cached_payload is not None:
                self._cache_hits += 1
                trace = self._reconstruct_trace(initial_grid, cached_payload)
                self._record_cache_event("hit", cache_key, base_metadata, extra={"stage_count": len(program)})
                return trace
        state = self._make_initial_state(initial_grid)
        trace = ExecutionTrace(initial_grid=initial_grid.copy())

        for index, stage in enumerate(program):
            path = (index,)
            result, stage_result = self._run_stage_internal(stage, state, path, base_metadata, nested=False)
            state = result.state
            trace.append(stage_result)

        trace.final_state = state  # type: ignore[attr-defined]

        if self._result_cache is not None and cache_key is not None:
            payload = {
                "grid": trace.final_grid.to_list(),
                "stage_count": len(trace),
            }
            self._result_cache.set(cache_key, payload)
            self._cache_misses += 1
            self._record_cache_event(
                "miss",
                cache_key,
                base_metadata,
                extra={"stage_count": len(trace)},
            )

        return trace

    def _make_initial_state(self, grid: Grid) -> ExecutionState:
        env: Dict[str, Any] = {
            "current_grid": grid,
            "last_value": None,
            "objects": [],
            "object_metadata": [],
            "last_grid": None,
        }
        return ExecutionState(
            grid=grid,
            env=env,
            object_stack=[],
            last_value=None,
            last_grid=None,
            background_colour=None,
        )

    def _run_stage_internal(
        self,
        stage: Stage,
        state: ExecutionState,
        path: Tuple[int, ...],
        base_metadata: Dict[str, Any],
        *,
        nested: bool,
    ) -> Tuple[PrimitiveResult, StageResult]:
        spec = self.registry.get(stage.operator)
        if spec is None:
            raise InterpreterFailure.validation(
                f"Primitive '{stage.operator}' is not registered.",
                details={"operator": stage.operator, "stage_path": path},
            )

        eval_ctx = EvaluationContext(
            state=state,
            config=self.config,
            stage_index=path[-1],
            operator=stage.operator,
        )
        evaluated_args = tuple(evaluate_expression(arg, eval_ctx) for arg in stage.arguments)

        primitive_ctx = PrimitiveContext(
            state=state,
            config=self.config,
            stage_index=path[-1],
            operator=stage.operator,
            path=path,
            logger=self.logger,
            metadata=base_metadata,
            run_stage=lambda sub_stage, sub_state, sub_path: self._run_stage_internal(
                sub_stage,
                sub_state,
                sub_path,
                base_metadata,
                nested=True,
            )[0],
        )

        bound_args = spec.bind_arguments(evaluated_args, primitive_ctx)

        start = time.perf_counter()
        try:
            result = spec.implementation(primitive_ctx, bound_args)
        except InterpreterFailure:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard
            raise InterpreterFailure(
                message=f"Primitive '{stage.operator}' raised an unexpected exception.",
                code="PRIMITIVE_ERROR",
                details={"operator": stage.operator, "stage_path": path},
                cause=exc,
            ) from exc
        duration_ms = (time.perf_counter() - start) * 1000.0

        ensure_palette(result.state.grid)

        stage_result = StageResult(
            stage=stage,
            value=result.value,
            grid=result.state.grid,
            duration_ms=duration_ms,
            metadata=dict(result.metadata or {}),
        )

        self._emit_metric(stage, path, duration_ms, spec, result, base_metadata)
        self._log_stage(path, stage, duration_ms, nested=nested)

        return result, stage_result

    def _build_cache_key(self, program: Program, initial_grid: Grid) -> str:
        stage_repr = "|".join(f"{stage.operator}:{repr(stage.arguments)}" for stage in program)
        grid_repr = json.dumps(initial_grid.to_list())
        payload = f"{stage_repr}#{grid_repr}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _reconstruct_trace(self, initial_grid: Grid, payload: Dict[str, Any]) -> ExecutionTrace:
        trace = ExecutionTrace(initial_grid=initial_grid.copy())
        raw_grid = payload.get("grid")
        final_grid = Grid.from_list(raw_grid) if isinstance(raw_grid, list) else initial_grid.copy()
        stage_count = int(payload.get("stage_count", 0) or 0)
        stage_result = StageResult(
            stage=Stage(operator="cache_replay", arguments=tuple()),
            value=None,
            grid=final_grid.copy(),
            duration_ms=0.0,
            metadata={"cache": "interpreter_hit", "stage_count": stage_count},
        )
        trace.append(stage_result)
        trace.final_state = self._make_initial_state(final_grid.copy())
        return trace

    def _record_cache_event(
        self,
        kind: str,
        cache_key: str,
        metadata: Dict[str, Any],
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.config.emit_metrics:
            return
        payload: Dict[str, Any] = {
            "event": "dsl_cache",
            "cache": "interpreter",
            "kind": kind,
            "cache_key": cache_key,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        if "task_id" in metadata:
            payload["task_id"] = metadata["task_id"]
        if self._result_cache is not None:
            stats = self._result_cache.stats()
            payload["hit_rate"] = stats.get("hit_rate")
            payload["size"] = stats.get("size")
            payload["capacity"] = stats.get("capacity")
        if extra:
            payload.update(extra)
        append_metric(self.metrics_path, payload)

    def _emit_metric(
        self,
        stage: Stage,
        path: Tuple[int, ...],
        duration_ms: float,
        spec: PrimitiveSpec,
        result: PrimitiveResult,
        metadata: Dict[str, Any],
    ) -> None:
        if not self.config.emit_metrics:
            return
        payload: Dict[str, Any] = {
            "event": "dsl_stage",
            "operator": stage.operator,
            "stage_path": ".".join(str(part) for part in path),
            "duration_ms": duration_ms,
            "result_type": spec.result_type,
        }
        run_id = metadata.get("run_id")
        if run_id is not None:
            payload["run_id"] = run_id
        if result.metadata:
            payload["metadata"] = result.metadata
        if spec.result_type in {"int", "colour", "bool"}:
            payload["value"] = result.value
        append_metric(self.metrics_path, payload)

    def _log_stage(self, path: Tuple[int, ...], stage: Stage, duration_ms: float, *, nested: bool) -> None:
        if not self.config.enable_logging:
            return
        label = ".".join(str(part) for part in path)
        if nested:
            self.logger.debug("DSL stage %s | %s | %.3f ms", label, stage.operator, duration_ms)
        else:
            self.logger.info("DSL stage %s | %s | %.3f ms", label, stage.operator, duration_ms)


def validate_program(program: Program, registry: Optional[Dict[str, PrimitiveSpec]] = None) -> List[str]:
    reg = registry or build_registry()
    errors: List[str] = []
    for index, stage in enumerate(program):
        spec = reg.get(stage.operator)
        if spec is None:
            errors.append(f"Stage {index}: unknown operator '{stage.operator}'.")
            continue
        arg_count = len(stage.arguments)
        required = sum(1 for arg in spec.arguments if arg.required and not arg.variadic)
        variadic_args = [arg for arg in spec.arguments if arg.variadic]
        if variadic_args:
            # Variadic arguments contribute at most one required slot but have no upper bound.
            required += sum(1 for arg in variadic_args if arg.required)
            max_args = float("inf")
        else:
            max_args = len(spec.arguments)
        if arg_count < required:
            errors.append(
                f"Stage {index}: operator '{stage.operator}' expects at least {required} arguments, received {arg_count}."
            )
        if arg_count > max_args:
            errors.append(
                f"Stage {index}: operator '{stage.operator}' expects at most {max_args} arguments, received {arg_count}."
            )
    return errors

