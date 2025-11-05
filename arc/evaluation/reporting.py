from __future__ import annotations

import datetime as dt
import json
import math
import statistics
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


def collect_run_metrics(tasks_dir: Path) -> Dict[str, Any]:
    """Aggregate per-task artefacts into summary statistics."""
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.exists():
        return {
            "tasks_analyzed": 0,
            "fallback_count": 0,
            "low_confidence_count": 0,
            "fallback_rate": 0.0,
            "low_confidence_rate": 0.0,
            "arbitration_latency_ms": {"mean": 0.0, "p95": 0.0, "max": 0.0},
            "module_stats": {},
        }

    fallback_count = 0
    low_confidence_count = 0
    arbitration_latency: list[float] = []
    module_stats: Dict[str, Dict[str, Any]] = {}
    tasks_analyzed = 0

    for entry in sorted(tasks_dir.glob("*.json")):
        data = json.loads(entry.read_text(encoding="utf-8"))
        arbitration = data.get("arbitration", {})
        summary = arbitration.get("summary", {})
        if summary.get("fallback_used"):
            fallback_count += 1
        if summary.get("low_confidence"):
            low_confidence_count += 1
        latency = summary.get("latency_ms")
        if isinstance(latency, (int, float)) and not math.isnan(latency):
            arbitration_latency.append(float(latency))

        modules = data.get("modules", {})
        for name, payload in modules.items():
            record = module_stats.setdefault(name, {"success": 0, "attempts": 0, "elapsed_total": 0.0, "elapsed_count": 0})
            status = payload.get("status")
            record["attempts"] += 1
            if status == "success":
                record["success"] += 1
            elapsed = payload.get("elapsed_s")
            if isinstance(elapsed, (int, float)) and not math.isnan(elapsed):
                record["elapsed_total"] += float(elapsed)
                record["elapsed_count"] += 1
        tasks_analyzed += 1

    metrics = {
        "tasks_analyzed": tasks_analyzed,
        "fallback_count": fallback_count,
        "low_confidence_count": low_confidence_count,
        "fallback_rate": (fallback_count / tasks_analyzed) if tasks_analyzed else 0.0,
        "low_confidence_rate": (low_confidence_count / tasks_analyzed) if tasks_analyzed else 0.0,
        "arbitration_latency_ms": _summarise_latency(arbitration_latency),
        "module_stats": _summarise_module_stats(module_stats),
    }
    return metrics


def write_run_manifest(
    reports_dir: Path,
    *,
    run_id: str,
    split: str,
    config_fingerprint: str,
    commit_hash: str,
    seed: int,
    time_limit_hours: float,
    dataset_root: Path,
    metrics_path: Path,
    run_dir: Path,
    overrides: Mapping[str, Sequence[str]],
    run_summary: Mapping[str, Any],
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc)
    manifest_name = f"eval_manifest_{timestamp.strftime('%Y%m%d')}_{run_id}.md"
    manifest_path = reports_dir / manifest_name

    run_state = run_summary.get("run_state", {})
    lines = [
        f"# Evaluation Manifest ({run_id})",
        "",
        f"- **Split**: `{split}`",
        f"- **Run directory**: `{run_dir}`",
        f"- **Started at**: {run_state.get('started_at', 'unknown')}",
        f"- **Last updated**: {run_state.get('updated_at', timestamp.isoformat())}",
        f"- **Commit hash**: `{commit_hash}`",
        f"- **Config fingerprint**: `{config_fingerprint}`",
        f"- **Seed**: `{seed}`",
        f"- **Wall-clock limit (hours)**: {time_limit_hours}",
        f"- **Dataset root**: `{dataset_root}`",
        f"- **Metrics file**: `{metrics_path}`",
        "",
        "## Module Overrides",
    ]
    if any(overrides.values()):
        for key, values in overrides.items():
            flat = ", ".join(sorted(values)) if values else "none"
            lines.append(f"- **{key.replace('_', ' ').title()}**: {flat}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Outcome",
            f"- Tasks processed: {run_summary.get('tasks_total', 0)}",
            f"- Tasks completed: {run_summary.get('tasks_completed', 0)}",
            f"- Tasks failed: {run_summary.get('tasks_failed', 0)}",
            f"- Elapsed seconds: {run_summary.get('elapsed_s', 0.0):.2f}",
        ]
    )

    modules = run_summary.get("modules", {})
    if modules:
        lines.extend(["", "## Module Success Summary", "", "| Module | Success | Attempts | Success Rate |", "|--------|---------|----------|--------------|"])
        for name, payload in sorted(modules.items()):
            attempts = max(1, int(payload.get("attempts", 0)))
            success = int(payload.get("success", 0))
            rate = success / attempts if attempts else 0.0
            lines.append(f"| {name} | {success} | {attempts} | {rate:.2%} |")

    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path


