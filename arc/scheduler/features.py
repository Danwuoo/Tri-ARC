from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid


@dataclass(frozen=True)
class GridStats:
    min_rows: int
    max_rows: int
    min_cols: int
    max_cols: int
    mean_cells: float
    sparsity: float
    example_count: int


@dataclass(frozen=True)
class PaletteStats:
    unique_colours: int
    entropy: float
    dominant_colour: int
    palette_histogram: Dict[int, int]


@dataclass(frozen=True)
class SymmetryStats:
    horizontal: float
    vertical: float
    rotational: float


@dataclass(frozen=True)
class ObjectStats:
    average_components: float
    average_component_size: float
    max_component_size: int


@dataclass(frozen=True)
class TaskFeatures:
    task_id: str
    grid: GridStats
    palette: PaletteStats
    symmetry: SymmetryStats
    objects: ObjectStats
    history: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "grid": asdict(self.grid),
            "palette": asdict(self.palette),
            "symmetry": asdict(self.symmetry),
            "objects": asdict(self.objects),
            "history": dict(self.history),
        }


def compute_task_features(
    task_id: str,
    examples: Sequence[Mapping[str, Any]],
    *,
    history: Mapping[str, Any] | None = None,
) -> TaskFeatures:
    grids = _collect_grids(examples)
    if not grids:
        raise ValueError(f"Task '{task_id}' does not contain any grids to analyse.")

    grid_stats = _compute_grid_stats(grids)
    palette_stats = _compute_palette_stats(grids)
    symmetry_stats = _compute_symmetry_stats(grids)
    object_stats = _compute_object_stats(grids)
    history_stats = _normalise_history(history)

    return TaskFeatures(
        task_id=task_id,
        grid=grid_stats,
        palette=palette_stats,
        symmetry=symmetry_stats,
        objects=object_stats,
        history=history_stats,
    )


def _collect_grids(examples: Sequence[Mapping[str, Any]]) -> List[Grid]:
    grids: List[Grid] = []
    for example in examples:
        for key in ("input", "output"):
            if key not in example:
                continue
            grid_literal = example[key]
            if grid_literal is None:
                continue
            try:
                grid = _normalise_grid(grid_literal)
            except Exception as exc:
                raise ValueError(f"Failed to normalise grid for key '{key}': {exc}") from exc
            grids.append(grid)
    return grids


def _compute_grid_stats(grids: Sequence[Grid]) -> GridStats:
    rows = [grid.shape[0] for grid in grids]
    cols = [grid.shape[1] for grid in grids]
    cells = [grid.shape[0] * grid.shape[1] for grid in grids]
    filled_cells = [int(np.count_nonzero(grid.data)) for grid in grids]

    sparsity_values = []
    for filled, total in zip(filled_cells, cells):
        sparsity_values.append(1.0 - (filled / total if total else 0.0))

    return GridStats(
        min_rows=int(min(rows)),
        max_rows=int(max(rows)),
        min_cols=int(min(cols)),
        max_cols=int(max(cols)),
        mean_cells=float(mean(cells)),
        sparsity=float(mean(sparsity_values)),
        example_count=len(grids),
    )


def _compute_palette_stats(grids: Sequence[Grid]) -> PaletteStats:
    histogram: Dict[int, int] = {}
    for grid in grids:
        unique, counts = np.unique(grid.data, return_counts=True)
        for colour, count in zip(unique.tolist(), counts.tolist()):
            histogram[colour] = histogram.get(colour, 0) + int(count)

    total = sum(histogram.values())
    entropy = 0.0
    if total > 0:
        for count in histogram.values():
            probability = count / total
            entropy -= probability * math.log(probability, 2)

    dominant_colour = max(histogram.items(), key=lambda item: item[1])[0] if histogram else 0

    return PaletteStats(
        unique_colours=len(histogram),
        entropy=float(entropy),
        dominant_colour=int(dominant_colour),
        palette_histogram=dict(sorted(histogram.items())),
    )


