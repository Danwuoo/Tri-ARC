from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from arc.symbolic.dsl.types import Program, Stage


@dataclass
class FragmentCandidate:
    pattern: Tuple[str, ...]
    occurrences: int
    score: float
    example: Program


@dataclass
class CompressionResult:
    fragments: List[FragmentCandidate]
    report_path: Optional[Path] = None


def _extract_patterns(program: Program, max_length: int) -> Sequence[Tuple[str, ...]]:
    operators = [stage.operator for stage in program]
    patterns: List[Tuple[str, ...]] = []
    for length in range(2, max_length + 1):
        for index in range(len(operators) - length + 1):
            window = tuple(operators[index : index + length])
            patterns.append(window)
    return patterns


def mine_fragments(
    programs: Iterable[Program],
    *,
    min_occurrences: int = 3,
    max_length: int = 4,
    report_path: Optional[Path] = None,
) -> CompressionResult:
    programs = list(programs)
    counter: Counter[Tuple[str, ...]] = Counter()
    examples: dict[Tuple[str, ...], Program] = {}
    for program in programs:
        for pattern in _extract_patterns(program, max_length):
            counter[pattern] += 1
            examples.setdefault(pattern, program)
    fragments: List[FragmentCandidate] = []
    for pattern, occurrences in counter.items():
        if occurrences < min_occurrences:
            continue
        score = occurrences / max(1, len(pattern))
        fragments.append(FragmentCandidate(pattern=pattern, occurrences=occurrences, score=score, example=examples[pattern]))
    fragments.sort(key=lambda item: item.score, reverse=True)
    resolved_path: Optional[Path] = None
    if fragments and report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as handle:
            handle.write("# DreamCoder Fragment Candidates\n")
            handle.write("| Pattern | Occurrences | Score | Example |\n")
            handle.write("|---------|-------------|-------|---------|\n")
            for fragment in fragments:
                payload = json.dumps(fragment.pattern)
                handle.write(f"| `{payload}` | {fragment.occurrences} | {fragment.score:.3f} | `{fragment.example}` |\n")
        resolved_path = report_path
    return CompressionResult(fragments=fragments, report_path=resolved_path)


__all__ = ["mine_fragments", "FragmentCandidate", "CompressionResult"]
