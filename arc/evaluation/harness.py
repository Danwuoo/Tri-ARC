from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence, Tuple

from arc.core import ModuleResult, ModuleSolveStatus, ModuleTelemetry, SolverModule
from arc.core.registry import ModuleRegistry
from arc.data import DatasetLoader, TaskRecord
from arc.evaluation.state import RunState
from arc import logging_utils
from arc.scheduler.core import ModuleBudget, SchedulerCore

LOGGER = logging.getLogger("tri_arc.eval.harness")


class EvaluationHarness:
    """Coordinates scheduler allocations, module execution, and arbitration."""

    def __init__(
        self,
        *,
        config: MutableMapping[str, Any],
        run_id: str,
        split: str,
        run_dir: Path,
        dataset_loader: DatasetLoader,
        metrics_path: Path,
        config_fingerprint: Optional[str] = None,
        scheduler: Optional[SchedulerCore] = None,
        registry: Optional[ModuleRegistry] = None,
        logger: Optional[logging.Logger] = None,
        time_limit_hours: Optional[float] = None,
        force_enable: Optional[Sequence[str]] = None,
        force_disable: Optional[Sequence[str]] = None,
        use_mocks: Optional[Sequence[str]] = None,
    ) -> None:
        self.config = config
        self.run_id = run_id
        self.split = split
        self.run_dir = Path(run_dir)
        self.tasks_dir = self.run_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or LOGGER
        self.dataset_loader = dataset_loader
        self.metrics_file = Path(metrics_path)
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_fingerprint = config_fingerprint
        self.shared_cache: MutableMapping[str, Any] = {}
        self.time_limit_hours = float(time_limit_hours) if time_limit_hours is not None else None
        self.run_started_at = time.time()

        self._metrics_context = {
            "run_id": self.run_id,
            "split": self.split,
            "config_fingerprint": self.config_fingerprint,
        }

        self._module_metrics_sink = self._build_metrics_sink()
        self.scheduler = scheduler or SchedulerCore(
            config,
            metrics_sink=self._module_metrics_sink,
            logger=logging.getLogger("tri_arc.scheduler"),
        )
        self.registry = registry or ModuleRegistry(
            config,
            run_id=self.run_id,
            shared_cache=self.shared_cache,
            metrics_sink=self._module_metrics_sink,
            logger=logging.getLogger("tri_arc.modules"),
            force_enable=force_enable,
            force_disable=force_disable,
            use_mocks=use_mocks,
        )
        self.registry.bootstrap()

        run_metadata = {
            "run_id": self.run_id,
            "split": self.split,
            "config_fingerprint": self.config_fingerprint,
            "time_limit_hours": self.time_limit_hours,
        }
        self.run_state = RunState.load_or_create(self.run_dir / "run_state.json", metadata=run_metadata)

        self._summary: Dict[str, Any] = {
            "tasks_total": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_skipped": 0,
            "modules": {},
        }

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(
        self,
        *,
        limit: Optional[int] = None,
        task_ids: Optional[Sequence[str]] = None,
        exclude_task_ids: Optional[Sequence[str]] = None,
        resume: bool = True,
        force_feature_refresh: bool = False,
    ) -> Dict[str, Any]:
        start_time = time.time()
        processed = 0
        skipped = 0
        completed = 0
        failed = 0
        active_modules = self.registry.active_modules()
        arbitrator = active_modules.get("arbitrator")
        if arbitrator is None:
            raise RuntimeError("Arbitrator module must be enabled for evaluation runs.")

        solver_modules = {name: module for name, module in active_modules.items() if name != "arbitrator"}

        for record in self.dataset_loader.iter_split(
            self.split,
            limit=limit,
            task_ids=task_ids,
            exclude_task_ids=exclude_task_ids,
        ):
            task_id = record.task_id
            if resume and self.run_state.is_completed(task_id):
                skipped += 1
                continue
            if self._time_budget_exhausted(start_time):
                self.logger.warning("Halting evaluation: reached time limit of %.2f hours.", self.time_limit_hours)
                self.run_state.mark_halted("time_limit")
                break

            processed += 1
            try:
                task_payload = self._prepare_task_payload(record)
            except Exception as exc:
                self.logger.exception("Failed to prepare payload for %s: %s", task_id, exc)
                self.run_state.mark_failed(task_id, error=f"payload_error: {exc!r}")
                failed += 1
                continue

            self.logger.info("Evaluating task %s (%s)", task_id, record.path)
            self.run_state.mark_started(task_id)
            scheduled = self.scheduler.schedule([task_payload], force_refresh=force_feature_refresh)
            if not scheduled:
                self.logger.error("Scheduler produced no allocations for task %s.", task_id)
                self.run_state.mark_failed(task_id, error="scheduler_allocation_empty")
                failed += 1
                continue
            scheduled_task = scheduled[0]

            self._execute_modules(
                task_payload,
                scheduled_task.allocations,
                solver_modules,
            )

            arbitration_success = self._execute_arbitrator(task_payload, arbitrator)
            if arbitration_success:
                completed += 1
            else:
                failed += 1

            self._persist_task_artifact(task_id)

        self._summary.update(
            {
                "tasks_total": processed,
                "tasks_skipped": skipped,
                "tasks_completed": completed,
                "tasks_failed": failed,
                "elapsed_s": time.time() - start_time,
            }
        )
        self._summary["run_state"] = self.run_state.summary()
        return dict(self._summary)

    def shutdown(self) -> None:
        try:
            self.registry.shutdown()
        finally:
            # Persist run state one final time for completeness.
            self.run_state.flush()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _prepare_task_payload(self, record: TaskRecord) -> Dict[str, Any]:
        payload = record.to_payload()
        metadata = dict(payload.get("metadata", {}))
        run_context = metadata.setdefault("run_context", {})
        run_context.setdefault("run_id", self.run_id)
        run_context.setdefault("split", self.split)
        if self.config_fingerprint:
            run_context.setdefault("config_fingerprint", self.config_fingerprint)
        run_context.setdefault("run_started_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.run_started_at)))
        metadata.setdefault("scheduler_history", metadata.get("scheduler_history", {}))
        payload["metadata"] = metadata
        return payload

    def _execute_modules(
        self,
        task_payload: Dict[str, Any],
        allocations: Mapping[str, ModuleBudget],
        solver_modules: Mapping[str, SolverModule],
    ) -> bool:
        task_id = str(task_payload.get("task_id"))
        overall_success = True
        ordered_allocations = sorted(
            allocations.items(),
            key=lambda item: (item[1].start_delay_s, -item[1].priority),
        )

        for module_name, budget in ordered_allocations:
            module = solver_modules.get(module_name)
            if module is None:
                self.logger.debug("Module %s not active; skipping for task %s.", module_name, task_id)
                continue
            self.logger.debug(
                "Running module %s for task %s with soft_limit=%.1fs hard_limit=%.1fs priority=%.2f",
                module_name,
                task_id,
                budget.soft_limit_s,
                budget.hard_limit_s,
                budget.priority,
            )
            module_payload, success = self._run_module(module_name, module, task_payload, budget)
            overall_success = overall_success and success
            self.run_state.record_module_result(task_id, module_name, module_payload)

        return overall_success

    def _run_module(
        self,
        module_name: str,
        module: SolverModule,
        task_payload: Mapping[str, Any],
        budget: ModuleBudget,
    ) -> Tuple[Dict[str, Any], bool]:
        task_id = str(task_payload.get("task_id"))
        payload_copy = copy.deepcopy(task_payload)
        start = time.time()
        runtime_s = 0.0
        status = ModuleSolveStatus.ERROR
        result_payload: Dict[str, Any]
        success = False
        try:
            prepared = module.prepare_task(payload_copy)
            result: ModuleResult = module.solve(prepared)
            runtime_s = max(0.0, time.time() - start)
            status = result.status
            result_payload = {
                "status": result.status.value,
                "summary": result.summary,
                "candidates": result.candidates,
                "telemetry": _serialise_telemetry(result.telemetry),
                "elapsed_s": runtime_s,
                "budget_s": budget.soft_limit_s,
                "hard_budget_s": budget.hard_limit_s,
                "priority": budget.priority,
            }
            success = status == ModuleSolveStatus.SUCCESS
        except Exception as exc:
            runtime_s = max(0.0, time.time() - start)
            self.logger.exception("Module %s failed on task %s: %s", module_name, task_id, exc)
            result_payload = {
                "status": "error",
                "error": repr(exc),
                "elapsed_s": runtime_s,
                "budget_s": budget.soft_limit_s,
                "hard_budget_s": budget.hard_limit_s,
                "priority": budget.priority,
            }
            success = False
            self._emit_metric(
                {
                    "event": "module_error",
                    "module": module_name,
                    "task_id": task_id,
                    "error": repr(exc),
                    "elapsed_s": runtime_s,
                }
            )

        try:
            self.scheduler.record_feedback(
                task_id,
                module_name,
                success=success,
                runtime_s=runtime_s,
                budget_s=budget.soft_limit_s,
            )
        except Exception as exc:
            self.logger.debug("Failed to record scheduler feedback for %s: %s", module_name, exc)

        self._emit_metric(
            {
                "event": "module_complete",
                "module": module_name,
                "task_id": task_id,
                "status": status.value if isinstance(status, ModuleSolveStatus) else status,
                "success": success,
                "elapsed_s": runtime_s,
                "budget_s": budget.soft_limit_s,
                "hard_budget_s": budget.hard_limit_s,
            }
        )
        self._summary.setdefault("modules", {}).setdefault(module_name, {"success": 0, "attempts": 0})
        module_summary = self._summary["modules"][module_name]
        module_summary["attempts"] += 1
        if success:
            module_summary["success"] += 1
        return result_payload, success

    def _execute_arbitrator(self, task_payload: Dict[str, Any], arbitrator: SolverModule) -> bool:
        task_id = str(task_payload.get("task_id"))
        payload_copy = copy.deepcopy(task_payload)
        start = time.time()
        runtime_s = 0.0
        try:
            prepared = arbitrator.prepare_task(payload_copy)
            result = arbitrator.solve(prepared)
            runtime_s = max(0.0, time.time() - start)
            summary = {
                "status": result.status.value,
                "summary": result.summary,
                "elapsed_s": runtime_s,
                "candidates": result.candidates,
                "telemetry": _serialise_telemetry(result.telemetry),
            }
            self.run_state.record_arbitration(task_id, summary)
            if result.status == ModuleSolveStatus.SUCCESS:
                self.run_state.mark_completed(task_id, summary=result.summary)
                self._emit_metric(
                    {
                        "event": "arbitration_success",
                        "task_id": task_id,
                        "elapsed_s": runtime_s,
                        "answers": len(result.summary.get("answers", [])),
                    }
                )
                self._cleanup_task_cache(task_id)
                return True
            self.run_state.mark_failed(task_id, error="arbitration_failed", module="arbitrator")
            self._emit_metric(
                {
                    "event": "arbitration_failed",
                    "task_id": task_id,
                    "elapsed_s": runtime_s,
                    "reason": result.summary.get("rationale"),
                }
            )
            self._cleanup_task_cache(task_id)
            return False
        except Exception as exc:
            runtime_s = max(0.0, time.time() - start)
            self.logger.exception("Arbitrator failed on task %s: %s", task_id, exc)
            self.run_state.mark_failed(task_id, error=repr(exc), module="arbitrator")
            self._emit_metric(
                {
                    "event": "arbitration_error",
                    "task_id": task_id,
                    "error": repr(exc),
                    "elapsed_s": runtime_s,
                }
            )
            self._cleanup_task_cache(task_id)
            return False

    def _cleanup_task_cache(self, task_id: str) -> None:
        for namespace in self.shared_cache.values():
            if isinstance(namespace, MutableMapping):
                namespace.pop(task_id, None)

    def _persist_task_artifact(self, task_id: str) -> None:
        snapshot = self.run_state.task_snapshot(task_id)
        if not snapshot:
            return
        safe_task_id = task_id.replace("/", "__")
        path = self.tasks_dir / f"{safe_task_id}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2)

    def _build_metrics_sink(self):
        context = dict(self._metrics_context)
        metrics_path = self.metrics_file

        def _sink(payload: Mapping[str, Any]) -> None:
            record = dict(context)
            record.update(payload)
            record.setdefault("timestamp", dt.datetime.now(dt.timezone.utc).isoformat())
            logging_utils.append_metric(metrics_path, record)

        return _sink

    def _emit_metric(self, payload: Mapping[str, Any]) -> None:
        self._module_metrics_sink(payload)

    def _time_budget_exhausted(self, start_time: float) -> bool:
        if self.time_limit_hours is None:
            return False
        elapsed_hours = (time.time() - start_time) / 3600.0
        return elapsed_hours >= max(0.0, self.time_limit_hours)


def _serialise_telemetry(telemetry: Optional[ModuleTelemetry]) -> Optional[Dict[str, Any]]:
    if telemetry is None:
        return None
    payload = {
        "module_name": telemetry.module_name,
        "stage": telemetry.stage,
        "status": telemetry.status,
        "started_at": telemetry.started_at,
        "completed_at": telemetry.completed_at,
        "duration_s": telemetry.duration_s,
        "error": telemetry.error,
    }
    if telemetry.extras:
        payload["extras"] = _recursive_serialise(telemetry.extras)
    return payload


def _recursive_serialise(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _recursive_serialise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_recursive_serialise(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
