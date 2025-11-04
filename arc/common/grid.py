from __future__ import annotations

from typing import Any, Sequence, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid, Region


def normalise_grid(value: Any) -> Grid:
    if isinstance(value, Grid):
        return value
    if isinstance(value, (list, tuple)):
        return Grid.from_list(value)  # type: ignore[arg-type]
    raise TypeError(f"Unsupported grid literal: {type(value).__name__}.")


def ensure_palette(grid: Grid) -> None:
    data = grid.data
    if data.min() < 0 or data.max() > 9:
        raise ValueError("Grid palette must remain within [0, 9].")


def validate_position(grid: Grid, position: Sequence[int]) -> Tuple[int, int]:
    if len(position) != 2:
        raise ValueError("Positions must contain exactly two indices.")
    row, col = int(position[0]), int(position[1])
    rows, cols = grid.shape
    if not (0 <= row < rows and 0 <= col < cols):
        raise ValueError(f"Position {(row, col)} is out of bounds for shape {(rows, cols)}.")
    return row, col


def ensure_region_matches_grid(region: Region, grid: Grid) -> Region:
    return region.ensure_shape(grid.shape)


def grids_equal(left: Grid, right: Grid) -> bool:
    return left.shape == right.shape and np.array_equal(left.data, right.data)

