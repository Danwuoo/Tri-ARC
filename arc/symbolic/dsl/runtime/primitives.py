from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from arc.symbolic.dsl.types import ExecutionState, Grid, Region, Stage

from .context import PrimitiveContext
from .errors import InterpreterFailure
from .utils import connected_components, ensure_grid, ensure_position, ensure_region, region_from_bbox, resolve_colour


@dataclass(frozen=True)
class ArgSpec:
    name: str
    type_hint: str
    required: bool = True
    default: Any = None
    variadic: bool = False


@dataclass
class PrimitiveResult:
    state: ExecutionState
    value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PrimitiveSpec:
    name: str
    arguments: Tuple[ArgSpec, ...]
    result_type: str
    implementation: Callable[[PrimitiveContext, Dict[str, Any]], PrimitiveResult]
    description: str

    def bind_arguments(self, values: Tuple[Any, ...], ctx: PrimitiveContext) -> Dict[str, Any]:
        bound: Dict[str, Any] = {}
        index = 0
        total = len(values)
        for i, arg in enumerate(self.arguments):
            if index >= total:
                if arg.required:
                    raise InterpreterFailure.validation(
                        f"Missing required argument '{arg.name}' for {self.name}.",
                        details={"operator": self.name, "stage_index": ctx.stage_index},
                    )
                bound[arg.name] = [] if arg.variadic else arg.default
                continue

            if arg.variadic:
                remaining = values[index:]
                if not remaining and arg.required:
                    raise InterpreterFailure.validation(
                        f"Operator {self.name} expects at least one argument for '{arg.name}'.",
                        details={"operator": self.name, "stage_index": ctx.stage_index},
                    )
                bound[arg.name] = [_normalise_argument(arg, value, ctx) for value in remaining]
                index = total
                continue
            raw = values[index]
            index += 1
            bound[arg.name] = _normalise_argument(arg, raw, ctx)
        if index < total:
            raise InterpreterFailure.validation(
                f"Operator {self.name} received too many arguments (expected {len(self.arguments)}, got {total}).",
                details={"operator": self.name, "stage_index": ctx.stage_index},
            )
        return bound


_TYPE_CHECKERS: Dict[str, Callable[[Any], Any]] = {}


def _register_type(name: str):
    def decorator(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
        _TYPE_CHECKERS[name] = fn
        return fn

    return decorator


@_register_type("int")
def _check_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError("Expected integer argument.")
    return int(value)


@_register_type("str")
def _check_str(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected string argument.")
    return value


@_register_type("bool")
def _check_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Expected boolean argument.")
    return value


@_register_type("colour")
def _check_colour(value: Any) -> int:
    return resolve_colour(value)


@_register_type("grid")
def _check_grid(value: Any) -> Grid:
    return ensure_grid(value)


@_register_type("region")
def _check_region(value: Any) -> Region:
    if not isinstance(value, Region):
        raise ValueError("Expected region argument.")
    return value


@_register_type("lambda")
def _check_lambda(value: Any) -> Callable[..., Any]:
    if not callable(value):
        raise ValueError("Expected lambda/callable argument.")
    return value


@_register_type("stage")
def _check_stage(value: Any) -> Stage:
    if not isinstance(value, Stage):
        raise ValueError("Expected nested Stage argument.")
    return value


@_register_type("position")
def _check_position(value: Any) -> Tuple[int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("Positions must be length-2 tuples.")
    return int(value[0]), int(value[1])


@_register_type("region_list")
def _check_region_list(value: Any) -> List[Region]:
    if not isinstance(value, list) or not all(isinstance(item, Region) for item in value):
        raise ValueError("Expected list of Region objects.")
    return value


def _normalise_argument(arg: ArgSpec, value: Any, ctx: PrimitiveContext) -> Any:
    options = [option.strip() for option in arg.type_hint.split("|")]
    last_error: Optional[Exception] = None
    for option in options:
        checker = _TYPE_CHECKERS.get(option)
        try:
            if checker:
                return checker(value)
            return value
        except Exception as exc:
            last_error = exc
    raise InterpreterFailure.validation(
        f"Argument '{arg.name}' failed validation for {ctx.operator} ({arg.type_hint}).",
        details={"operator": ctx.operator, "stage_index": ctx.stage_index, "value": repr(value), "error": str(last_error) if last_error else None},
    )


def _clone_state(state: ExecutionState) -> ExecutionState:
    new_state = state.clone()
    new_state.env["current_grid"] = new_state.grid
    return new_state


def _update_grid(ctx: PrimitiveContext, grid: Grid) -> ExecutionState:
    state = ctx.state.with_grid(grid)
    state.last_value = None
    state.env["last_value"] = None
    return state


def _set_last_value(state: ExecutionState, value: Any) -> ExecutionState:
    state.last_value = value
    state.env["last_value"] = value
    return state


def _set_last_region(state: ExecutionState, region: Region) -> None:
    state.env["last_region"] = region


def _erode_mask(mask: np.ndarray) -> np.ndarray:
    up = np.zeros_like(mask, dtype=bool)
    down = np.zeros_like(mask, dtype=bool)
    left = np.zeros_like(mask, dtype=bool)
    right = np.zeros_like(mask, dtype=bool)

    up[1:, :] = mask[:-1, :]
    down[:-1, :] = mask[1:, :]
    left[:, 1:] = mask[:, :-1]
    right[:, :-1] = mask[:, 1:]

    return mask & up & down & left & right


def _dilate_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    expanded = mask.copy()
    for _ in range(radius):
        shell = expanded.copy()
        shell[:-1, :] |= expanded[1:, :]
        shell[1:, :] |= expanded[:-1, :]
        shell[:, :-1] |= expanded[:, 1:]
        shell[:, 1:] |= expanded[:, :-1]
        expanded |= shell
    return expanded


def primitive_identity(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    state = _clone_state(ctx.state)
    return PrimitiveResult(state=state, value=state.grid)


def primitive_rotate(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    steps = int(args["steps"]) % 4
    if steps == 0:
        state = _clone_state(ctx.state)
        return PrimitiveResult(state=state, value=state.grid, metadata={"steps": 0})
    rotated = np.rot90(ctx.state.grid.data, -steps)
    new_grid = Grid(rotated)
    state = _update_grid(ctx, new_grid)
    return PrimitiveResult(state=state, value=new_grid, metadata={"steps": steps})


def primitive_reflect(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    axis = args["axis"].lower()
    data = ctx.state.grid.data
    if axis == "horizontal":
        reflected = np.flipud(data)
    elif axis == "vertical":
        reflected = np.fliplr(data)
    elif axis == "main_diagonal":
        reflected = data.T
    elif axis == "anti_diagonal":
        reflected = np.rot90(data.T, 2)
    else:
        raise InterpreterFailure.validation(
            f"Unknown reflection axis '{axis}'.",
            details={"operator": "reflect", "stage_index": ctx.stage_index},
        )
    new_grid = Grid(reflected.copy())
    state = _update_grid(ctx, new_grid)
    return PrimitiveResult(state=state, value=new_grid, metadata={"axis": axis})


def primitive_transpose(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    data = ctx.state.grid.data
    new_grid = Grid(data.T.copy())
    state = _update_grid(ctx, new_grid)
    return PrimitiveResult(state=state, value=new_grid)


def primitive_replace_colour(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    src = resolve_colour(args["src"])
    dst = resolve_colour(args["dst"])
    region: Optional[Region] = args.get("region")

    data = ctx.state.grid.data.copy()
    if region is not None:
        mask = region.ensure_shape(ctx.state.grid.shape).mask
        data[mask & (data == src)] = dst
    else:
        data[data == src] = dst

    new_grid = Grid(data)
    state = _update_grid(ctx, new_grid)
    return PrimitiveResult(state=state, value=new_grid, metadata={"src": src, "dst": dst})


def primitive_flood_fill(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    position = args["seed"]
    colour = resolve_colour(args["colour"])
    try:
        row, col = ensure_position(position, ctx.state.grid.shape)
    except ValueError as exc:
        raise InterpreterFailure.out_of_bounds(str(exc), details={"operator": "flood_fill", "stage_index": ctx.stage_index}) from exc

    data = ctx.state.grid.data.copy()
    target_colour = int(data[row, col])
    if target_colour == colour:
        state = _clone_state(ctx.state)
        return PrimitiveResult(state=state, value=state.grid, metadata={"seed": (row, col), "colour": colour})

    rows, cols = data.shape
    queue: List[Tuple[int, int]] = [(row, col)]
    visited = np.zeros_like(data, dtype=bool)
    deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    while queue:
        r, c = queue.pop()
        if visited[r, c] or data[r, c] != target_colour:
            continue
        visited[r, c] = True
        data[r, c] = colour
        for dr, dc in deltas:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr, nc] and data[nr, nc] == target_colour:
                queue.append((nr, nc))

    new_grid = Grid(data)
    state = _update_grid(ctx, new_grid)
    return PrimitiveResult(state=state, value=new_grid, metadata={"seed": (row, col), "colour": colour})


def primitive_paint_region(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    colour = resolve_colour(args["colour"])
    data = ctx.state.grid.data.copy()
    mask = region.mask
    data[mask] = colour
    new_grid = Grid(data)
    state = _update_grid(ctx, new_grid)
    _set_last_region(state, region)
    return PrimitiveResult(state=state, value=new_grid, metadata={"colour": colour, "pixels": int(mask.sum())})


def primitive_extract_region(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    pad = int(args.get("pad", 0))
    bbox = region.bounding_box()
    if bbox is None:
        raise InterpreterFailure.validation(
            "Cannot extract from an empty region.",
            details={"operator": "extract_region", "stage_index": ctx.stage_index},
        )
    top = max(0, bbox.top - pad)
    left = max(0, bbox.left - pad)
    bottom = min(ctx.state.grid.shape[0] - 1, bbox.bottom + pad)
    right = min(ctx.state.grid.shape[1] - 1, bbox.right + pad)
    data = ctx.state.grid.data[top : bottom + 1, left : right + 1].copy()
    new_grid = Grid(data)
    state = _update_grid(ctx, new_grid)
    return PrimitiveResult(
        state=state,
        value=new_grid,
        metadata={"bounding_box": (top, left, bottom, right), "pad": pad},
    )


def primitive_trim_background(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    grid = ctx.state.grid
    data = grid.data
    pad = max(0, int(args.get("pad", 0)))
    colour_arg = args.get("colour")
    auto_colour = False
    if colour_arg is None:
        auto_colour = True
    elif isinstance(colour_arg, str) and colour_arg.lower() in {"auto", "background"}:
        auto_colour = True
    if auto_colour:
        colour = ctx.state.background_colour if ctx.state.background_colour is not None else int(grid.detect_background_colour())
    else:
        colour = resolve_colour(colour_arg)
    mask = data != colour
    if not np.any(mask):
        state = _clone_state(ctx.state)
        return PrimitiveResult(state=state, value=state.grid, metadata={"colour": colour, "trimmed": False})
    row_indices = np.where(mask.any(axis=1))[0]
    col_indices = np.where(mask.any(axis=0))[0]
    top = max(0, row_indices[0] - pad)
    bottom = min(data.shape[0] - 1, row_indices[-1] + pad)
    left = max(0, col_indices[0] - pad)
    right = min(data.shape[1] - 1, col_indices[-1] + pad)
    top_i, bottom_i, left_i, right_i = int(top), int(bottom), int(left), int(right)
    cropped = data[top_i : bottom_i + 1, left_i : right_i + 1].copy()
    new_grid = Grid(cropped)
    state = _update_grid(ctx, new_grid)
    state.background_colour = colour
    trimmed = new_grid.shape != grid.shape
    metadata = {
        "colour": int(colour),
        "bounding_box": (top_i, left_i, bottom_i, right_i),
        "trimmed": trimmed,
    }
    return PrimitiveResult(state=state, value=new_grid, metadata=metadata)


def primitive_place(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    source = ensure_grid(args["source"])
    position = args["position"]
    mode = args.get("mode", "overwrite").lower() if args.get("mode") else "overwrite"
    target_arg = args.get("target")
    target_grid = ensure_grid(target_arg) if target_arg is not None else ctx.state.grid

    try:
        row, col = ensure_position(position, target_grid.shape)
    except ValueError as exc:
        raise InterpreterFailure.out_of_bounds(str(exc), details={"operator": "place", "stage_index": ctx.stage_index}) from exc

    src_rows, src_cols = source.shape
    tgt_rows, tgt_cols = target_grid.shape
    if row + src_rows > tgt_rows or col + src_cols > tgt_cols:
        raise InterpreterFailure.out_of_bounds(
            "Source grid does not fit inside target grid at the requested position.",
            details={"operator": "place", "stage_index": ctx.stage_index, "source_shape": source.shape, "target_shape": target_grid.shape, "position": (row, col)},
        )

    target_data = target_grid.data.copy()
    src_data = source.data
    for r in range(src_rows):
        for c in range(src_cols):
            value = int(src_data[r, c])
            if mode == "transparent" and value == 0:
                continue
            target_data[row + r, col + c] = value

    new_grid = Grid(target_data)
    state = _update_grid(ctx, new_grid)
    return PrimitiveResult(
        state=state,
        value=new_grid,
        metadata={"position": (row, col), "mode": mode, "source_shape": source.shape},
    )


def primitive_map_cells(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    func = args["lambda"]
    mask = region.mask
    data = ctx.state.grid.data.copy()
    coords = list(zip(*np.where(mask)))
    last_colour = None
    for row, col in coords:
        cell = {"row": int(row), "col": int(col), "value": int(data[row, col])}
        try:
            result = func(cell)
        except InterpreterFailure:
            raise
        except Exception as exc:
            raise InterpreterFailure.lambda_error(
                "Lambda evaluation raised an exception.",
                details={"operator": "map_cells", "stage_index": ctx.stage_index, "location": (int(row), int(col))},
                cause=exc,
            ) from exc
        try:
            new_colour = resolve_colour(result)
        except ValueError as exc:
            raise InterpreterFailure.lambda_error(
                str(exc),
                details={"operator": "map_cells", "stage_index": ctx.stage_index, "location": (int(row), int(col))},
            ) from exc
        data[row, col] = new_colour
        last_colour = new_colour

    new_grid = Grid(data)
    state = _update_grid(ctx, new_grid)
    if last_colour is not None:
        _set_last_value(state, last_colour)
    _set_last_region(state, region)
    return PrimitiveResult(
        state=state,
        value=new_grid,
        metadata={"updated_cells": len(coords)},
    )


def primitive_region_all(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    rows, cols = ctx.state.grid.shape
    mask = np.ones((rows, cols), dtype=bool)
    region = Region(mask)
    state = _clone_state(ctx.state)
    state.push_object(region)
    _set_last_region(state, region)
    return PrimitiveResult(state=state, value=region, metadata={"area": rows * cols})

def primitive_region_where_colour(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    colour = resolve_colour(args["colour"])
    mask = ctx.state.grid.data == colour
    region = Region(mask)
    state = _clone_state(ctx.state)
    state.push_object(region)
    _set_last_region(state, region)
    return PrimitiveResult(state=state, value=region, metadata={"area": int(mask.sum()), "colour": colour})

def primitive_region_from_bbox(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    top = _check_int(args["top"])
    left = _check_int(args["left"])
    bottom = _check_int(args["bottom"])
    right = _check_int(args["right"])
    try:
        region = region_from_bbox(top, left, bottom, right, ctx.state.grid.shape)
    except ValueError as exc:
        raise InterpreterFailure.out_of_bounds(str(exc), details={"operator": "region_from_bbox", "stage_index": ctx.stage_index}) from exc
    state = _clone_state(ctx.state)
    state.push_object(region)
    _set_last_region(state, region)
    return PrimitiveResult(state=state, value=region, metadata={"bounding_box": (top, left, bottom, right)})


def primitive_region_outline(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    mask = region.mask
    interior = _erode_mask(mask)
    outline_mask = mask & ~interior
    outline = Region(outline_mask)
    state = _clone_state(ctx.state)
    state.push_object(outline)
    _set_last_region(state, outline)
    return PrimitiveResult(state=state, value=outline, metadata={"area": int(outline_mask.sum())})


def primitive_region_expand(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    radius = max(0, int(args.get("radius", 1)))
    if radius == 0:
        state = _clone_state(ctx.state)
        state.push_object(region)
        _set_last_region(state, region)
        return PrimitiveResult(state=state, value=region, metadata={"area": int(region.mask.sum()), "radius": radius})
    expanded_mask = _dilate_mask(region.mask, radius)
    expanded = Region(expanded_mask)
    state = _clone_state(ctx.state)
    state.push_object(expanded)
    _set_last_region(state, expanded)
    return PrimitiveResult(
        state=state,
        value=expanded,
        metadata={"area": int(expanded_mask.sum()), "radius": radius},
    )

def primitive_detect_objects(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    connectivity = int(args.get("connectivity", 4))
    min_size = int(args.get("min_size", 1))
    background = ctx.state.background_colour
    if background is None:
        background = int(ctx.state.grid.detect_background_colour())
    components = connected_components(ctx.state.grid, connectivity=connectivity, background=background)
    filtered = [comp for comp in components if comp["area"] >= min_size]
    state = _clone_state(ctx.state)
    state.object_stack.clear()
    regions: List[Region] = []
    metadata: List[Dict[str, Any]] = []
    for entry in filtered:
        region = entry["region"]
        regions.append(region)
        metadata.append({"area": entry["area"], "colour": entry["colour"], "bounding_box": entry["bounding_box"]})
    for region in reversed(regions):
        state.push_object(region)
    state.env["objects"] = regions
    state.env["object_metadata"] = metadata
    state.background_colour = background
    _set_last_value(state, len(regions))
    return PrimitiveResult(state=state, value=regions, metadata={"count": len(regions), "connectivity": connectivity, "min_size": min_size})

def primitive_select_object(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    selector = args["selector"].lower()
    hint = args.get("hint")
    state = _clone_state(ctx.state)
    metadata: List[Dict[str, Any]] = state.env.get("object_metadata", [])
    if not metadata:
        raise InterpreterFailure.validation(
            "select_object requires prior detect_objects metadata.",
            details={"operator": "select_object", "stage_index": ctx.stage_index},
        )
    if selector == "largest":
        index = max(range(len(metadata)), key=lambda i: metadata[i]["area"])
    elif selector == "smallest":
        index = min(range(len(metadata)), key=lambda i: metadata[i]["area"])
    elif selector == "index":
        if hint is None:
            raise InterpreterFailure.validation(
                "select_object index selector requires a hint argument.",
                details={"operator": "select_object", "stage_index": ctx.stage_index},
            )
        index = int(hint)
        if index < 0 or index >= len(metadata):
            raise InterpreterFailure.out_of_bounds(
                f"Object index {index} outside valid range 0..{len(metadata) - 1}.",
                details={"operator": "select_object", "stage_index": ctx.stage_index},
            )
    elif selector == "colour":
        if hint is None:
            raise InterpreterFailure.validation(
                "select_object colour selector requires a colour hint.",
                details={"operator": "select_object", "stage_index": ctx.stage_index},
            )
        colour = resolve_colour(hint)
        matches = [i for i, meta in enumerate(metadata) if meta["colour"] == colour]
        if not matches:
            raise InterpreterFailure.validation(
                f"No object found for colour {colour}.",
                details={"operator": "select_object", "stage_index": ctx.stage_index},
            )
        index = matches[0]
    else:
        raise InterpreterFailure.validation(
            f"Unknown selector '{selector}'.",
            details={"operator": "select_object", "stage_index": ctx.stage_index},
        )
    region = state.env["objects"][index]
    state.push_object(region)
    _set_last_region(state, region)
    state.env["last_object"] = region
    _set_last_value(state, index)
    chosen = metadata[index]
    return PrimitiveResult(state=state, value=region, metadata={"selector": selector, "index": index, "colour": chosen["colour"], "area": chosen["area"]})

def primitive_push_region(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    state = _clone_state(ctx.state)
    state.push_object(region)
    _set_last_region(state, region)
    return PrimitiveResult(state=state, value=list(state.object_stack), metadata={"stack_size": len(state.object_stack)})

def primitive_pop_region(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    state = _clone_state(ctx.state)
    region = state.pop_object()
    if region is None:
        raise InterpreterFailure.validation(
            "Cannot pop region from an empty stack.",
            details={"operator": "pop_region", "stage_index": ctx.stage_index},
        )
    _set_last_region(state, region)
    return PrimitiveResult(state=state, value=region, metadata={"stack_size": len(state.object_stack)})

def primitive_majority_colour(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    mask = region.mask
    if not mask.any():
        raise InterpreterFailure.validation(
            "Cannot compute majority colour for an empty region.",
            details={"operator": "majority_colour", "stage_index": ctx.stage_index},
        )
    values = ctx.state.grid.data[mask].astype(int)
    counts = np.bincount(values, minlength=10)
    colour = int(np.argmax(counts))
    state = _clone_state(ctx.state)
    _set_last_region(state, region)
    _set_last_value(state, colour)
    return PrimitiveResult(state=state, value=colour, metadata={"colour": colour})

def primitive_count_cells(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    region = ensure_region(args["region"], ctx.state.grid.shape)
    count = int(region.mask.sum())
    state = _clone_state(ctx.state)
    _set_last_region(state, region)
    _set_last_value(state, count)
    return PrimitiveResult(state=state, value=count, metadata={"cells": count})


def primitive_compose(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    stages = args["stages"]
    if not stages:
        raise InterpreterFailure.validation(
            "compose requires at least one stage.",
            details={"operator": "compose", "stage_index": ctx.stage_index},
        )
    if ctx.run_stage is None:
        raise InterpreterFailure.validation(
            "compose cannot dispatch nested stages without interpreter support.",
            details={"operator": "compose", "stage_index": ctx.stage_index},
        )
    state = ctx.state
    for index, stage in enumerate(stages):
        if not isinstance(stage, Stage):
            raise InterpreterFailure.validation(
                "compose arguments must be Stage values.",
                details={"operator": "compose", "stage_index": ctx.stage_index},
            )
        path_tuple = ctx.path + (index,)
        result = ctx.run_stage(stage, state, path_tuple)
        state = result.state
    return PrimitiveResult(state=state, value=state.grid, metadata={"stages": len(stages)})


def primitive_repeat(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    count = max(0, int(args["count"]))
    stage = args["stage"]
    if not isinstance(stage, Stage):
        raise InterpreterFailure.validation(
            "repeat expects a Stage argument.",
            details={"operator": "repeat", "stage_index": ctx.stage_index},
        )
    if ctx.run_stage is None:
        raise InterpreterFailure.validation(
            "repeat cannot execute without interpreter support.",
            details={"operator": "repeat", "stage_index": ctx.stage_index},
        )
    state = ctx.state
    for iteration in range(count):
        path_tuple = ctx.path + (iteration,)
        result = ctx.run_stage(stage, state, path_tuple)
        state = result.state
    return PrimitiveResult(state=state, value=state.grid, metadata={"iterations": count})


def primitive_if_equal(ctx: PrimitiveContext, args: Dict[str, Any]) -> PrimitiveResult:
    left = args["left"]
    right = args["right"]
    then_stage = args["then_stage"]
    else_stage = args.get("else_stage")
    branch = "then" if left == right else "else"
    if ctx.run_stage is None:
        raise InterpreterFailure.validation(
            "if_equal cannot execute without interpreter support.",
            details={"operator": "if_equal", "stage_index": ctx.stage_index},
        )
    if left == right:
        if not isinstance(then_stage, Stage):
            raise InterpreterFailure.validation(
                "if_equal requires Stage values for branches.",
                details={"operator": "if_equal", "stage_index": ctx.stage_index},
            )
        path_tuple = ctx.path + (0,)
        result = ctx.run_stage(then_stage, ctx.state, path_tuple)
        return PrimitiveResult(state=result.state, value=result.value, metadata={"branch": branch})
    if else_stage is None:
        state = _clone_state(ctx.state)
        return PrimitiveResult(state=state, value=state.grid, metadata={"branch": branch})
    if not isinstance(else_stage, Stage):
        raise InterpreterFailure.validation(
            "if_equal requires Stage values for branches.",
            details={"operator": "if_equal", "stage_index": ctx.stage_index},
        )
    path_tuple = ctx.path + (1,)
    result = ctx.run_stage(else_stage, ctx.state, path_tuple)
    return PrimitiveResult(state=result.state, value=result.value, metadata={"branch": branch})

PRIMITIVES: Dict[str, PrimitiveSpec] = {}

def register(spec: PrimitiveSpec) -> None:
    PRIMITIVES[spec.name] = spec

def build_registry() -> Dict[str, PrimitiveSpec]:
    return PRIMITIVES

register(PrimitiveSpec(
    name="identity",
    arguments=(),
    result_type="grid",
    implementation=primitive_identity,
    description="Return the input grid unchanged.",
))
register(PrimitiveSpec(
    name="rotate",
    arguments=(ArgSpec("steps", "int"),),
    result_type="grid",
    implementation=primitive_rotate,
    description="Rotate the grid by multiples of 90 degrees clockwise.",
))
register(PrimitiveSpec(
    name="reflect",
    arguments=(ArgSpec("axis", "str"),),
    result_type="grid",
    implementation=primitive_reflect,
    description="Reflect the grid along the requested axis.",
))
register(PrimitiveSpec(
    name="transpose",
    arguments=(),
    result_type="grid",
    implementation=primitive_transpose,
    description="Transpose the grid.",
))
register(PrimitiveSpec(
    name="replace_colour",
    arguments=(ArgSpec("src", "colour"), ArgSpec("dst", "colour"), ArgSpec("region", "region", required=False, default=None)),
    result_type="grid",
    implementation=primitive_replace_colour,
    description="Replace one colour with another, optionally inside a region.",
))
register(PrimitiveSpec(
    name="flood_fill",
    arguments=(ArgSpec("seed", "position"), ArgSpec("colour", "colour")),
    result_type="grid",
    implementation=primitive_flood_fill,
    description="Flood fill from a seed using four-connectivity.",
))
register(PrimitiveSpec(
    name="paint_region",
    arguments=(ArgSpec("region", "region"), ArgSpec("colour", "colour")),
    result_type="grid",
    implementation=primitive_paint_region,
    description="Paint all cells in a region with a colour.",
))
register(PrimitiveSpec(
    name="extract_region",
    arguments=(ArgSpec("region", "region"), ArgSpec("pad", "int", required=False, default=0)),
    result_type="grid",
    implementation=primitive_extract_region,
    description="Extract the bounding box grid for a region.",
))
register(PrimitiveSpec(
    name="trim_background",
    arguments=(
        ArgSpec("pad", "int", required=False, default=0),
        ArgSpec("colour", "colour|str", required=False, default=None),
    ),
    result_type="grid",
    implementation=primitive_trim_background,
    description="Trim uniform background rows/columns and optionally retain padding.",
))
register(PrimitiveSpec(
    name="place",
    arguments=(
        ArgSpec("source", "grid"),
        ArgSpec("position", "position"),
        ArgSpec("mode", "str", required=False, default=None),
        ArgSpec("target", "grid", required=False, default=None),
    ),
    result_type="grid",
    implementation=primitive_place,
    description="Place one grid onto another.",
))
register(PrimitiveSpec(
    name="map_cells",
    arguments=(ArgSpec("region", "region"), ArgSpec("lambda", "lambda")),
    result_type="grid",
    implementation=primitive_map_cells,
    description="Apply a lambda to every cell in a region.",
))
register(PrimitiveSpec(
    name="region_all",
    arguments=(),
    result_type="region",
    implementation=primitive_region_all,
    description="Return a region covering the entire grid.",
))
register(PrimitiveSpec(
    name="region_where_colour",
    arguments=(ArgSpec("colour", "colour"),),
    result_type="region",
    implementation=primitive_region_where_colour,
    description="Return a region mask for a specific colour.",
))
register(PrimitiveSpec(
    name="region_from_bbox",
    arguments=(ArgSpec("top", "int"), ArgSpec("left", "int"), ArgSpec("bottom", "int"), ArgSpec("right", "int")),
    result_type="region",
    implementation=primitive_region_from_bbox,
    description="Construct a rectangular region from coordinates.",
))
register(PrimitiveSpec(
    name="region_outline",
    arguments=(ArgSpec("region", "region"),),
    result_type="region",
    implementation=primitive_region_outline,
    description="Return the boundary pixels of a region.",
))
register(PrimitiveSpec(
    name="region_expand",
    arguments=(ArgSpec("region", "region"), ArgSpec("radius", "int", required=False, default=1)),
    result_type="region",
    implementation=primitive_region_expand,
    description="Dilate a region using four-connectivity.",
))
register(PrimitiveSpec(
    name="detect_objects",
    arguments=(ArgSpec("connectivity", "int", required=False, default=4), ArgSpec("min_size", "int", required=False, default=1)),
    result_type="region_list",
    implementation=primitive_detect_objects,
    description="Detect connected components on the grid.",
))
register(PrimitiveSpec(
    name="select_object",
    arguments=(ArgSpec("selector", "str"), ArgSpec("hint", "int|colour|str", required=False, default=None)),
    result_type="region",
    implementation=primitive_select_object,
    description="Select a region from the detected objects list.",
))
register(PrimitiveSpec(
    name="push_region",
    arguments=(ArgSpec("region", "region"),),
    result_type="region_list",
    implementation=primitive_push_region,
    description="Push a region onto the object stack.",
))
register(PrimitiveSpec(
    name="pop_region",
    arguments=(),
    result_type="region",
    implementation=primitive_pop_region,
    description="Pop the most recent region from the object stack.",
))
register(PrimitiveSpec(
    name="majority_colour",
    arguments=(ArgSpec("region", "region"),),
    result_type="colour",
    implementation=primitive_majority_colour,
    description="Return the majority colour inside a region.",
))
register(PrimitiveSpec(
    name="count_cells",
    arguments=(ArgSpec("region", "region"),),
    result_type="int",
    implementation=primitive_count_cells,
    description="Count the number of cells within a region.",
))
register(PrimitiveSpec(
    name="compose",
    arguments=(ArgSpec("stages", "stage", variadic=True),),
    result_type="grid",
    implementation=primitive_compose,
    description="Execute nested stages sequentially.",
))
register(PrimitiveSpec(
    name="repeat",
    arguments=(ArgSpec("count", "int"), ArgSpec("stage", "stage")),
    result_type="grid",
    implementation=primitive_repeat,
    description="Repeat a stage a fixed number of times.",
))
register(PrimitiveSpec(
    name="if_equal",
    arguments=(
        ArgSpec("left", "any"),
        ArgSpec("right", "any"),
        ArgSpec("then_stage", "stage"),
        ArgSpec("else_stage", "stage", required=False, default=None),
    ),
    result_type="grid",
    implementation=primitive_if_equal,
    description="Branch on scalar equality.",
))
