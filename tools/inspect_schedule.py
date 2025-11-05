#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


def load_events(path: Path) -> Iterable[Mapping[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Metrics file '{path}' not found.")
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield payload


def summarise_tasks(events: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for event in events:
        if event.get("event") != "scheduler_allocate":
            continue
        task_id = str(event.get("task_id", "unknown"))
        summary[task_id] = {
            "matched_rules": event.get("matched_rules", []),
            "risk": float(event.get("global_budget_risk", 0.0)),
            "donation_window_s": float(event.get("donation_window_s", 0.0)),
            "risk_alert": bool(event.get("risk_alert", False)),
        }
    return summary


def describe_allocation(event: Mapping[str, Any]) -> str:
    allocations = event.get("allocations", {})
    lines: List[str] = []
    for module, payload in allocations.items():
        lines.append(
            f"  - {module}: priority={payload.get('priority', 0):.3f}, "
            f"soft={payload.get('soft_limit_s', 0):.1f}s, "
            f"hard={payload.get('hard_limit_s', 0):.1f}s, "
            f"start_delay={payload.get('start_delay_s', 0):.1f}s"
        )
    return "\n".join(lines)


def describe_resources(event: Mapping[str, Any]) -> Sequence[str]:
    resources = event.get("resources", {})
    devices = resources.get("devices", {})
    lines: List[str] = []
    for device, payload in devices.items():
        lines.append(
            f"  - {device}: allocations={int(payload.get('allocations', 0))}, "
            f"total_runtime={payload.get('total_expected_runtime_s', 0):.1f}s, "
            f"utilisation={payload.get('utilisation_ratio', 0):.2f}"
        )
    return lines


def describe_cache(event: Mapping[str, Any]) -> Sequence[str]:
    cache = event.get("cache", {})
    lines: List[str] = []
    for name, stats in cache.items():
        if isinstance(stats, Mapping):
            if "overall" in stats:
                overall = stats["overall"]
                lines.append(
                    f"  - {name}: size={overall.get('size', overall.get('capacity', 0))}/{overall.get('capacity', 0)}, "
                    f"hit_rate={overall.get('hit_rate', 0):.2f}"
                )
            else:
                lines.append(f"  - {name}: {stats}")
        else:
            lines.append(f"  - {name}: {stats}")
    return lines


def inspect_task(metrics: Path, task_id: str) -> None:
    matches = []
    for event in load_events(metrics):
        if event.get("event") != "scheduler_allocate":
            continue
        if str(event.get("task_id")) == task_id:
            matches.append(event)

    if not matches:
        print(f"No scheduler allocations found for task '{task_id}'.")
        return

    for idx, event in enumerate(matches, start=1):
        print(f"Allocation #{idx} for task {task_id}")
        print(f"  timestamp: {event.get('timestamp', 'unknown')}")
        print(f"  matched_rules: {', '.join(event.get('matched_rules', [])) or 'none'}")
        print(f"  global_risk: {event.get('global_budget_risk', 0):.3f}")
        print(f"  donation_window: {event.get('donation_window_s', 0):.1f}s")
        if event.get("risk_alert"):
            print("  risk_alert: TRUE")
        print("  allocations:")
        print(describe_allocation(event))
        cache_lines = describe_cache(event)
        if cache_lines:
            print("  caches:")
            for line in cache_lines:
                print(line)
        resource_lines = describe_resources(event)
        if resource_lines:
            print("  resources:")
            for line in resource_lines:
                print(line)
        print()


def list_tasks(metrics: Path, *, limit: int = 20) -> None:
    events = list(load_events(metrics))
    grouped = summarise_tasks(events)
    if not grouped:
        print("No scheduler allocations recorded.")
        return
    count = 0
    for task_id, payload in grouped.items():
        print(
            f"{task_id}: rules={','.join(payload['matched_rules']) or 'none'} "
            f"risk={payload['risk']:.3f} donation_window={payload['donation_window_s']:.1f}s "
            f"{'[RISK]' if payload['risk_alert'] else ''}"
        )
        count += 1
        if limit and count >= limit:
            break


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect scheduler allocations recorded in metrics JSONL logs.")
    parser.add_argument("--metrics", type=Path, default=Path("metrics.jsonl"), help="Path to metrics JSONL file.")
    parser.add_argument("--task-id", dest="task_id", help="Inspect allocations for a specific task identifier.")
    parser.add_argument("--list", action="store_true", help="List recent task allocations instead of detailed inspection.")
    parser.add_argument("--limit", type=int, default=20, help="Limit number of tasks when listing summaries.")
    args = parser.parse_args(argv)

    try:
        if args.list or not args.task_id:
            list_tasks(args.metrics, limit=args.limit)
        if args.task_id:
            inspect_task(args.metrics, args.task_id)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
