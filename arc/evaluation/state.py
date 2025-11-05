from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class RunState:
    """Persists evaluation progress for resumable runs."""

    def __init__(self, path: Path, state: Dict[str, Any]) -> None:
        self.path = Path(path)
        self.state = state
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Factory helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def load_or_create(cls, path: Path, *, metadata: Mapping[str, Any]) -> "RunState":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            instance = cls(path, raw)
            instance._merge_run_metadata(metadata)
            instance._flush()
            return instance

        now = _utc_now()
        run_meta = dict(metadata)
        run_meta.setdefault("status", "running")
        run_meta.setdefault("started_at", now)
        run_meta.setdefault("updated_at", now)
        run_meta.setdefault("completed_tasks", 0)
        run_meta.setdefault("failed_tasks", 0)
        state = {"run": run_meta, "tasks": {}}
        instance = cls(path, state)
        instance._flush()
        return instance

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def is_completed(self, task_id: str) -> bool:
        entry = self.state.get("tasks", {}).get(task_id, {})
        return entry.get("status") == "completed"

    def is_failed(self, task_id: str) -> bool:
        entry = self.state.get("tasks", {}).get(task_id, {})
        return entry.get("status") == "failed"

    def mark_started(self, task_id: str) -> None:
        entry = self._ensure_task_entry(task_id)
        entry["status"] = "in_progress"
        timestamps = entry.setdefault("timestamps", {})
        timestamps.setdefault("started_at", _utc_now())
        self._touch_run()
        self._flush()

    def mark_completed(self, task_id: str, summary: Optional[Mapping[str, Any]] = None) -> None:
        entry = self._ensure_task_entry(task_id)
        entry["status"] = "completed"
        entry.setdefault("timestamps", {})["completed_at"] = _utc_now()
        if summary is not None:
            entry["summary"] = dict(summary)
        self._recalculate_counts()
        self._touch_run()
        self._flush()

    def mark_failed(self, task_id: str, error: str, *, module: Optional[str] = None) -> None:
        entry = self._ensure_task_entry(task_id)
        entry["status"] = "failed"
        failure = entry.setdefault("failure", {})
        failure["error"] = error
        if module:
            failure["module"] = module
        entry.setdefault("timestamps", {})["failed_at"] = _utc_now()
        self._recalculate_counts()
        self._touch_run()
        self._flush()

    def record_module_result(self, task_id: str, module: str, payload: Mapping[str, Any]) -> None:
        entry = self._ensure_task_entry(task_id)
        modules = entry.setdefault("modules", {})
        modules[module] = dict(payload)
        self._touch_run()
        self._flush()

    def record_arbitration(self, task_id: str, payload: Mapping[str, Any]) -> None:
        entry = self._ensure_task_entry(task_id)
        entry["arbitration"] = dict(payload)
        self._touch_run()
        self._flush()

    def task_snapshot(self, task_id: str) -> Dict[str, Any]:
        entry = self.state.get("tasks", {}).get(task_id)
        if entry is None:
            return {}
        return json.loads(json.dumps(entry))

    def mark_halted(self, reason: str) -> None:
        run_meta = self.state.setdefault("run", {})
        run_meta["status"] = f"halted_{reason}"
        run_meta["halt_reason"] = reason
        run_meta["updated_at"] = _utc_now()
        self._flush()

    def summary(self) -> Dict[str, Any]:
        run_meta = dict(self.state.get("run", {}))
        run_meta["tasks_total"] = len(self.state.get("tasks", {}))
        return run_meta

    def flush(self) -> None:
        self._flush()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _ensure_task_entry(self, task_id: str) -> Dict[str, Any]:
        tasks = self.state.setdefault("tasks", {})
        entry = tasks.get(task_id)
        if entry is None:
            entry = {"status": "pending"}
            tasks[task_id] = entry
        return entry

    def _merge_run_metadata(self, metadata: Mapping[str, Any]) -> None:
        run_meta = self.state.setdefault("run", {})
        for key, value in metadata.items():
            run_meta.setdefault(key, value)

    def _touch_run(self) -> None:
        run_meta = self.state.setdefault("run", {})
        run_meta["updated_at"] = _utc_now()

    def _recalculate_counts(self) -> None:
        tasks = self.state.get("tasks", {})
        completed = sum(1 for entry in tasks.values() if entry.get("status") == "completed")
        failed = sum(1 for entry in tasks.values() if entry.get("status") == "failed")
        run_meta = self.state.setdefault("run", {})
        run_meta["completed_tasks"] = completed
        run_meta["failed_tasks"] = failed

    def _flush(self) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2)
        tmp_path.replace(self.path)
