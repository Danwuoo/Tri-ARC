# Tri-ARC DSL Specification

Version: 0.3.0 (2025-11-07)

The Tri-ARC domain-specific language encodes grid transformations as composable, deterministic programs. This document defines the grammar, typing rules, primitive catalogue, and governance required to execute the DSL inside the symbolic solver, scheduler, and arbitrator lanes.

## Design Objectives
- **Grid-centric**: Operators consume and produce finite 2D grids whose cells encode palette colours `0-9`.
- **Deterministic**: Evaluation is pure and reproducible. All randomness is eliminated by construction; seeded utilities live behind deterministic wrappers.
- **Composable**: Higher-order combinators (map, repeat, if) operate on operators rather than raw code strings to keep search tractable.
- **Auditable**: Operator contracts, static validation, and governance checkpoints guarantee downstream components can reason about program behaviour.

## Core Grammar
```
<program>      ::= (pipeline <stage>+)
<stage>        ::= (apply <operator> <argument>*)
<operator>     ::= identifier matching a registered primitive or combinator
<argument>     ::= <literal> | <env-ref> | <tuple> | <lambda> | <stage>
<env-ref>      ::= @identifier                       ; binds to interpreter environment
<tuple>        ::= (tuple <argument> <argument>+)
<lambda>       ::= (lambda (<param>) <expression>)
<expression>   ::= literal | env-ref | tuple
                 | (if <expression> <expression> <expression>)
                 | (eq|ne|lt|le|gt|ge <expression> <expression>)
                 | (and|or <expression> <expression>)
                 | (not <expression>)
                 | (get <expression> <expression>)
```

- Identifiers are snake_case ASCII tokens.
- String literals must be double quoted (for example `"horizontal"`).
- Environment references use the `@` sigil (for example `@last_object`).
- Nested `(apply ...)` forms may appear inside combinators such as `compose` and `repeat`.
- Lambdas close over a single parameter; the interpreter binds dictionaries describing each visited cell when evaluating `map_cells`.

## Type System
The interpreter reasons over the following first-order types. Types are enforced during preflight validation and at runtime.

| Type Id | Description | Notes |
|---------|-------------|-------|
| `grid` | Immutable wrapper around a `np.ndarray[int16]` with shape `(rows, cols)` | See `arc/symbolic/dsl/types.Grid` |
| `region` | Boolean mask aligned with the current grid | Instances of `Region` ensure shape compatibility |
| `colour` | Integer in `[0, 9]` | Colour names map to their ids via `COLOUR_NAME_TO_ID` |
| `int` / `bool` / `str` | Scalar values | Strings must be ASCII |
| `position` | Tuple `(row, col)` with zero-based coordinates | Rows and columns respect grid bounds |
| `lambda` | First-order lambda receiving a single dictionary parameter | Used exclusively by `map_cells` |
| `stage` | Nested `Stage` value produced by the parser | Consumed by combinators (`compose`, `repeat`, `if_equal`) |
| `region_list` | Ordered list of regions | Produced by `detect_objects` |

Type conversions are explicit; there is no implicit casting between scalars and structured types.

## Evaluation Model
1. Programs execute inside an `ExecutionState` containing the current grid, environment bindings, object stack, and cached scalars.
2. Each stage looks up its operator in the primitive registry, validates argument arity and types, then executes against a cloned state. Side-effects are surfaced through environment updates (for example `last_region`, `last_value`).
3. Stage execution appends a `StageResult` containing the operator, evaluated arguments, duration, and resulting grid or value to an `ExecutionTrace`.
4. Determinism is guaranteed through pure numpy kernels, deterministic iteration order, and seeded RNG hooks for future stochastic extensions.
5. Failures raise `InterpreterFailure` with machine-parsable `code` and `details`. The interpreter logs the failure, emits a metric event, and aborts evaluation.

## Environment Conventions
The interpreter exposes stable bindings that downstream tooling may rely on:

| Key | Type | Producer |
|-----|------|----------|
| `current_grid` | `grid` | Always present; equals latest grid state |
| `last_grid` | `grid` or `null` | Previous grid prior to the most recent mutation |
| `last_value` | scalar | Scalars produced by the most recent operator |
| `last_region` | `region` | Region-producing primitives (`region_all`, `region_where_colour`, `select_object`, etc.) |
| `objects` | `region_list` | Populated by `detect_objects` |
| `last_object` | `region` | Selection primitives (`select_object`) |
| `object_stack_size` | `int` | Number of regions currently on the stack |
| `background_colour` | `colour` | Lazy-computed via `detect_objects` and `region_all` |

Users must reference environment bindings with the `@` prefix (for example `@last_region`).

