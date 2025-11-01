#!/usr/bin/env python3
"""
Execute the Tri-ARC smoke validation suite and archive results.

Usage:
    python scripts/run_smoke.py --env local
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tri_arc.smoke import SmokeContext, SmokeSuite, default_smoke_tests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Tri-ARC smoke validation suite.")
    parser.add_argument("--env", default="local", help="Environment label (e.g. local, kaggle).")
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=ROOT_DIR,
        help="Tri-ARC repository root. Defaults to the repository containing this script.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        help="Directory to write smoke artefacts. Defaults to <root>/reports/smoke_logs.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="Log directory override. Defaults to <root>/logs.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="ARC dataset root override. Defaults to <root>/data/arcagi2.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        help="Path to docs/CONFIG_DEFAULTS.yaml. Defaults to <root>/docs/CONFIG_DEFAULTS.yaml.",
    )
    parser.add_argument("--wheel-root", action="append", type=Path, default=[], help="Additional wheel cache directories.")
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop the suite when the first failure occurs.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Explicit path for JSON output. Defaults to reports/<timestamp>_<env>_smoke.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        help="Explicit path for Markdown output. Defaults to reports/<timestamp>_<env>_smoke.md.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = SmokeContext.from_root(
        root_dir=args.root_dir,
        env=args.env,
        reports_dir=args.reports_dir,
        log_dir=args.log_dir,
        data_root=args.data_root,
        config_path=args.config_path,
        wheel_roots=args.wheel_root,
    )
    suite = SmokeSuite(default_smoke_tests())
    results = suite.run(context, stop_on_fail=args.stop_on_fail)
    summary = SmokeSuite.summarise(results)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports_dir = context.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = args.json_output or (reports_dir / f"{timestamp}_{args.env}_smoke.json")
    markdown_path = args.markdown_output or (reports_dir / f"{timestamp}_{args.env}_smoke.md")

    json_text = SmokeSuite.to_json(context, results, summary, timestamp=timestamp)
    markdown_text = SmokeSuite.to_markdown(context, results, summary, timestamp=timestamp)

    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")

    print(f"[SMOKE] Overall status: {summary['overall'].upper()}")
    print(f"[SMOKE] Results written to:\n  - {json_path}\n  - {markdown_path}")

    if summary["overall"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
