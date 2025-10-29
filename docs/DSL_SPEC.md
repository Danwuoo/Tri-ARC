# Tri-ARC DSL Specification

The Tri-ARC domain-specific language describes grid transformations as composable, interpretable programs. It balances expressive power with tractable search to serve both the symbolic solver and downstream verification.

## Design Principles
- **Grid-centric**: Programs operate on finite 2D grids with discrete colours drawn from `[0, 9]`.
- **Deterministic**: No randomness; identical inputs produce identical outputs.
- **Composable**: Higher-order combinators encourage reuse and enable library growth.
- **Verifiable**: Semantics are simple enough to translate into SMT constraints for formal checking.

## Syntax Overview
The language uses prefix notation with explicit arity. Informally:

```
<program>    ::= (pipeline <stage>+)
<stage>      ::= (apply <op> <args...>)
<op>         ::= primitive-id | derived-id
<args>       ::= literal | grid-ref | region-expr | expression
<expression> ::= (if <predicate> <expression> <expression>)
               | (map <lambda> <region-expr>)
               | (reduce <reducer> <region-expr>)
               | (compose <op>+)
```

Lambdas are first-order and close over a single cell binding `(lambda (cell) ...)`. Identifiers follow snake_case. Literals cover integers, colour ids, direction tokens, and boolean flags.

## Core Semantics
- **Grid representation**: A grid is `(rows, cols, data)` where `data` is a matrix over colours. Regions are subsets defined by predicates (e.g., object masks).
- **Execution model**: Pipelines evaluate stages sequentially, threading the grid state. Each stage applies an operator to produce a new grid or intermediate scalar.
- **Shape rules**: Operators must respect grid bounds. Attempts to read/write outside the grid raise verification errors and cause candidate rejection.
- **Referential transparency**: Operators do not mutate inputs in-place; they return new grid states, enabling equational reasoning.

## Built-In Primitives
### Grid And Object Access
- `identity`: return the input grid unchanged.
- `extract_region(region)`: crop the grid to the specified region.
- `paint_region(region, colour)`: fill the region with a single colour.
- `place(grid, position)`: paste a sub-grid at a given top-left coordinate.

### Geometry And Symmetry
- `rotate(grid, k)`: rotate by `k * 90` degrees.
- `reflect(axis)`: mirror across horizontal, vertical, or diagonal axes.
- `transpose`: swap row/column indices.

### Colour And Pattern Logic
- `replace_colour(src, dst)`: globally remap colours.
- `majority_colour(region)`: return the most frequent colour within a region.
- `flood_fill(seed, colour)`: flood from a seed coordinate using 4-connectivity.

### Control And Composition
- `if_equal(a, b, then_op, else_op)`: dynamic dispatch based on scalar equality.
- `repeat(count, op)`: iterate an operator a fixed number of times.
- `compose(op1, op2, ...)`: sequentially apply multiple operators.
- `map_cells(region, lambda)`: map a lambda over each cell in the region, returning an updated grid.

## Derived Primitives And Library Growth
- New primitives arise from frequent sub-programs mined after successful solves. A candidate is promoted when:
  - It appears in at least three distinct tasks.
  - Its inclusion reduces symbolic search depth in ablation comparisons.
  - It passes equivalence checks ensuring semantics match the originating program.
- Derived primitives store their definition so they can be inlined during SMT translation or when a solver lacks the extended library.

## Extension Rules
1. Maintain backward compatibility: existing programs must remain valid when new primitives arrive.
2. Provide metadata: each primitive defines arity, input types, output type, and side-condition predicates.
3. Supply rewrite candidates: additions should register potential equivalence rules (e.g., associativity) to enrich the e-graph.
4. Document test cases: every primitive includes canonical examples and counterexamples for regression testing.

## Example Programs
### Example 1: Paint Largest Object
```
(pipeline
  (apply find_largest_object)
  (apply paint_region last_object red))
```
- `find_largest_object` pushes the largest connected component onto an implicit object stack.
- `paint_region` consumes the object reference and paints it red.

### Example 2: Symmetry Completion
```
(pipeline
  (apply reflect vertical)
  (apply compose
    (apply overlay_half left)
    (apply enforce_palette))
```
- The program mirrors the grid vertically, overlays the left half onto the right, and enforces palette conservation.

## Equivalence And Rewrite Rules
- **Commutativity**: `(compose opA opB)` equals `(compose opB opA)` when both operate on disjoint regions. This rule is gated by a static side-condition proven via region analysis.
- **Idempotence**: `reflect(axis)` applied twice reduces to `identity`.
- **Fusion**: `replace_colour(a, b)` followed by `replace_colour(b, c)` rewrites to `replace_colour(a, c)` if colour `b` does not appear outside the first replacement region.
- **Neutral elements**: `compose(identity, op)` rewrites to `op`.

These rules seed the e-graph and SMT translator, shrinking search space and strengthening formal verification.

## Sample SMT Translation Sketch
1. Encode grids as integer matrices with dimension constraints.
2. Model primitives as sets of Horn clauses (e.g., rotation as coordinate remapping constraints).
3. Assert that executing the program on each input grid yields the matching output grid.
4. Query Z3 for satisfiability; a model confirms the program honours all examples.

## Usage Notes
- Keep programs concise; arbitrator scoring penalises excessive depth and unused intermediate results.
- Document custom primitives in `docs/MODULES/SYMBOLIC.md` and add regression tests before promoting them.
- When extending the DSL, update the SMT translation tables and the symbolic solver enum to preserve consistency across modules.
