from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np

from arc.symbolic.dsl.types import COLOUR_NAME_TO_ID, Grid, Region

ColourValue = int
Position = Tuple[int, int]


def resolve_colour(value: Any) -> ColourValue:
    if isinstance(value, bool):
        raise ValueError("Colour cannot be a boolean.")
    if isinstance(value, (int, np.integer)):
        colour = int(value)
    elif isinstance(value, str):
        lower = value.lower()
        if lower not in COLOUR_NAME_TO_ID:
            raise ValueError(f"Unknown colour token '{value}'.")
        colour = int(COLOUR_NAME_TO_ID[lower])
    else:
        raise ValueError(f"Unsupported colour value: {value!r}")
    if not 0 <= colour <= 9:
        raise ValueError(f"Colour id {colour} outside palette range [0, 9].")
    return colour


def ensure_position(value: Any, shape: Sequence[int]) -> Position:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"Positions must be length-2 tuples, received {value!r}.")
    row, col = int(value[0]), int(value[1])
    rows, cols = int(shape[0]), int(shape[1])
    if not (0 <= row < rows and 0 <= col < cols):
        raise ValueError(f"Position {(row, col)} out of bounds for grid shape {(rows, cols)}.")
    return row, col


def ensure_region(value: Any, shape: Sequence[int]) -> Region:
    if isinstance(value, Region):
        mask = value.ensure_shape((int(shape[0]), int(shape[1]))).mask
        return Region(mask)
    raise ValueError(f"Expected Region instance, received {type(value).__name__}.")


def ensure_grid(value: Any) -> Grid:
    if isinstance(value, Grid):
        return value
    if isinstance(value, (list, tuple)):
        return Grid.from_list(value)
    raise ValueError(f"Expected Grid instance or list representation, received {type(value).__name__}.")


def region_from_bbox(top: int, left: int, bottom: int, right: int, shape: Sequence[int]) -> Region:
    rows, cols = int(shape[0]), int(shape[1])
    if not (0 <= top <= bottom < rows and 0 <= left <= right < cols):
        raise ValueError("Bounding box coordinates out of grid bounds.")
    mask = np.zeros((rows, cols), dtype=bool)
    mask[top : bottom + 1, left : right + 1] = True
    return Region(mask)


def connected_components(grid: Grid, *, connectivity: int = 4, background: int = 0) -> List[Dict[str, Any]]:
    if connectivity not in (4, 8):
        raise ValueError("Connectivity must be either 4 or 8.")

    deltas: List[Tuple[int, int]]
    if connectivity == 4:
        deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    else:
        deltas = [
            (-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ]

    data = grid.data
    rows, cols = data.shape
    visited = np.zeros_like(data, dtype=bool)
    components: List[Dict[str, Any]] = []

    for row in range(rows):
        for col in range(cols):
            if visited[row, col] or data[row, col] == background:
                continue
            colour = int(data[row, col])
            coords: List[Tuple[int, int]] = []
            queue: deque[Tuple[int, int]] = deque([(row, col)])
            visited[row, col] = True

            while queue:
                r, c = queue.popleft()
                if data[r, c] != colour:
                    continue
                coords.append((r, c))
                for dr, dc in deltas:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and not visited[nr, nc] and data[nr, nc] == colour:
                        visited[nr, nc] = True
                        queue.append((nr, nc))

            mask = np.zeros_like(data, dtype=bool)
            for r, c in coords:
                mask[r, c] = True
            region = Region(mask)
            bbox = region.bounding_box()
            components.append(
                {
                    "region": region,
                    "area": len(coords),
                    "colour": colour,
                    "bounding_box": bbox,
                    "top_left": (bbox.top, bbox.left) if bbox else (row, col),
                }
            )

    components.sort(
        key=lambda entry: (
            -entry["area"],
            entry["top_left"][0],
            entry["top_left"][1],
        )
    )
    return components

