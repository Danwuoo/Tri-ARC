#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence, Set

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arc import logging_utils
from arc.config import DEFAULT_CONFIG_PATH, load_config
from arc.data import DatasetLoader
from arc.evaluation import (
    EvaluationHarness,
    append_history,
    collect_run_metrics,
    find_previous_entry,
    package_run_artifacts,
    write_delta_report,
    write_run_manifest,
    write_run_summary,
    write_history_markdown,
)

REPORTS_DIR = REPO_ROOT / "reports"


def set_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tri-ARC evaluation harness entrypoint.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Base configuration YAML path.")
    parser.add_argument("--preset", type=str, help="Evaluation preset name under configs/eval (e.g., smoke, evaluation).")
    parser.add_argument("--split", choices=["train", "evaluation", "smoke"], default="evaluation", help="Dataset split to evaluate.")
    parser.add_argument("--max-tasks", dest="max_tasks", type=int, help="Optional limit for number of tasks to evaluate.")
    parser.add_argument("--task-id", dest="task_ids", action="append", help="Specific task ID to evaluate (can be supplied multiple times).")
    parser.add_argument(
        "--exclude-task-id",
        dest="exclude_task_ids",
        action="append",
        help="Task IDs to exclude from the run (can be supplied multiple times).",
    )
    parser.add_argument("--run-id", type=str, help="Optional identifier for the evaluation run.")
    parser.add_argument("--run-root", type=Path, help="Directory under which run artefacts are stored (defaults to reports/eval_runs).")
    parser.add_argument("--resume-from", type=Path, help="Existing run directory to resume.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore previous progress and re-run completed tasks.")
    parser.add_argument("--time-limit-hours", type=float, help="Override global max wall-clock hours for this run.")
    parser.add_argument("--force-feature-refresh", action="store_true", help="Recompute scheduler features even if cached.")
    parser.add_argument("--log-level", default=None, help="Override logging level (e.g., DEBUG).")
    parser.add_argument("--metrics-file", type=Path, default=None, help="Explicit metrics file path (overrides config).")
    parser.add_argument("--enable-modules", default=None, help="Comma-separated module names to force enable.")
    parser.add_argument("--disable-modules", default=None, help="Comma-separated module names to force disable.")
    parser.add_argument("--mock-modules", default=None, help="Comma-separated module names to instantiate using mock implementations.")
    parser.add_argument(
        "--module-budget",
        action="append",
        default=[],
        metavar="NAME=SECONDS",
        help="Override module execution budgets (seconds). May be specified multiple times.",
    )
    return parser.parse_args()


def _deep_update(target: MutableMapping[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), MutableMapping):
            _deep_update(target[key], value)  # type: ignore[index]
        else:
            target[key] = value  # type: ignore[index]


def _parse_csv(value: Optional[str]) -> Sequence[str]:
    if not value:
        return []
    return [token.strip() for token in value.split(",") if token.strip()]


def _collect_overrides(args: argparse.Namespace) -> Dict[str, Set[str]]:
    enable = set(_parse_csv(args.enable_modules))
    disable = set(_parse_csv(args.disable_modules))
    mocks = set(_parse_csv(args.mock_modules))

    env_enable = _parse_csv(_env("TRI_ARC_ENABLE_MODULES"))
    env_disable = _parse_csv(_env("TRI_ARC_DISABLE_MODULES"))
    env_mocks = _parse_csv(_env("TRI_ARC_MOCK_MODULES"))

    enable.update(env_enable)
    disable.update(env_disable)
    mocks.update(env_mocks)

    for name in list(enable):
        if name in disable:
            enable.discard(name)
    return {"enable": enable, "disable": disable, "mocks": mocks}


def _apply_budget_overrides(config: Dict[str, Any], overrides: Sequence[str], logger: logging.Logger) -> None:
    if not overrides:
        return
    modules_cfg = config.setdefault("modules", {})
    for item in overrides:
        if "=" not in item:
            logger.warning("Skipping invalid --module-budget override '%s' (expected name=value).", item)
            continue
        name, raw_value = item.split("=", 1)
        name = name.strip()
        raw_value = raw_value.strip()
        try:
            value = float(raw_value)
        except ValueError:
            logger.warning("Skipping module budget override for %s; '%s' is not numeric.", name, raw_value)
            continue
        module_entry = modules_cfg.setdefault(name, {})
        module_entry["budget_seconds"] = value


def _env(key: str) -> Optional[str]:
    return os.environ.get(key)


def _load_preset_overrides(preset: str) -> Dict[str, Any]:
    preset_path = REPO_ROOT / "configs" / "eval" / f"{preset}.yaml"
    if not preset_path.exists():
        raise FileNotFoundError(f"Preset '{preset}' not found at {preset_path}.")
    with preset_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Preset '{preset}' must contain a mapping at the top level.")
    return payload


