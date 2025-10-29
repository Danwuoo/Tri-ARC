# SMT Gatekeeper

The SMT gatekeeper filters candidate programs from the symbolic and LLM lanes by proving they satisfy all known input-output constraints before the arbitrator invests further time. It relies on Z3 to reason about grid transformations encoded in the Tri-ARC DSL.

## Objectives
- Translate DSL or Python-like candidate programs into solvable logical constraints.
- Dispatch verification queries to Z3 with tight time limits and capture model evidence.
- Provide actionable diagnostics when satisfiability checks fail or time out.

## I/O Constraint Modelling
1. **Grid encoding**: Encode each grid as a 2D array of integer variables with domains `[0, 9]`.
2. **Primitive semantics**: Expand DSL primitives using pre-defined rewrite templates (see `docs/DSL_SPEC.md`). For example, `rotate` remaps coordinates, `paint_region` asserts colour equality over a mask, and `compose` sequences constraints.
3. **Program unrolling**: Inline each pipeline stage into a symbolic state transition. Intermediate grids become fresh arrays linked by operator constraints.
4. **Example coupling**: For every provided I/O pair, assert that executing the program on the input grid yields the exact output grid. Combine all examples conjunctively to enforce strict consistency.
5. **Auxiliary invariants**: Add optional domain priors (palette conservation, object counts) to catch trivial contradictions sooner.

## Z3 Interface
- **Batching**: Candidates share a solver context per task. Common sub-expressions (e.g., repeated primitives) are cached and reused.
- **Timeouts**: Default solver timeout is 2 seconds per candidate. The scheduler may extend to 5 seconds for complex programs when slack exists.
- **Incremental solving**: Push/pop frames to test variations (e.g., alternative parameter instantiations) without rebuilding the entire constraint set.
- **Results**:
  - `sat`: Candidate passes; extract model to confirm intermediate values if debugging is requested.
  - `unsat`: Candidate rejected; capture unsat core to guide module retries.
  - `unknown`: Treat as failure; escalate to fallback heuristics or request simplified candidates.

## Failure Modes And Mitigations
- **Unsupported primitive**: If a program references a primitive lacking SMT semantics, flag the DSL library for updates and reject the candidate.
- **Solver timeout**: Reduce candidate complexity (prune optional steps) or split the program into smaller fragments for staged verification.
- **Arithmetic overflow**: All constraints use bounded integers; if overflow risks appear, clamp values and emit diagnostics to symbolic/LLM modules.
- **Constraint explosion**: Detect excessive node counts; trigger early abort and log for performance tuning (see `docs/PERF_BUDGET.md`).

## Telemetry
- Track per-candidate solve time, success rate by module, and failure reasons.
- Feed aggregated metrics back to the scheduler so SMT thread pools scale with demand.
- Store solver seeds and emitted constraints for reproducibility within the offline environment described in `docs/EVAL_PROTOCOL.md`.
