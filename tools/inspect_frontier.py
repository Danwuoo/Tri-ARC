from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional


def parse_markdown_table(lines: Iterable[str]) -> List[Dict[str, str]]:
    headers: List[str] = []
    rows: List[Dict[str, str]] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [item.strip() for item in line.strip("|").split("|")]
        if set(parts) <= {"-", ""}:
            continue
        if not headers:
            headers = parts
            continue
        if len(parts) != len(headers):
            continue
        rows.append({header: value for header, value in zip(headers, parts)})
    return rows


def inspect_report(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    rows = parse_markdown_table(path.read_text(encoding="utf-8").splitlines())
    if not rows:
        print(f"[report] No rows found in {path}")
        return
    print(f"[report] Loaded {len(rows)} snapshots from {path}")
    last = rows[-1]
    print("[report] Latest snapshot:")
    for key, value in last.items():
        print(f"  {key}: {value}")


def inspect_log(path: Path, *, task_id: Optional[str], tail: int) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Frontier log not found: {path}")
    counts: Counter[str] = Counter()
    expansions = 0
    last_events: Deque[Dict[str, str]] = deque(maxlen=tail)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = record.get("payload", {})
            record_task = record.get("task_id") or payload.get("task_id")
            if task_id and record_task != task_id:
                continue
            event = record.get("event", "unknown")
            counts[event] += 1
            if event == "expand_node":
                expansions += 1
            last_events.append(
                {
                    "event": event,
                    "timestamp": f"{record.get('timestamp', 0):.3f}",
                    "task": record_task or "-",
                    "details": payload,
                }
            )
    total = sum(counts.values())
    print(f"[log] Analysed {total} events from {path}")
    if task_id:
        print(f"[log] Filtered for task {task_id}")
    for event, count in counts.most_common():
        print(f"  {event}: {count}")
    print(f"  node_expansions: {expansions}")
    if last_events:
        print(f"[log] Last {len(last_events)} events:")
        for entry in last_events:
            print(f"  {entry['timestamp']} | {entry['event']} | task={entry['task']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect symbolic frontier reports and logs.")
    parser.add_argument("--report", type=Path, help="Path to a frontier Markdown report.")
    parser.add_argument("--log", type=Path, help="Path to the symbolic_frontier.log JSONL file.")
    parser.add_argument("--task", type=str, help="Filter log events for a specific task id.")
    parser.add_argument("--tail", type=int, default=10, help="Number of recent events to display.")
    args = parser.parse_args()

    if not args.report and not args.log:
        parser.error("Specify at least --report or --log.")

    if args.report:
        inspect_report(args.report)
    if args.log:
        inspect_log(args.log, task_id=args.task, tail=args.tail)


if __name__ == "__main__":
    main()