def _compute_symmetry_stats(grids: Sequence[Grid]) -> SymmetryStats:
    horizontal_scores: List[float] = []
    vertical_scores: List[float] = []
    rotational_scores: List[float] = []

    for grid in grids:
        data = grid.data
        if data.size == 0:
            continue
        horizontal_scores.append(_symmetry_score(data, np.flipud))
        vertical_scores.append(_symmetry_score(data, np.fliplr))
        rotational_scores.append(_symmetry_score(data, lambda x: np.rot90(x, k=2)))

    if not horizontal_scores:
        horizontal_scores = [0.0]
    if not vertical_scores:
        vertical_scores = [0.0]
    if not rotational_scores:
        rotational_scores = [0.0]

    return SymmetryStats(
        horizontal=float(mean(horizontal_scores)),
        vertical=float(mean(vertical_scores)),
        rotational=float(mean(rotational_scores)),
    )


def _symmetry_score(data: np.ndarray, transform: Any) -> float:
    mirrored = transform(data)
    matches = np.sum(data == mirrored)
    total = data.size
    return float(matches / total) if total else 0.0


def _compute_object_stats(grids: Sequence[Grid]) -> ObjectStats:
    component_counts: List[int] = []
    component_sizes: List[int] = []
    max_sizes: List[int] = []

    for grid in grids:
        _, sizes = _connected_components(grid.data)
        component_counts.append(len(sizes))
        component_sizes.extend(sizes)
        max_sizes.append(max(sizes) if sizes else 0)

    if not component_sizes:
        component_sizes = [0]

    average_components = float(mean(component_counts)) if component_counts else 0.0
    average_size = float(mean(component_sizes))
    max_size = int(max(max_sizes)) if max_sizes else 0

    return ObjectStats(
        average_components=average_components,
        average_component_size=average_size,
        max_component_size=max_size,
    )


def _connected_components(data: np.ndarray) -> Tuple[int, List[int]]:
    rows, cols = data.shape
    visited = np.zeros_like(data, dtype=bool)
    components: List[int] = []

    background = int(np.bincount(data.reshape(-1), minlength=10).argmax())

    for row in range(rows):
        for col in range(cols):
            if visited[row, col]:
                continue
            if int(data[row, col]) == background:
                visited[row, col] = True
                continue
            size = _flood_fill(data, visited, row, col)
            if size > 0:
                components.append(size)
    return len(components), components


def _flood_fill(data: np.ndarray, visited: np.ndarray, start_row: int, start_col: int) -> int:
    target = int(data[start_row, start_col])
    stack = [(start_row, start_col)]
    size = 0
    rows, cols = data.shape

    while stack:
        row, col = stack.pop()
        if visited[row, col]:
            continue
        if int(data[row, col]) != target:
            continue
        visited[row, col] = True
        size += 1

        if row > 0:
            stack.append((row - 1, col))
        if row + 1 < rows:
            stack.append((row + 1, col))
        if col > 0:
            stack.append((row, col - 1))
        if col + 1 < cols:
            stack.append((row, col + 1))

    return size


def _normalise_history(history: Mapping[str, Any] | None) -> Dict[str, float]:
    if not history:
        return {
            "symbolic_success_rate": 0.5,
            "ttt_success_rate": 0.5,
            "llm_success_rate": 0.5,
        }

    def clamp(value: Any, default: float = 0.5) -> float:
        try:
            numeric = float(value)
        except Exception:
            return default
        return max(0.0, min(1.0, numeric))

    return {
        "symbolic_success_rate": clamp(history.get("symbolic_success_rate")),
        "ttt_success_rate": clamp(history.get("ttt_success_rate")),
        "llm_success_rate": clamp(history.get("llm_success_rate")),
    }


def _normalise_grid(value: Any) -> Grid:
    if isinstance(value, Grid):
        return value
    if isinstance(value, (list, tuple)):
        return Grid.from_list(value)  # type: ignore[arg-type]
    raise TypeError(f"Unsupported grid literal of type {type(value).__name__}.")
