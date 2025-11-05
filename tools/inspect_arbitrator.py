#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

DEFAULT_DECISIONS_DIR = Path("logs/arbitrator/decisions")
DEFAULT_VERIFICATION_DIR = Path("logs/arbitrator/verification")
DEFAULT_OUTPUT_PATH = Path("outputs/pass2.json")


def _load_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def list_tasks(decisions_dir: Path) -> List[str]:
    if not decisions_dir.exists():
        return []
    return sorted(item.stem for item in decisions_dir.glob("*.json"))


def show_task(task_id: str, decisions_dir: Path, *, include_traces: bool) -> None:
    decision_path = decisions_dir / f"{task_id}.json"
    if not decision_path.exists():
        raise FileNotFoundError(f"No decision log found for task '{task_id}'. (expected {decision_path})")

    payload = _load_json(decision_path)
    print(f"# Task {task_id}")
    print(f"- Timestamp: {payload.get('timestamp')}")
    print(f"- Fallback used: {payload.get('fallback_used')}")
    print(f"- Low confidence: {payload.get('low_confidence')}")
    print("- Answers:")
    for answer in payload.get("answers", []):
        print(
            f"  - {answer.get('candidate_id')} (module={answer.get('module')}) "
            f"score={answer.get('score'):.3f} signature={answer.get('signature')}"
        )
    if payload.get("rationale"):
        print("- Rationale:")
        for entry in payload["rationale"]:
            print(f"  - {entry}")
    if payload.get("rejected_candidates"):
        print("- Rejected candidates:")
        for candidate in payload["rejected_candidates"]:
            print(
                f"  - {candidate.get('candidate_id')} [{candidate.get('module')}] "
                f"status={candidate.get('verification_status')} reason={candidate.get('failure_reason')}"
            )

    if include_traces:
        print("\nVerification traces:")
        verification_dir = DEFAULT_VERIFICATION_DIR
        for answer in payload.get("answers", []):
            prefix = f"{task_id}_{answer['candidate_id']}"
            matches = sorted(verification_dir.glob(f"{prefix}_*.json"))
            for trace_path in matches:
                trace_payload = _load_json(trace_path)
                status = trace_payload.get("status")
                print(f"- {trace_path.name} :: status={status}")


def regenerate_outputs(
    decisions_dir: Path,
    *,
    destination: Path,
    tasks: Optional[Iterable[str]] = None,
) -> None:
    selected_tasks = list(tasks) if tasks else list_tasks(decisions_dir)
    outputs: Dict[str, List[List[List[int]]]] = {}
    for task_id in selected_tasks:
        payload = _load_json(decisions_dir / f"{task_id}.json")
        outputs[task_id] = payload.get("answers_outputs", [])
        if not outputs[task_id]:
            # Fall back to flattening decisions directly
            outputs[task_id] = [answer.get("outputs", []) for answer in payload.get("answers", [])]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(outputs, handle, indent=2)
    print(f"Wrote regenerated outputs for {len(selected_tasks)} tasks to {destination}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect arbitrator decisions, candidate scores, and regenerate submission outputs."
    )
    parser.add_argument("--decisions-dir", type=Path, default=DEFAULT_DECISIONS_DIR)
    parser.add_argument("--list", action="store_true", help="List tasks with arbitration decisions.")
    parser.add_argument("--task", type=str, default=None, help="Task identifier to inspect.")
    parser.add_argument("--show-traces", action="store_true", help="Include verification trace filenames in output.")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate submission outputs from decision logs (writes to outputs/pass2.json by default).",
    )
    parser.add_argument("--destination", type=Path, default=DEFAULT_OUTPUT_PATH, help="Destination for regenerated JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    decisions_dir = args.decisions_dir
    if args.list:
        tasks = list_tasks(decisions_dir)
        if not tasks:
            print("No arbitrator decisions found.")
        else:
            print("\n".join(tasks))
    if args.task:
        show_task(args.task, decisions_dir, include_traces=args.show_traces)

    if args.regenerate:
        tasks = [args.task] if args.task else None
        regenerate_outputs(decisions_dir, destination=args.destination, tasks=tasks)

    if not (args.list or args.task or args.regenerate):
        print("No action requested; use --list, --task, or --regenerate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