def write_run_summary(
    summary_path: Path,
    *,
    run_id: str,
    split: str,
    run_summary: Mapping[str, Any],
    run_metrics: Mapping[str, Any],
    manifest_path: Path,
) -> Path:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_completed = run_summary.get("tasks_completed", 0)
    tasks_failed = run_summary.get("tasks_failed", 0)
    total = max(1, tasks_completed + tasks_failed)
    pass_rate = tasks_completed / total if total else 0.0
    latency = run_metrics.get("arbitration_latency_ms", {})

    lines = [
        f"# Evaluation Summary ({run_id})",
        "",
        f"- Split: `{split}`",
        f"- Manifest: `{manifest_path}`",
        f"- Tasks completed: {tasks_completed}",
        f"- Tasks failed: {tasks_failed}",
        f"- Pass rate: {pass_rate:.2%}",
        f"- Fallback activations: {run_metrics.get('fallback_count', 0)} ({run_metrics.get('fallback_rate', 0.0):.2%})",
        f"- Low-confidence decisions: {run_metrics.get('low_confidence_count', 0)} ({run_metrics.get('low_confidence_rate', 0.0):.2%})",
        f"- Mean arbitration latency: {latency.get('mean', 0.0):.2f} ms",
        f"- 95th percentile latency: {latency.get('p95', 0.0):.2f} ms",
        f"- Max latency: {latency.get('max', 0.0):.2f} ms",
        "",
        "## Module Performance",
        "",
        "| Module | Success | Attempts | Success Rate | Avg Runtime (s) |",
        "|--------|---------|----------|--------------|-----------------|",
    ]

    module_stats = run_metrics.get("module_stats", {})
    for name, stats in sorted(module_stats.items()):
        lines.append(
            f"| {name} | {stats.get('success', 0)} | {stats.get('attempts', 0)} | "
            f"{stats.get('success_rate', 0.0):.2%} | {stats.get('avg_elapsed_s', 0.0):.2f} |"
        )

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path


