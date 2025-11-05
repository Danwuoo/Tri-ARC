from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from arc.config import load_config
from arc.scheduler import SchedulerCore

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "scheduler" / "features"


def _load_task(name: str) -> Dict[str, Any]:
    payload = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return payload["task"]


def _configure_scheduler(tmp_path: Path, *, halt_threshold: float = 0.95) -> Dict[str, Any]:
    cfg = copy.deepcopy(load_config())
    scheduler_cfg = cfg.setdefault("scheduler", {})
    feature_cache_cfg = scheduler_cfg.setdefault("feature_cache", {})
    feature_cache_cfg["backing_store"] = str(tmp_path / "features_cache.jsonl")
    scheduler_log_cfg = scheduler_cfg.setdefault("logging", {})
    scheduler_log_cfg["ingest_log"] = str(tmp_path / "ingest.log")
    diagnostics_cfg = scheduler_cfg.setdefault("diagnostics", {})
    diagnostics_cfg["snapshot_dir"] = str(tmp_path / "reports")
    scheduler_cfg["halt_threshold"] = halt_threshold

    descriptor_cfg = scheduler_cfg.setdefault("descriptor_cache", {})
    descriptor_cfg["max_items"] = 8
    warm_cache_cfg = scheduler_cfg.setdefault("warm_start_cache", {})
    warm_cache_cfg["max_items"] = 4

    global_cfg = cfg.setdefault("global", {})
    global_cfg["log_root"] = str(tmp_path / "logs")
    return cfg


def test_scheduler_prefers_symbolic_for_symmetry(tmp_path: Path) -> None:
    config = _configure_scheduler(tmp_path)
    core = SchedulerCore(config)
    task = _load_task("symmetry_task")

    scheduled = core.schedule([task])
    assert len(scheduled) == 1
    entry = scheduled[0]

    assert "small_symmetry" in entry.matched_rules
    allocations = entry.allocations
    assert allocations["symbolic"].priority > allocations["ttt"].priority > allocations["llm"].priority
    assert allocations["symbolic"].start_delay_s == pytest.approx(0.0)
    assert allocations["ttt"].start_delay_s == pytest.approx(5.0)
    assert allocations["llm"].start_delay_s >= allocations["ttt"].start_delay_s

    cache_stats = core.feature_cache.stats()
    assert cache_stats["size"] == 1


def test_feedback_adjusts_module_weights(tmp_path: Path) -> None:
    config = _configure_scheduler(tmp_path)
    core = SchedulerCore(config)
    task = _load_task("symmetry_task")

    baseline = core.schedule([task])[0]
    baseline_weight = baseline.allocations["symbolic"].weight

    for _ in range(3):
        core.record_feedback(task["task_id"], "symbolic", success=True, runtime_s=90.0, budget_s=90.0)

    adjusted = core.schedule([task])[0]
    assert adjusted.allocations["symbolic"].weight > baseline_weight


def test_scheduler_halts_when_risk_threshold_triggered(tmp_path: Path) -> None:
    config = _configure_scheduler(tmp_path, halt_threshold=0.0)
    core = SchedulerCore(config)
    task = _load_task("symmetry_task")

    scheduled = core.schedule([task])
    assert scheduled == []

    cache_entry = core.feature_cache.get("symmetry-task")
    assert cache_entry is not None
