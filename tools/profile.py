#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import time
from pathlib import Path
from contextlib import nullcontext
from typing import Any, Dict, Iterable, List, Optional, Sequence

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arc.common.profiling import capture_performance_snapshot, summarise_snapshot_delta
from arc.config import DEFAULT_CONFIG_PATH, load_config
from arc.core import ModuleRegistry
from arc.data import load_sample_task


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile Tri-ARC modules and capture baseline metrics.")
    parser.add_argument("--module", choices=["symbolic", "ttt", "llm", "arbitrator"], required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to configuration YAML.")
    parser.add_argument(
        "--variant",
        choices=["default", "no_heuristics", "no_cache", "no_heuristics_no_cache"],
        default="default",
        help="Configuration variant to apply for the profiling run.",
    )
    parser.add_argument(
        "--notes-file",
        type=Path,
        default=Path("reports/perf_notes.md"),
        help="Path to append high-level profiling notes.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("profiles"),
        help="Directory for profiler artefacts.",
    )
    parser.add_argument(
        "--torch-profiler",
        action="store_true",
        help="Enable PyTorch profiler if torch is available.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Initialise modules but skip execution. Useful for testing configuration changes.",
    )
    return parser.parse_args()


def _clone_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(config)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _enumerate_modules(config: Dict[str, Any]) -> Iterable[str]:
    modules_cfg = config.get("modules", {})
    if isinstance(modules_cfg, dict):
        return modules_cfg.keys()
    return ()


def _apply_variant(config: Dict[str, Any], module: str, variant: str) -> Dict[str, Any]:
    updated = _clone_config(config)
    module_cfg = updated.setdefault(module, {})

    if variant in {"no_heuristics", "no_heuristics_no_cache"} and module == "symbolic":
        heuristics_cfg = module_cfg.setdefault("heuristics", {})

        rule_based = heuristics_cfg.setdefault("rule_based", {})
        rule_based["enabled"] = False

        neural_cfg = heuristics_cfg.setdefault("neural", {})
        neural_cfg["enabled"] = False

        modules_cfg = updated.setdefault("modules", {}).setdefault("symbolic", {})
        modules_cfg["warm_start"] = False

    if variant in {"no_cache", "no_heuristics_no_cache"}:
        scheduler_cfg = updated.setdefault("scheduler", {})
        feature_cache = scheduler_cfg.setdefault("feature_cache", {})
        feature_cache["max_items"] = 0
        feature_cache["ttl_seconds"] = 0

        descriptor_cache = scheduler_cfg.setdefault("descriptor_cache", {})
        descriptor_cache["max_items"] = 0

        warm_cache = scheduler_cfg.setdefault("warm_start_cache", {})
        warm_cache["max_items"] = 0

        modules_cfg = updated.setdefault("modules", {}).setdefault(module, {})
        modules_cfg["warm_start"] = False

    return updated


def _disable_other_modules(config: Dict[str, Any], active_module: str) -> Sequence[str]:
    disabled = []
    modules_cfg = config.setdefault("modules", {})
    for name in list(modules_cfg.keys()):
        if name == active_module:
            continue
        entry = modules_cfg.setdefault(name, {})
        entry["enabled"] = False
        disabled.append(name)
    return disabled


def _serialise_metrics(metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    serialised: List[Dict[str, Any]] = []
    for entry in metrics:
        serialised.append(entry)
    return serialised


def _export_torch_profile(module: str, variant: str, output_dir: Path, profiler: Any, timestamp: str) -> Optional[Path]:
    if profiler is None:
        return None
    trace_path = output_dir / f"torch_profile_{module}_{variant}_{timestamp}.json"
    try:
        profiler.export_chrome_trace(str(trace_path))
    except Exception:
        return None
    return trace_path


def _profiler_context(enabled: bool) -> Any:
    if not enabled:
        return nullcontext()
    try:
        import torch
    except Exception:
        return nullcontext()

    try:
        activities = [torch.profiler.ProfilerActivity.CPU]
        if torch.cuda.is_available():
            activities.append(torch.profiler.ProfilerActivity.CUDA)
        return torch.profiler.profile(
            activities=activities,
            record_shapes=True,
            profile_memory=True,
            with_stack=True,
        )
    except Exception:
        return nullcontext()


def main() -> int:
    args = _parse_args()
    config = load_config(args.config)
    mutated_config = _apply_variant(config, args.module, args.variant)
    disabled_modules = _disable_other_modules(mutated_config, args.module)

    _ensure_dir(args.output_dir)
    _ensure_dir(args.notes_file.parent)

    data_root = Path(mutated_config.get("global", {}).get("data_root", "data/arcagi2"))
    sample_task = load_sample_task(data_root)
    if sample_task is None:
        raise SystemExit(f"No sample ARC task available under {data_root}.")

    run_id = f"profile-{args.module}-{args.variant}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    metrics_buffer: List[Dict[str, Any]] = []

    registry = ModuleRegistry(
        mutated_config,
        run_id=run_id,
        shared_cache={},
        metrics_sink=metrics_buffer.append,
        logger=None,
        force_enable=[args.module],
        force_disable=disabled_modules,
    )
    registry.bootstrap()

    try:
        module = registry.get(args.module)
    except KeyError as exc:  # pragma: no cover - guard rails for misconfiguration
        registry.shutdown()
        raise SystemExit(f"Module {args.module} did not initialise: {exc}") from exc

    task_payload = {
        "task_id": sample_task.get("task_id", "profile_task"),
        "train_examples": [
            {"input": entry.get("input"), "output": entry.get("output")}
            for entry in sample_task.get("train", [])
        ],
        "test_examples": [
            {"input": entry.get("input")}
            for entry in sample_task.get("test", [])
        ],
        "metadata": {"source": "profile_sample"},
    }

    notes: List[str] = []
    prepared = module.prepare_task(task_payload)
    perf_before = capture_performance_snapshot()
    solve_result: Optional[Any] = None
    elapsed_s: float = 0.0
    profiler_trace: Optional[Path] = None

    if args.dry_run:
        notes.append("Dry run requested; skipping module.solve call.")
    else:
        with _profiler_context(args.torch_profiler) as profiler:
            start = time.perf_counter()
            try:
                solve_result = module.solve(prepared)
            finally:
                elapsed_s = time.perf_counter() - start
        if profiler:
            trace_stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
            profiler_trace = _export_torch_profile(args.module, args.variant, args.output_dir, profiler, trace_stamp)

    perf_after = capture_performance_snapshot()

    registry.shutdown()

    perf_delta = summarise_snapshot_delta(perf_before, perf_after)

    result_summary: Dict[str, Any] = {
        "status": getattr(getattr(solve_result, "status", None), "value", None) if solve_result else None,
        "summary": getattr(solve_result, "summary", None) if solve_result else None,
    }
    if solve_result and hasattr(solve_result, "telemetry") and solve_result.telemetry:
        result_summary["telemetry"] = solve_result.telemetry.extras

    timestamp = dt.datetime.now(dt.timezone.utc)
    profile_payload = {
        "timestamp": timestamp.isoformat(),
        "module": args.module,
        "variant": args.variant,
        "run_id": run_id,
        "elapsed_s": round(elapsed_s, 4),
        "perf_delta": perf_delta,
        "metrics_events": _serialise_metrics(metrics_buffer),
        "result": result_summary,
        "profiler_trace": str(profiler_trace) if profiler_trace else None,
        "notes": notes,
        "disabled_modules": list(disabled_modules),
    }

    _ensure_dir(args.output_dir)
    output_path = args.output_dir / f"profile_{args.module}_{args.variant}_{timestamp.strftime('%Y%m%dT%H%M%S')}.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(profile_payload, handle, indent=2, default=str)

    _ensure_dir(args.notes_file.parent)
    with args.notes_file.open("a", encoding="utf-8") as handle:
        handle.write(
            f"- {timestamp.strftime('%Y-%m-%d %H:%M:%S')}Z | module={args.module} variant={args.variant} "
            f"elapsed={profile_payload['elapsed_s']}s rss_delta={perf_delta.get('cpu', {}).get('rss_delta_mb')}MB\n"
        )

    print(f"Profile artefact written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
