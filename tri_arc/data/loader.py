from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

Grid = List[List[int]]


@dataclass(slots=True)
class ARCTaskExample:
    """Single ARC example with an input and output grid."""

    input: Grid
    output: Grid


@dataclass(slots=True)
class TaskMetadata:
    """Derived statistics for an ARC task."""

    task_id: str
    split: str
    train_examples: int
    test_examples: int
    input_shapes: Sequence[Tuple[int, int]]
    output_shapes: Sequence[Tuple[int, int]]
    palette: Sequence[int]


@dataclass(slots=True)
class ARCTask:
    """In-memory representation of an ARC task ready for evaluation."""

    task_id: str
    split: str
    train: Sequence[ARCTaskExample]
    test: Sequence[ARCTaskExample]
    metadata: TaskMetadata


class ARCAGI2Dataset:
    """Loader for the ARC-AGI-2 dataset with deterministic iteration."""

    _SPLIT_ALIASES = {
        "train": "training",
        "training": "training",
        "eval": "evaluation",
        "evaluation": "evaluation",
        "public": "evaluation",
        "smoke": "training",
    }

    def __init__(self, data_root: Path, *, cache_in_memory: bool = True) -> None:
        self.data_root = data_root.resolve()
        self._cache_enabled = cache_in_memory
        self._task_cache: Dict[Tuple[str, str], ARCTask] = {}
        if not self.data_root.exists():
            raise FileNotFoundError(f"Dataset root not found: {self.data_root}")

    def resolve_split(self, split: str) -> str:
        try:
            return self._SPLIT_ALIASES[split.lower()]
        except KeyError:
            raise ValueError(f"Unknown split '{split}'. Expected one of {sorted(self._SPLIT_ALIASES)}.") from None

    def list_task_ids(self, split: str) -> List[str]:
        canonical = self.resolve_split(split)
        split_dir = self.data_root / canonical
        if not split_dir.exists():
            raise FileNotFoundError(f"Split directory missing: {split_dir}")
        return sorted(path.stem for path in split_dir.glob("*.json"))

    def load_task(self, task_id: str, split: str) -> ARCTask:
        canonical = self.resolve_split(split)
        cache_key = (canonical, task_id)
        if self._cache_enabled and cache_key in self._task_cache:
            return self._task_cache[cache_key]

        path = self.data_root / canonical / f"{task_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Task file not found: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        train_examples = [
            ARCTaskExample(input=_clone_grid(item["input"]), output=_clone_grid(item["output"]))
            for item in payload.get("train", [])
        ]
        test_examples = [
            ARCTaskExample(input=_clone_grid(item["input"]), output=_clone_grid(item["output"]))
            for item in payload.get("test", [])
        ]
        metadata = _compute_metadata(task_id, canonical, train_examples, test_examples)
        task = ARCTask(task_id=task_id, split=canonical, train=train_examples, test=test_examples, metadata=metadata)

        if self._cache_enabled:
            self._task_cache[cache_key] = task
        return task

    def iter_split(
        self,
        split: str,
        *,
        shuffle: bool = False,
        seed: Optional[int] = None,
        limit: Optional[int] = None,
        smoke_sample: int = 10,
    ) -> Iterator[ARCTask]:
        """
        Iterate over tasks in the requested split.

        Parameters
        ----------
        split:
            Dataset partition. Supports aliases defined in `_SPLIT_ALIASES`.
        shuffle:
            If True, tasks are shuffled deterministically using `seed`.
        seed:
            Seed for deterministic shuffling. When omitted, `shuffle=True` falls back to Python's hash seed.
        limit:
            Optional maximum number of tasks to yield.
        smoke_sample:
            Number of training tasks to stream when `split="smoke"`.
        """
        canonical = self.resolve_split(split)
        task_ids = self.list_task_ids(canonical)

        if split.lower() == "smoke":
            task_ids = task_ids[:smoke_sample]

        if shuffle:
            rng = random.Random(seed)
            rng.shuffle(task_ids)

        if limit is not None:
            task_ids = task_ids[:limit]

        for task_id in task_ids:
            yield self.load_task(task_id, canonical)


def _clone_grid(grid: Iterable[Iterable[int]]) -> Grid:
    return [list(row) for row in grid]


def _compute_metadata(
    task_id: str,
    split: str,
    train: Sequence[ARCTaskExample],
    test: Sequence[ARCTaskExample],
) -> TaskMetadata:
    input_shapes: List[Tuple[int, int]] = []
    output_shapes: List[Tuple[int, int]] = []
    palette: set[int] = set()

    for example in list(train) + list(test):
        input_shapes.append(_grid_shape(example.input))
        output_shapes.append(_grid_shape(example.output))
        palette.update(_grid_palette(example.input))
        palette.update(_grid_palette(example.output))

    metadata = TaskMetadata(
        task_id=task_id,
        split=split,
        train_examples=len(train),
        test_examples=len(test),
        input_shapes=tuple(input_shapes),
        output_shapes=tuple(output_shapes),
        palette=tuple(sorted(palette)),
    )
    return metadata


def _grid_shape(grid: Grid) -> Tuple[int, int]:
    if not grid:
        return (0, 0)
    return (len(grid), len(grid[0]))


def _grid_palette(grid: Grid) -> Iterable[int]:
    for row in grid:
        for value in row:
            yield int(value)


def seed_everything(seed: int) -> None:
    """
    Seed Python, NumPy, and torch (if available) for deterministic behaviour.

    The environment variable `PYTHONHASHSEED` is set to stabilise hash-based operations.
    """
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:  # pragma: no cover - optional dependency
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass
