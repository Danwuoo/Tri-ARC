from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

ColourValue = int

COLOUR_NAME_TO_ID: Dict[str, ColourValue] = {
    "black": 0,
    "blue": 1,
    "red": 2,
    "green": 3,
    "yellow": 4,
    "gray": 5,
    "grey": 5,
    "magenta": 6,
    "purple": 6,
    "orange": 7,
    "cyan": 8,
    "teal": 9,
    "white": 0,
}

ID_TO_COLOUR_NAME: Dict[ColourValue, str] = {value: key for key, value in COLOUR_NAME_TO_ID.items()}


@dataclass(frozen=True)
class BoundingBox:
    top: int
    left: int
    bottom: int
    right: int

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def width(self) -> int:
        return self.right - self.left + 1


@dataclass(frozen=True)
class Grid:
    data: np.ndarray

    def __post_init__(self) -> None:
        if self.data.ndim != 2:
            raise ValueError("Grid data must be a 2D array.")
        if not np.issubdtype(self.data.dtype, np.integer):
            object.__setattr__(self, "data", self.data.astype(np.int16, copy=True))
        else:
            object.__setattr__(self, "data", self.data.astype(np.int16, copy=True))

    @classmethod
    def from_list(cls, raw: Sequence[Sequence[int]]) -> "Grid":
        array = np.array(raw, dtype=np.int16)
        if array.ndim != 2:
            raise ValueError("Grid list representation must be rectangular.")
        return cls(array)

    def to_list(self) -> List[List[int]]:
        return self.data.tolist()

    @property
    def shape(self) -> Tuple[int, int]:
        return int(self.data.shape[0]), int(self.data.shape[1])

    def copy(self) -> "Grid":
        return Grid(self.data.copy())

    def equals(self, other: "Grid") -> bool:
        return self.shape == other.shape and np.array_equal(self.data, other.data)

    def detect_background_colour(self) -> ColourValue:
        flat = self.data.reshape(-1)
        counts = np.bincount(flat, minlength=10)
        return int(np.argmax(counts))


@dataclass(frozen=True)
class Region:
    mask: np.ndarray

    def __post_init__(self) -> None:
        if self.mask.ndim != 2:
            raise ValueError("Region mask must be 2D.")
        if self.mask.dtype != bool:
            object.__setattr__(self, "mask", self.mask.astype(bool, copy=True))
        else:
            object.__setattr__(self, "mask", self.mask.copy())

    @classmethod
    def empty(cls, shape: Tuple[int, int]) -> "Region":
        return cls(np.zeros(shape, dtype=bool))

    @classmethod
    def full(cls, shape: Tuple[int, int]) -> "Region":
        return cls(np.ones(shape, dtype=bool))

    @classmethod
    def from_coordinates(cls, shape: Tuple[int, int], coordinates: Iterable[Tuple[int, int]]) -> "Region":
        mask = np.zeros(shape, dtype=bool)
        for row, col in coordinates:
            mask[row, col] = True
        return cls(mask)

    @property
    def area(self) -> int:
        return int(self.mask.sum())

    def bounding_box(self) -> Optional[BoundingBox]:
        if self.area == 0:
            return None
        rows = np.any(self.mask, axis=1)
        cols = np.any(self.mask, axis=0)
        top = int(np.argmax(rows))
        bottom = int(len(rows) - 1 - np.argmax(rows[::-1]))
        left = int(np.argmax(cols))
        right = int(len(cols) - 1 - np.argmax(cols[::-1]))
        return BoundingBox(top=top, left=left, bottom=bottom, right=right)

    def contains(self, row: int, col: int) -> bool:
        return bool(self.mask[row, col])

    def to_indices(self) -> List[Tuple[int, int]]:
        rows, cols = np.where(self.mask)
        return list(zip(rows.tolist(), cols.tolist()))

    def ensure_shape(self, shape: Tuple[int, int]) -> "Region":
        if self.mask.shape != shape:
            raise ValueError(f"Region mask shape {self.mask.shape} does not match expected shape {shape}.")
        return self


Expression = Any


@dataclass(frozen=True)
class Stage:
    operator: str
    arguments: Tuple[Expression, ...]

    def __str__(self) -> str:
        args_repr = " ".join(repr(arg) for arg in self.arguments)
        return f"(apply {self.operator} {args_repr})"


@dataclass(frozen=True)
class Program:
    stages: Tuple[Stage, ...]

    def __iter__(self):
        return iter(self.stages)

    def __len__(self) -> int:
        return len(self.stages)


@dataclass(frozen=True)
class LambdaExpression:
    parameters: Tuple[str, ...]
    body: Expression


@dataclass
class StageResult:
    stage: Stage
    value: Any
    grid: Grid
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTrace:
    initial_grid: Grid
    stage_results: List[StageResult] = field(default_factory=list)

    def append(self, result: StageResult) -> None:
        self.stage_results.append(result)

    @property
    def final_grid(self) -> Grid:
        if not self.stage_results:
            return self.initial_grid
        return self.stage_results[-1].grid


@dataclass
class ExecutionState:
    grid: Grid
    env: Dict[str, Any] = field(default_factory=dict)
    object_stack: List[Region] = field(default_factory=list)
    last_value: Any = None
    last_grid: Optional[Grid] = None
    background_colour: Optional[int] = None

    def clone(self) -> "ExecutionState":
        return ExecutionState(
            grid=self.grid.copy(),
            env=dict(self.env),
            object_stack=list(self.object_stack),
            last_value=self.last_value,
            last_grid=self.last_grid.copy() if self.last_grid else None,
            background_colour=self.background_colour,
        )

    def with_grid(self, grid: Grid) -> "ExecutionState":
        new_state = self.clone()
        new_state.last_grid = self.grid.copy()
        new_state.grid = grid
        new_state.env["current_grid"] = grid
        return new_state

    def push_object(self, region: Region) -> None:
        self.object_stack.append(region)
        self.env["last_object"] = region
        self.env["object_stack_size"] = len(self.object_stack)

    def pop_object(self) -> Optional[Region]:
        if not self.object_stack:
            return None
        region = self.object_stack.pop()
        self.env["object_stack_size"] = len(self.object_stack)
        if self.object_stack:
            self.env["last_object"] = self.object_stack[-1]
        else:
            self.env.pop("last_object", None)
        return region

    def peek_object(self) -> Optional[Region]:
        return self.object_stack[-1] if self.object_stack else None


DSLValue = Union[int, bool, Grid, Region, Tuple[int, int], List[Any], None, LambdaExpression]
