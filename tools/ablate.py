#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_EVAL_SCRIPT = REPO_ROOT / "scripts" / "run_eval.py"
REPORTS_DIR = REPO_ROOT / "reports" / "ablations"

DEFAULT_SCENARIOS: Dict[str, Mapping[str, str]] = {
    "baseline": {},
    "symbolic_only": {"ttt": "disable", "llm": "disable"},
    "ttt_only": {"symbolic": "disable", "llm": "disable"},
    "llm_only": {"symbolic": "disable", "ttt": "disable"},
    "symbolic_disabled": {"symbolic": "disable"},
}


@dataclass(frozen=True)
class Scenario:
    name: str
    toggles: Dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run evaluation ablations by toggling module availability.")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "docs" / "CONFIG_DEFAULTS.yaml")
    parser.add_argument("--preset", type=str, help="Preset name forwarded to scripts/run_eval.py.")
    parser.add_argument("--split", choices=["train", "evaluation", "smoke"], default="smoke")
    parser.add_argument("--max-tasks", dest="max_tasks", type=int, help="Limit number of tasks per ablation scenario.")
    parser.add_argument("--time-limit-hours", type=float, help="Override wall-clock limit per run.")
    parser.add_argument("--scenario", action="append", help="Scenario specification NAME:module=action (actions: enable, disable, mock).")
    parser.add_argument("--run-root", type=Path, help="Directory to store ablation run artefacts (defaults to reports/ablations/<timestamp>).")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing.")
    return parser.parse_args()


def parse_scenarios(raw: Optional[Iterable[str]]) -> List[Scenario]:
    if not raw:
        return [Scenario(name, dict(toggles)) for name, toggles in DEFAULT_SCENARIOS.items()]
    scenarios: List[Scenario] = []
    for entry in raw:
        if ":" not in entry:
            raise ValueError(f"Scenario '{entry}' must be formatted as name:module=action,...")
        name, spec = entry.split(":", 1)
        toggles: Dict[str, str] = {}
        for token in spec.split(","):
            token = token.strip()
            if not token:
                continue
            if "=" not in token:
                raise ValueError(f"Scenario token '{token}' must use module=action syntax.")
            module, action = token.split("=", 1)
            action = action.lower().strip()
            if action not in {"enable", "disable", "mock"}:
                raise ValueError(f"Unsupported action '{action}' in scenario '{entry}'.")
            toggles[module.strip()] = action
        scenarios.append(Scenario(name=name.strip(), toggles=toggles))
    return scenarios


def build_command(
    *,
    scenario: Scenario,
    args: argparse.Namespace,
    run_root: Path,
    run_id: str,
) -> List[str]:
    cmd: List[str] = [sys.executable, str(RUN_EVAL_SCRIPT)]
    cmd.extend(["--config", str(args.config)])
    cmd.extend(["--split", args.split])
    cmd.extend(["--run-id", run_id])
    cmd.extend(["--run-root", str(run_root)])
    if args.preset:
        cmd.extend(["--preset", args.preset])
    if args.max_tasks is not None:
        cmd.extend(["--max-tasks", str(args.max_tasks)])
    if args.time_limit_hours is not None:
        cmd.extend(["--time-limit-hours", str(args.time_limit_hours)])

    disable_modules = [module for module, action in scenario.toggles.items() if action == "disable"]
    enable_modules = [module for module, action in scenario.toggles.items() if action == "enable"]
    mock_modules = [module for module, action in scenario.toggles.items() if action == "mock"]

    if enable_modules:
        cmd.extend(["--enable-modules", ",".join(sorted(set(enable_modules)))])
    if disable_modules:
        cmd.extend(["--disable-modules", ",".join(sorted(set(disable_modules)))])
    if mock_modules:
        cmd.extend(["--mock-modules", ",".join(sorted(set(mock_modules)))])
    return cmd


def load_summary(run_dir: Path) -> Optional[Dict[str, Any]]:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None
    with summary_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    args = parse_args()
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scenarios = parse_scenarios(args.scenario)

    base_run_root = args.run_root or (REPORTS_DIR / timestamp)
    base_run_root = Path(base_run_root)
    base_run_root.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    for scenario in scenarios:
        run_id = f"{scenario.name}-{timestamp}"
        command = build_command(scenario=scenario, args=args, run_root=base_run_root, run_id=run_id)
        print(f"[ablate] Scenario '{scenario.name}' -> run_id={run_id}")
        print(f"[ablate] Command: {' '.join(command)}")
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(f"[ablate] Scenario '{scenario.name}' failed with exit code {result.returncode}.", file=sys.stderr)
            return result.returncode
        run_dir = base_run_root / run_id
        summary = load_summary(run_dir)
        if summary is None:
            print(f"[ablate] Missing summary for scenario '{scenario.name}' at {run_dir}.", file=sys.stderr)
            continue
        completed = int(summary.get("tasks_completed", 0))
        failed = int(summary.get("tasks_failed", 0))
        total = max(1, completed + failed)
        pass_rate = completed / total if total else 0.0
        records.append(
            {
                "scenario": scenario.name,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "tasks_completed": completed,
                "tasks_failed": failed,
                "pass_rate": pass_rate,
                "elapsed_s": summary.get("elapsed_s", 0.0),
                "toggles": scenario.toggles,
            }
        )

    if args.dry_run:
        return 0

    if not records:
        print("[ablate] No scenarios executed successfully.", file=sys.stderr)
        return 1

    report_lines = [
        f"# Ablation Summary ({timestamp})",
        "",
        "| Scenario | Run ID | Pass Rate | Completed | Failed | Elapsed (s) | Toggles |",
        "|----------|--------|-----------|-----------|--------|-------------|---------|",
    ]
    for record in records:
        toggles_repr = ", ".join(f"{module}={action}" for module, action in sorted(record["toggles"].items()))
        report_lines.append(
            f"| {record['scenario']} | {record['run_id']} | {record['pass_rate']:.2%} | "
            f"{record['tasks_completed']} | {record['tasks_failed']} | {record['elapsed_s']:.2f} | {toggles_repr or 'baseline'} |"
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"ablation_{timestamp}.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"[ablate] Report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
