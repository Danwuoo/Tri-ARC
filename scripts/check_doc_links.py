#!/usr/bin/env python3
"""Verify that every Markdown reference to docs/*.md resolves locally."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Iterable, List, Sequence

LINK_PATTERN = re.compile(r"(docs/[A-Za-z0-9_.\-/]+\.md(?:#[A-Za-z0-9_.\-]+)?)")


def _iter_markdown_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.md"):
        if path.is_file():
            yield path


def _check_file(path: Path, repo_root: Path) -> List[str]:
    errors: List[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # pragma: no cover - surface IO errors
        errors.append(f"{path}: unable to read file ({exc})")
        return errors

    for line_no, line in enumerate(lines, start=1):
        for match in LINK_PATTERN.finditer(line):
            target = match.group(1)
            target_path = target.split("#", 1)[0]
            resolved = (repo_root / target_path).resolve()
            if not resolved.exists():
                errors.append(f"{path}:{line_no}: missing Markdown target '{target_path}'")
    return errors


def _check_paths(paths: Sequence[Path], repo_root: Path) -> List[str]:
    issues: List[str] = []
    for path in paths:
        if path.is_dir():
            for markdown_file in _iter_markdown_files(path):
                issues.extend(_check_file(markdown_file, repo_root))
        elif path.suffix.lower() == ".md":
            issues.extend(_check_file(path, repo_root))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=(Path("docs"),),
        help="Directories or Markdown files to scan (defaults to docs/).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root used to resolve relative paths.",
    )
    args = parser.parse_args()

    paths = [path if path.is_absolute() else args.repo_root / path for path in args.paths]
    issues = _check_paths(paths, args.repo_root)

    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("All Markdown references to docs/*.md resolved successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
