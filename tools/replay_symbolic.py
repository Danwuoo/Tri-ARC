from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_events(path: Path, task_id: Optional[str]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(f"Frontier log not found: {path}")
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
            record["task_id"] = record_task
            events.append(record)
    events.sort(key=lambda item: item.get("timestamp", 0.0))
    return events


def render_timeline(events: List[Dict[str, Any]], *, show_candidates: bool, limit: Optional[int]) -> None:
    print(f"[replay] Loaded {len(events)} events.")
    interesting = {"expand_node", "candidate_evaluated", "prune_expansion", "frontier_snapshot", "search_complete"}
    rendered = 0
    for record in events:
        event = record.get("event")
        if event not in interesting and not show_candidates:
            continue
        if limit is not None and rendered >= limit:
            break
        timestamp = record.get("timestamp", 0.0)
        payload = record.get("payload", {})
        task = record.get("task_id", "-")
        print(f"{timestamp:013.3f} | {event:<18} | task={task} | details={payload}")
        rendered += 1
    if limit is not None and rendered >= limit:
        print(f"... truncated after {limit} events ...")


def replay_egraph(path: Path, *, limit: int) -> None:
    if not path.exists():
        raise FileNotFoundError(f"E-graph history not found: {path}")
    entries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(record)
    if not entries:
        print("[egraph] No rewrite entries found.")
        return
    print(f"[egraph] Showing top {min(limit, len(entries))} rewrites (cost_delta ascending).")
    entries.sort(key=lambda item: item.get("cost_delta", 0.0))
    for record in entries[:limit]:
        print(
            f"  rule={record.get('rule')} | cost_delta={record.get('cost_delta', 0.0):+.3f} | "
            f"{record.get('source', '')[:48]} -> {record.get('target', '')[:48]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay symbolic search sessions and e-graph histories.")
    parser.add_argument("--task", type=str, help="Task identifier to filter events.")
    parser.add_argument("--frontier-log", type=Path, default=Path("logs/symbolic/symbolic_frontier.log"))
    parser.add_argument("--egraph-history", type=Path, help="Path to an e-graph history JSONL file.")
    parser.add_argument("--limit", type=int, help="Limit number of events rendered in the timeline.")
    parser.add_argument("--show-candidates", action="store_true", help="Include candidate evaluation details in the timeline.")
    parser.add_argument("--egraph-limit", type=int, default=10, help="Limit number of rewrite entries to display.")
    args = parser.parse_args()

    events = load_events(args.frontier_log, args.task)
    render_timeline(events, show_candidates=args.show_candidates, limit=args.limit)

    if args.egraph_history:
        replay_egraph(args.egraph_history, limit=args.egraph_limit)


if __name__ == "__main__":
    main()