def _configure_run_paths(config: MutableMapping[str, Any], run_dir: Path, metrics_override: Optional[Path]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = run_dir / "logs"
    outputs_dir = run_dir / "outputs"
    reports_dir = run_dir / "reports"

    global_cfg = config.setdefault("global", {})
    global_cfg["log_root"] = str(logs_dir)

    logging_cfg = config.setdefault("logging", {})
    logging_cfg.setdefault("runtime_log", "runtime.log")
    metrics_path = Path(metrics_override) if metrics_override else Path(logging_cfg.get("metrics_file", run_dir / "metrics.jsonl"))
    if not metrics_path.is_absolute():
        metrics_path = run_dir / metrics_path
    logging_cfg["metrics_file"] = str(metrics_path)

    arbitrator_cfg = config.setdefault("arbitrator", {})
    arbitrator_cfg.setdefault("outputs_dir", str(outputs_dir))
    arbitrator_cfg.setdefault("reports_dir", str(reports_dir / "arbitrator"))
    arbitrator_cfg.setdefault("logs_dir", str(logs_dir / "arbitrator"))

    evaluation_cfg = config.setdefault("evaluation", {})
    evaluation_cfg["run_dir"] = str(run_dir)
    evaluation_cfg.setdefault("tasks_dir", str(run_dir / "tasks"))
    evaluation_cfg.setdefault("reports_dir", str(reports_dir))

    return metrics_path


def _determine_run_directory(
    *,
    args: argparse.Namespace,
    config: Mapping[str, Any],
    split: str,
) -> tuple[str, Path]:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{split}-{timestamp}"
    if args.resume_from:
        run_dir = Path(args.resume_from)
        if not run_dir.exists():
            raise FileNotFoundError(f"Resume directory {run_dir} does not exist.")
        run_id = run_dir.name if args.run_id is None else args.run_id
        return run_id, run_dir

    run_root = args.run_root
    if run_root is None:
        evaluation_cfg = config.get("evaluation", {}) if isinstance(config.get("evaluation"), Mapping) else {}
        run_root = Path(evaluation_cfg.get("runs_dir", "reports/eval_runs"))
    run_dir = Path(run_root) / run_id
    return run_id, run_dir


def _compute_config_fingerprint(config: Mapping[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _resolve_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    args = parse_args()
    base_config = load_config(args.config)
    if args.preset:
        preset_overrides = _load_preset_overrides(args.preset)
        _deep_update(base_config, preset_overrides)

    overrides = _collect_overrides(args)
    logger = logging.getLogger("tri_arc.run_eval")

    _apply_budget_overrides(base_config, args.module_budget, logger)

    seed = int(base_config.get("global", {}).get("seed", 0))
    set_seed(seed)

    run_id, run_dir = _determine_run_directory(args=args, config=base_config, split=args.split)
    metrics_path = _configure_run_paths(base_config, run_dir, args.metrics_file)

    logging_cfg = base_config.get("logging", {}) if isinstance(base_config.get("logging"), Mapping) else {}
    level = args.log_level or logging_cfg.get("level", "INFO")
    runtime_log_name = logging_cfg.get("runtime_log", "runtime.log")
    log_root = Path(base_config.get("global", {}).get("log_root", run_dir / "logs"))

    max_bytes_mb = float(logging_cfg.get("log_max_bytes_mb", 5))
    max_bytes = int(max_bytes_mb * 1024 * 1024)
    backup_count_cfg = logging_cfg.get("log_backup_count", 3)
    try:
        backup_count = int(backup_count_cfg)
    except Exception:
        backup_count = 3
    compress_rotated = bool(logging_cfg.get("compress_rotated_logs", True))

    log_path = logging_utils.configure_logging(
        log_root,
        runtime_log_name,
        level=level,
        max_bytes=max_bytes,
        backup_count=backup_count,
        compress_rotated=compress_rotated,
    )

    logger.info("Tri-ARC evaluation starting")
    logger.info("Runtime log: %s", log_path)
    logger.info("Run directory: %s", run_dir)
    logger.info("Metrics file: %s", metrics_path)

    data_root = Path(base_config.get("global", {}).get("data_root", "data/arcagi2"))
    if not data_root.exists():
        logger.error("Data root %s does not exist.", data_root)
        return 1

    dataset_loader = DatasetLoader(data_root, enable_checksums=True, logger=logging.getLogger("tri_arc.data"))
    config_fingerprint = _compute_config_fingerprint(base_config)
    time_limit = args.time_limit_hours or float(base_config.get("global", {}).get("max_wall_clock_hours", 12))
    commit_hash = _resolve_commit_hash()

    harness = EvaluationHarness(
        config=base_config,
        run_id=run_id,
        split=args.split,
        run_dir=run_dir,
        dataset_loader=dataset_loader,
        metrics_path=Path(metrics_path),
        config_fingerprint=config_fingerprint,
        time_limit_hours=time_limit,
        force_enable=sorted(overrides["enable"]),
        force_disable=sorted(overrides["disable"]),
        use_mocks=sorted(overrides["mocks"]),
    )

    run_summary: Dict[str, Any] = {}
    try:
        run_summary = harness.run(
            limit=args.max_tasks,
            task_ids=args.task_ids,
            exclude_task_ids=args.exclude_task_ids,
            resume=not args.no_resume,
            force_feature_refresh=args.force_feature_refresh,
        )
    finally:
        harness.shutdown()

    summary_path = run_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(run_summary, handle, indent=2)

    run_metrics = collect_run_metrics(run_dir / "tasks")
    manifest_path = write_run_manifest(
        REPORTS_DIR,
        run_id=run_id,
        split=args.split,
        config_fingerprint=config_fingerprint,
        commit_hash=commit_hash,
        seed=seed,
        time_limit_hours=time_limit,
        dataset_root=data_root,
        metrics_path=Path(metrics_path),
        run_dir=run_dir,
        overrides={key: sorted(value) for key, value in overrides.items()},
        run_summary=run_summary,
    )
    summary_report_path = write_run_summary(
        REPORTS_DIR / "eval_summary.md",
        run_id=run_id,
        split=args.split,
        run_summary=run_summary,
        run_metrics=run_metrics,
        manifest_path=manifest_path,
    )

    history_path = REPORTS_DIR / "eval_history.jsonl"
    previous_entry = find_previous_entry(history_path, split=args.split, exclude_run_id=run_id)
    pass_rate = 0.0
    completed = int(run_summary.get("tasks_completed", 0))
    failed = int(run_summary.get("tasks_failed", 0))
    total_attempted = max(1, completed + failed)
    if total_attempted:
        pass_rate = completed / total_attempted

    history_entry = {
        "run_id": run_id,
        "timestamp": run_summary.get("run_state", {}).get("updated_at"),
        "split": args.split,
        "config_fingerprint": config_fingerprint,
        "commit": commit_hash,
        "seed": seed,
        "time_limit_hours": time_limit,
        "tasks_total": run_summary.get("tasks_total", 0),
        "tasks_completed": completed,
        "tasks_failed": failed,
        "elapsed_s": run_summary.get("elapsed_s", 0.0),
        "fallback_count": run_metrics.get("fallback_count", 0),
        "latency_mean": run_metrics.get("arbitration_latency_ms", {}).get("mean", 0.0),
        "pass_rate": pass_rate,
        "module_stats": run_metrics.get("module_stats", {}),
    }
    append_history(history_path, history_entry)
    delta_path = write_delta_report(REPORTS_DIR, current_entry=history_entry, previous_entry=previous_entry)
    history_markdown_path = write_history_markdown(history_path, REPORTS_DIR / "eval_history.md")

    archive_path = package_run_artifacts(
        run_dir,
        run_id=run_id,
        metrics_path=Path(metrics_path),
        destination_dir=REPORTS_DIR / "archives",
    )

    run_reports_dir = run_dir / "reports"
    run_reports_dir.mkdir(parents=True, exist_ok=True)
    (run_reports_dir / manifest_path.name).write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
    (run_reports_dir / summary_report_path.name).write_text(summary_report_path.read_text(encoding="utf-8"), encoding="utf-8")
    if delta_path is not None:
        (run_reports_dir / delta_path.name).write_text(delta_path.read_text(encoding="utf-8"), encoding="utf-8")
    (run_reports_dir / history_markdown_path.name).write_text(history_markdown_path.read_text(encoding="utf-8"), encoding="utf-8")

    logger.info("Evaluation complete. Summary written to %s", summary_path)
    logger.info("Completed tasks: %s", run_summary.get("tasks_completed"))
    logger.info("Failed tasks: %s", run_summary.get("tasks_failed"))
    logger.info("Total elapsed seconds: %.2f", run_summary.get("elapsed_s", 0.0))
    logger.info("Manifest: %s", manifest_path)
    logger.info("Summary report: %s", summary_report_path)
    if delta_path:
        logger.info("Delta report: %s", delta_path)
    logger.info("History log: %s", history_markdown_path)
    logger.info("Packaged artefacts: %s", archive_path)
    
    return 0 if run_summary.get("tasks_failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
