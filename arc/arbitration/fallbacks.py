from __future__ import annotations

import itertools
from typing import Any, Dict, Iterable, List, Sequence

from arc.common.grid import normalise_grid
from arc.symbolic.dsl.types import Grid

from .models import (
    ArbitrationCandidate,
    CandidateType,
    VerificationRecord,
    VerificationStatus,
)


def generate_fallback_candidates(
    task_id: str,
    train_examples: Sequence[Dict[str, Any]],
    test_examples: Sequence[Dict[str, Any]],
) -> List[ArbitrationCandidate]:
    strategies = [
        _identity_strategy,
        _most_common_colour_strategy,
    ]

    results: List[ArbitrationCandidate] = []
    for index, strategy in enumerate(strategies):
        metadata, outputs = strategy(train_examples, test_examples)
        candidate = ArbitrationCandidate(
            candidate_id=f"fallback-{index}",
            module="fallback",
            candidate_type=CandidateType.FALLBACK,
            payload={"outputs": outputs},
            metadata=metadata,
            provenance={"strategy": metadata.get("strategy"), "task_id": task_id},
        )
        candidate.verification = VerificationRecord(
            status=VerificationStatus.SKIPPED,
            duration_ms=0.0,
            traces=[],
            extras={"reason": "fallback"},
        )
        results.append(candidate)
    return results


def _identity_strategy(
    train_examples: Sequence[Dict[str, Any]],
    test_examples: Sequence[Dict[str, Any]],
) -> Any:
    outputs = []
    for example in test_examples:
        grid = example.get("input")
        outputs.append(_grid_to_list(grid))
    metadata = {
        "strategy": "identity",
        "rationale": "No verified candidates; returning test inputs unchanged.",
    }
    return metadata, outputs


def _most_common_colour_strategy(
    train_examples: Sequence[Dict[str, Any]],
    test_examples: Sequence[Dict[str, Any]],
) -> Any:
    colour_counts = [0] * 10
    for example in itertools.chain(train_examples, test_examples):
        grid = example.get("input") or example.get("output")
        if not grid:
            continue
        normalised = normalise_grid(grid)
        for value in normalised.data.reshape(-1):
            colour_counts[int(value)] += 1
    dominant_colour = max(range(len(colour_counts)), key=lambda idx: colour_counts[idx])

    outputs = []
    for example in test_examples:
        input_grid = normalise_grid(example.get("input"))
        rows, cols = input_grid.shape
        filled = Grid.from_list([[dominant_colour for _ in range(cols)] for _ in range(rows)])
        outputs.append(filled.to_list())
    metadata = {
        "strategy": "dominant_colour_fill",
        "rationale": f"Fallback fill using dominant colour {dominant_colour}.",
        "dominant_colour": dominant_colour,
    }
    return metadata, outputs


def _grid_to_list(grid_like: Any) -> List[List[int]]:
    if grid_like is None:
        return []
    return normalise_grid(grid_like).to_list()


__all__ = ["generate_fallback_candidates"]