def append_history(history_path: Path, entry: Mapping[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def find_previous_entry(history_path: Path, *, split: str, exclude_run_id: str) -> Optional[Dict[str, Any]]:
    if not history_path.exists():
        return None
    previous: Optional[Dict[str, Any]] = None
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("split") != split:
                continue
            if record.get("run_id") == exclude_run_id:
                continue
            previous = record
    return previous


def write_delta_report(
    reports_dir: Path,
    *,
    current_entry: Mapping[str, Any],
    previous_entry: Optional[Mapping[str, Any]],
) -> Optional[Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    if previous_entry is None:
        return None

    run_id = current_entry.get("run_id", "unknown_run")
    delta_path = reports_dir / f"eval_delta_{run_id}.md"
    deltas = calculate_deltas(current_entry, previous_entry)
    lines = [
        f"# Evaluation Delta ({run_id})",
        "",
        f"- Compared against run `{previous_entry.get('run_id', 'unknown')}` (commit `{previous_entry.get('commit', 'unknown')}`)",
        f"- Task delta: {deltas['tasks_completed']:+d} completions, {deltas['tasks_failed']:+d} failures",
        f"- Pass rate delta: {deltas['pass_rate']:+.2%}",
        f"- Fallback delta: {deltas['fallback_count']:+d}",
        f"- Mean latency delta: {deltas['latency_mean']:+.2f} ms",
        "",
        "## Module Success Delta",
        "",
        "| Module | Success Δ | Attempts Δ | Success Rate Δ |",
        "|--------|-----------|------------|----------------|",
    ]

    for module, payload in sorted(deltas["modules"].items()):
        lines.append(
            f"| {module} | {payload.get('success_delta', 0):+d} | "
            f"{payload.get('attempts_delta', 0):+d} | {payload.get('success_rate_delta', 0.0):+.2%} |"
        )

    delta_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return delta_path


def package_run_artifacts(
    run_dir: Path,
    *,
    run_id: str,
    metrics_path: Path,
    destination_dir: Path,
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    archive_path = destination_dir / f"{run_id}_artefacts.zip"

    include_paths: list[Tuple[Path, str]] = []
    run_dir = Path(run_dir)
    metrics_path = Path(metrics_path)

    candidates = [
        run_dir / "run_state.json",
        run_dir / "summary.json",
        metrics_path,
        run_dir / "outputs",
        run_dir / "logs",
        run_dir / "reports",
    ]

    seen = set()
    for path in candidates:
        if not path.exists():
            continue
        if path in seen:
            continue
        seen.add(path)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    arcname = child.relative_to(run_dir) if child.is_relative_to(run_dir) else Path(child.name)
                    include_paths.append((child, str(arcname)))
        else:
            arcname = path.relative_to(run_dir) if path.is_relative_to(run_dir) else Path(path.name)
            include_paths.append((path, str(arcname)))

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, arcname in include_paths:
            archive.write(path, arcname)

    return archive_path


def write_history_markdown(history_path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not history_path.exists():
        destination.write_text("# Evaluation History\n\n_No runs recorded yet._\n", encoding="utf-8")
        return destination

    entries: list[Dict[str, Any]] = []
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not entries:
        destination.write_text("# Evaluation History\n\n_No runs recorded yet._\n", encoding="utf-8")
        return destination

    entries.sort(key=lambda item: item.get("timestamp") or "")
    lines = [
        "# Evaluation History",
        "",
        "| Run ID | Split | Pass Rate | Completed | Failed | Commit | Timestamp |",
        "|--------|-------|-----------|-----------|--------|--------|-----------|",
    ]
    for entry in entries:
        lines.append(
            f"| {entry.get('run_id', 'unknown')} | {entry.get('split', 'n/a')} | {entry.get('pass_rate', 0.0):.2%} | "
            f"{entry.get('tasks_completed', 0)} | {entry.get('tasks_failed', 0)} | {entry.get('commit', 'unknown')} | "
            f"{entry.get('timestamp', 'unknown')} |"
        )
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def _summarise_latency(samples: Iterable[float]) -> Dict[str, float]:
    data = list(samples)
    if not data:
        return {"mean": 0.0, "p95": 0.0, "max": 0.0}
    mean_val = statistics.fmean(data)
    sorted_values = sorted(data)
    index = min(len(sorted_values) - 1, int(math.ceil(0.95 * len(sorted_values))) - 1)
    return {
        "mean": mean_val,
        "p95": sorted_values[index],
        "max": max(sorted_values),
    }


def _summarise_module_stats(raw_stats: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for name, payload in raw_stats.items():
        attempts = int(payload.get("attempts", 0))
        success = int(payload.get("success", 0))
        elapsed_total = float(payload.get("elapsed_total", 0.0))
        elapsed_count = max(1, int(payload.get("elapsed_count", 0)))
        summary[name] = {
            "success": success,
            "attempts": attempts,
            "success_rate": (success / attempts) if attempts else 0.0,
            "avg_elapsed_s": (elapsed_total / elapsed_count) if elapsed_count else 0.0,
        }
    return summary


def calculate_deltas(current: Mapping[str, Any], previous: Mapping[str, Any]) -> Dict[str, Any]:
    tasks_completed_delta = int(current.get("tasks_completed", 0)) - int(previous.get("tasks_completed", 0))
    tasks_failed_delta = int(current.get("tasks_failed", 0)) - int(previous.get("tasks_failed", 0))
    pass_rate_delta = float(current.get("pass_rate", 0.0)) - float(previous.get("pass_rate", 0.0))
    fallback_delta = int(current.get("fallback_count", 0)) - int(previous.get("fallback_count", 0))
    latency_delta = float(current.get("latency_mean", 0.0)) - float(previous.get("latency_mean", 0.0))

    module_deltas: Dict[str, Dict[str, Any]] = {}
    current_modules: Mapping[str, Mapping[str, Any]] = current.get("module_stats", {})
    previous_modules: Mapping[str, Mapping[str, Any]] = previous.get("module_stats", {})
    module_keys = set(current_modules.keys()) | set(previous_modules.keys())
    for module in sorted(module_keys):
        cur = current_modules.get(module, {})
        prev = previous_modules.get(module, {})
        module_deltas[module] = {
            "success_delta": int(cur.get("success", 0)) - int(prev.get("success", 0)),
            "attempts_delta": int(cur.get("attempts", 0)) - int(prev.get("attempts", 0)),
            "success_rate_delta": float(cur.get("success_rate", 0.0)) - float(prev.get("success_rate", 0.0)),
        }

    return {
        "tasks_completed": tasks_completed_delta,
        "tasks_failed": tasks_failed_delta,
        "pass_rate": pass_rate_delta,
        "fallback_count": fallback_delta,
        "latency_mean": latency_delta,
        "modules": module_deltas,
    }
