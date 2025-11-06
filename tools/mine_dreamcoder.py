from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Iterable, List

sys.path.append(str(Path(__file__).resolve().parents[1]))

from arc.symbolic.dsl.types import Program, Stage  # noqa: E402
from arc.symbolic.egraph.compression import mine_fragments  # noqa: E402


def load_programs_from_json(path: Path) -> List[Program]:
    data = json.loads(path.read_text(encoding="utf-8"))
    programs: List[Program] = []
    for program_spec in data:
        stages = []
        for entry in program_spec:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError(f"Invalid stage entry in {path}: {entry!r}")
            operator, arguments = entry
            if not isinstance(operator, str):
                raise ValueError(f"Operator must be a string, got {operator!r}")
            stages.append(Stage(operator=operator, arguments=tuple(arguments)))
        programs.append(Program(tuple(stages)))
    return programs


def load_programs_from_checkpoint(path: Path) -> List[Program]:
    payload = pickle.loads(path.read_bytes())
    candidates = payload.get("candidates", [])
    programs: List[Program] = []
    for candidate in candidates:
        program = getattr(candidate, "program", None)
        if program is None:
            raw = candidate.get("program")
            if raw is None:
                continue
            stages = []
            for operator, arguments in raw:
                stages.append(Stage(operator=operator, arguments=tuple(arguments)))
            program = Program(tuple(stages))
        programs.append(program)
    return programs


def append_changelog(changelog_path: Path, report_path: Path, fragments: Iterable[str]) -> None:
    timestamp = time.strftime("%Y-%m-%d")
    new_lines = [
        f"## {timestamp} - DreamCoder Fragment Mining",
        f"- Report: `{report_path}`",
        "- Top fragments:",
    ]
    for fragment in fragments:
        new_lines.append(f"  - {fragment}")
    new_lines.append("")

    original = changelog_path.read_text(encoding="utf-8").splitlines()
    insert_at = 2 if len(original) > 2 else len(original)
    updated = original[:insert_at] + new_lines + original[insert_at:]
    changelog_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def format_fragment(pattern: Iterable[str], occurrences: int, score: float) -> str:
    pattern_repr = ", ".join(pattern)
    return f"`({pattern_repr})` occurrences={occurrences} score={score:.2f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine DreamCoder-style fragments from symbolic solver outputs.")
    parser.add_argument("--checkpoint", type=Path, help="Path to a symbolic checkpoint containing candidates.")
    parser.add_argument("--programs", type=Path, help="JSON file containing explicit program stage lists.")
    parser.add_argument("--output", type=Path, help="Destination report path.")
    parser.add_argument("--min-occurrences", type=int, default=3, help="Minimum occurrences for a fragment to be reported.")
    parser.add_argument("--max-length", type=int, default=4, help="Maximum fragment length (number of stages).")
    parser.add_argument("--update-changelog", action="store_true", help="Append summary to docs/changelog.md.")
    parser.add_argument("--changelog", type=Path, default=Path("docs/changelog.md"), help="Path to the changelog file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    programs: List[Program] = []
    if args.checkpoint:
        programs.extend(load_programs_from_checkpoint(args.checkpoint))
    if args.programs:
        programs.extend(load_programs_from_json(args.programs))
    if not programs:
        raise RuntimeError("No programs provided. Supply --checkpoint and/or --programs.")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = args.output or Path("reports") / f"dreamcoder_fragments_{timestamp}.md"
    result = mine_fragments(
        programs,
        min_occurrences=args.min_occurrences,
        max_length=args.max_length,
        report_path=output_path,
    )

    print(f"[dreamcoder] Analysed {len(programs)} programs; discovered {len(result.fragments)} fragments.")
    if result.report_path:
        print(f"[dreamcoder] Report written to {result.report_path}")

    if args.update_changelog and result.fragments:
        top_fragments = [format_fragment(fragment.pattern, fragment.occurrences, fragment.score) for fragment in result.fragments[:3]]
        append_changelog(args.changelog, result.report_path or output_path, top_fragments)
        print(f"[dreamcoder] Changelog updated at {args.changelog}")


if __name__ == "__main__":
    main()