## Static Validation and Lint Checklist
Interpreter preflight enforces the following rules before a program is executed. Failing any item raises `InterpreterFailure` with code `VALIDATION_ERROR`.

- [ ] **Arity**: each stage matches the registered primitive arity (including optional arguments with defaults).
- [ ] **Type safety**: argument types align with the operator contract. Regions must match the current grid shape, colours must lie in `[0, 9]`, and lambdas provide exactly one positional parameter.
- [ ] **Bounds**: numeric arguments obey grid limits. Tuples used as positions stay within `0 <= row < rows` and `0 <= col < cols`.
- [ ] **Region guards**: region arguments originate from earlier primitives in the same invocation or are validated explicitly via `Region.ensure_shape`.
- [ ] **Higher-order literals**: primitives that declare `<stage>` or `<lambda>` arguments must receive literal nested stages / lambda expressions; static lint rejects scalars, env references, or other placeholders before execution.
- [ ] **Object stack discipline**: stack operations (`select_object`, `push_region`, `pop_region`) may only operate when the stack is non-empty.
- [ ] **Deterministic seeds**: operators that rely on randomness (none in v0.2.0) must receive the interpreter seed; future extensions register through governance.
- [ ] **Instrumentation health**: metrics sink (`metrics.jsonl`) and runtime log exist and are writable before evaluation begins.

The interpreter ships a lint helper under `arc.symbolic.dsl.interpreter.validate_program` so callers can stop invalid programs ahead of execution.

## Primitive Catalogue

| Operator | Inputs | Output | Description | Side effects |
|----------|--------|--------|-------------|--------------|
| `identity` | n/a | `grid` | Returns the input grid unchanged. | none |
| `rotate` | `int steps` | `grid` | Rotates the grid by `steps * 90 deg` clockwise. | updates `last_grid` |
| `reflect` | `str axis` | `grid` | Mirrors the grid across `"horizontal"`, `"vertical"`, `"main_diagonal"`, or `"anti_diagonal"`. | updates `last_grid` |
| `transpose` | n/a | `grid` | Swaps rows and columns. | updates `last_grid` |
| `replace_colour` | `colour src`, `colour dst`, `[region]` | `grid` | Replaces occurrences of `src` with `dst`. Optional region restricts the update. | updates `last_grid` |
| `flood_fill` | `position seed`, `colour new_colour` | `grid` | Flood-fills from `seed` using four-connectivity and replaces the contiguous region with `new_colour`. | updates `last_grid` |
| `paint_region` | `region`, `colour` | `grid` | Paints all cells in the supplied region. | updates `last_grid`, sets `last_region` |
| `extract_region` | `region`, `[int pad]` | `grid` | Crops the minimal bounding box around the region with optional zero-padding. | sets `last_grid` to crop result |
| `trim_background` | `[int pad]`, `[colour|"auto"]` | `grid` | Removes uniform background rows/columns and optionally expands the retained content by `pad` cells per side. Auto mode infers the dominant colour. | updates `last_grid`, preserves background metadata |
| `place` | `grid source`, `position top_left`, `[str mode]`, `[grid target]` | `grid` | Places `source` onto the current grid (or optional `target`) at `top_left`. Modes: `"overwrite"` or `"transparent"` (skip zeros). | updates `last_grid` |
| `map_cells` | `region`, `lambda` | `grid` | Applies the lambda to each cell `(row, col, value)` in the region, expecting a colour result per invocation. | updates `last_value`, stores lambda metadata |
| `region_all` | n/a | `region` | Produces a region covering the entire grid. | sets `last_region` and pushes onto stack |
| `region_where_colour` | `colour` | `region` | Returns a region masking cells matching the colour. | sets `last_region`, pushes onto stack |
| `region_from_bbox` | `int top`, `int left`, `int bottom`, `int right` | `region` | Produces a rectangular region; bounds validated against the grid. | sets `last_region`, pushes onto stack |
| `region_outline` | `region` | `region` | Emits only the boundary cells of the supplied region using four-connectivity. | sets `last_region`, pushes outline |
| `region_expand` | `region`, `[int radius]` | `region` | Dilates the region by `radius` steps (four-connectivity) while respecting grid bounds. | sets `last_region`, pushes expanded mask |
| `detect_objects` | `[int connectivity]`, `[int min_size]` | `region_list` | Performs connected-component analysis over non-background cells. | populates `objects`, rebuilds object stack |
| `select_object` | `str selector`, `[scalar hint]` | `region` | Picks a region from the object stack (`"largest"`, `"smallest"`, `"index"`, `"colour"`). | sets `last_object`, `last_region`, pushes selection |
| `push_region` | `region` | `region_list` | Pushes a region onto the stack (for custom workflows). | updates stack |
| `pop_region` | n/a | `region` or `null` | Pops the top region from the stack. | updates stack, `last_region` |
| `majority_colour` | `region` | `colour` | Returns the most frequent colour inside the region. | sets `last_value` |
| `count_cells` | `region` | `int` | Counts cells within the region. | sets `last_value` |

All region-producing primitives ensure masks align with the current grid shape.

## Combinators and Control Operators

| Operator | Inputs | Output | Behaviour |
|----------|--------|--------|-----------|
| `compose` | `<stage>+` | `grid` | Executes each nested stage sequentially against a cloned state, returning the final grid. Metrics are emitted per nested stage. |
| `repeat` | `int count`, `<stage>` | `grid` | Executes the embedded stage `count` times. Counts must be non-negative. |
| `if_equal` | `<expression> left`, `<expression> right`, `<stage> then`, `[<stage> else]` | `grid` | Evaluates expressions, executes the matching branch, and returns its resulting grid. |

Combinators perform full validation of the nested stages before execution. Nested stage failures propagate to the parent stage with contextualised metadata (`repeat_iteration`, `compose_index`).

## Lambda Semantics
- `map_cells` receives a lambda with exactly one parameter (recommended name `cell`).
- For each `(row, col)` in the target region the interpreter binds a dictionary: `{ "row": r, "col": c, "value": current_colour }`.
- The lambda body may use the expression forms listed in the grammar. `get` is commonly used to access the dictionary (for example `(get cell "value")`).
- The lambda must return an integer colour `0-9`. Violations raise `InterpreterFailure(code="LAMBDA_ERROR")`.
- Lambdas execute in deterministic row-major order (top-left to bottom-right).

## Failure Modes
Every primitive emits structured failure codes so that solvers can diagnose issues quickly:

| Code | Trigger |
|------|---------|
| `VALIDATION_ERROR` | Static validation failed before execution |
| `OUT_OF_BOUNDS` | Position or region access exceeded grid bounds |
| `MISSING_ENV` | Requested environment key was absent |
| `PRIMITIVE_ERROR` | Primitive-specific runtime issue (details include operator name) |
| `LAMBDA_ERROR` | Lambda returned an invalid value or raised an exception |

All failures attach `stage_index`, `operator`, and evaluated arguments to the `details` payload.

## Instrumentation
- Each stage appends a JSON event to `metrics.jsonl` with keys `event="dsl_stage"`, `operator`, `duration_ms`, `result_type`, and optional `metadata`.
- Runtime logs emit structured messages using the root logging configuration established during Phase 1 (`logs/runtime.log`).
- The interpreter exposes trace objects so downstream tooling can perform richer analyses (coverage, timings, diffs).

## DSL Library Growth
The symbolic solver is designed to learn new primitives over time, accelerating search on future tasks. This process is inspired by the DreamCoder methodology, where high-frequency sub-programs from successful solutions are compressed into new DSL functions.

### Core Principles
- **Abstraction**: Reusable program fragments are identified and promoted to first-class primitives.
- **Distillation**: Only general-purpose, high-utility fragments are retained to prevent the library from becoming bloated with task-specific solutions.
- **Governance**: The promotion of new primitives is a governed process, requiring evidence of utility and review by the governance board.

### Candidate Identification
1. **Fragment Mining**: After a task is solved, the e-graph and execution traces are mined for frequently occurring sub-programs.
2. **Utility Scoring**: Candidates are scored based on their frequency, complexity reduction, and applicability across a diverse set of validation tasks.
3. **Generalization**: Candidate fragments are parameterized to create more general-purpose primitives.

### Promotion Workflow
1. **Proposal**: A candidate primitive is proposed via a pull request, including its implementation, documentation, and validation evidence.
2. **Review**: The governance board reviews the proposal for correctness, utility, and adherence to DSL design principles.
3. **Integration**: Upon approval, the new primitive is integrated into the DSL, versioned, and announced in the changelog.

This self-reinforcing cycle allows the DSL to evolve a rich library of operations tailored to the ARC domain, improving both search efficiency and the expressiveness of the language.

## Governance and Versioning
- Spec updates follow semantic versioning. Increments occur alongside entries in `docs/changelog.md` describing the change, review owner, and ratification timestamp.
- Any change to operator semantics, argument contracts, or evaluation order must land as a spec pull request that includes updated canonical examples and green DSL tests.
- Interpreter releases are gated on checkpoints DSL-1 through DSL-4 in `DEVELOPMENT_PLAN.md`. Downstream lanes consume tagged spec releases only.
- The governance board maintains a template for spec proposals (see `docs/changelog.md`), capturing motivation, design sketches, and validation evidence.

## Canonical Examples
See `docs/DSL_PRIMER.md` and the fixture set under `fixtures/dsl/spec_examples/` for end-to-end worked examples covering every primitive and combinator defined in this release.




## Intermediate Representation (IR) Layer

**Added in v0.4.0 (2025-11-12)**

The IR layer provides bidirectional mappings between grids, object graphs, and DSL programs, enabling object-centric reasoning and decomposition strategies.

### IR Architecture

```
Grid ←→ ObjectGraph ←→ DSL Program
  ↑         ↑              ↑
  └─────────┴──────────────┘
     Bidirectional Mappings
```

### ObjectNode Structure

Represents a connected component in a grid:

```python
@dataclass
class ObjectNode:
    id: int                          # Unique identifier
    region: Region                   # Set of (row, col) coordinates
    color: int                       # Primary color (0-9)
    bbox: BoundingBox               # (min_row, min_col, max_row, max_col)
    properties: Dict[str, Any]      # symmetry, connectivity, area, etc.
```

### ObjectGraph Structure

Represents a grid as a collection of objects with relationships:

```python
@dataclass
class ObjectGraph:
    nodes: List[ObjectNode]                    # All objects
    edges: List[Tuple[int, int, str]]         # (src_id, dst_id, relation_type)
    background_color: int                      # Background color
    canvas_shape: Tuple[int, int]             # (height, width)
    metadata: Dict[str, Any]                  # Additional metadata
```

**Edge Relation Types**:
- `"adjacent"`: Objects share a boundary
- `"contains"`: One object spatially contains another
- `"aligned_horizontal"`: Objects share same row range
- `"aligned_vertical"`: Objects share same column range
- `"same_color"`: Objects have the same color
- `"same_shape"`: Objects have similar shapes

### Grid-to-ObjectGraph Mapping

**API**: `GridToObjectGraphMapper.map_grid_to_objects(grid, connectivity=4, min_size=1)`

**Algorithm**:
1. Connected component analysis on same-color regions
2. Extract ObjectNode for each component
3. Compute properties (bbox, area, symmetry)
4. Detect spatial relationships
5. Build ObjectGraph

**Reconstruction**: `GridToObjectGraphMapper.map_objects_to_grid(object_graph, canvas_shape)`

Guarantees: `map_objects_to_grid(map_grid_to_objects(grid)) == grid`

### ObjectGraph-to-DSL Mapping

**API**: `ObjectGraphToDSLMapper.generate_sketch(input_graph, output_graph)`

Generates program sketches with holes based on I/O object graph analysis:

**Heuristics**:
- Object count change → `detect_objects` + `repeat` pattern
- Color change → `paint_region` or `recolor`
- Spatial transformation → `translate`, `rotate`, `reflect`
- Topological change → `flood_fill`, `draw_line`, `connect`

**Sketch Instantiation**: `ObjectGraphToDSLMapper.instantiate_sketch(sketch, hole_assignments)`

Fills holes to create complete programs.

### ProgramSketch Structure

```python
@dataclass
class ProgramSketch:
    stages: List[Union[Stage, Hole]]    # Mix of concrete stages and holes
    constraints: List[Constraint]        # Constraints on holes
    metadata: Dict[str, Any]            # Sketch metadata
```

### Hole Structure

```python
@dataclass
class Hole:
    id: str                    # Unique hole identifier
    type: Type                 # Expected type (e.g., "color", "direction")
    domain: Set[Any]          # Possible values
    constraints: List[Constraint]  # Additional constraints
```

### Integration with DSL

The IR layer extends the DSL with object-centric operations:

```python
# Example: Object-centric decomposition
input_graph = mapper.map_grid_to_objects(input_grid)
output_graph = mapper.map_grid_to_objects(output_grid)

# Generate sketch
sketch = dsl_mapper.generate_sketch(input_graph, output_graph)

# Synthesize program
program = synthesizer.synthesize_from_sketch(sketch, examples)

# Execute
result = interpreter.execute(program, input_grid)
```

### Performance Characteristics

- **Memory**: ObjectGraph uses 10-100x less memory than dense grid for sparse patterns
- **Computation**: Grid-to-ObjectGraph is O(H×W), ObjectGraph-to-Grid is O(N×A)
- **Suitable for**: Grids up to 30×30 (ARC-AGI-2 maximum)

### See Also

- Full IR Specification: `docs/symbolic/ir_spec.md`
- Implementation: `arc/symbolic/ir/`
- Tests: `tests/symbolic/test_ir.py`
