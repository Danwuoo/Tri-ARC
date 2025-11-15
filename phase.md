# Symbolic Synthesis Remediation & Optimization Phases

Context from the latest module sweep:
- `tests/symbolic/test_integration_e2e.py::TestFallbackMechanisms::test_error_handling_on_invalid_grid` currently fails because `SymbolicSolver` returns `success` even when the input grids are jagged (`tests/symbolic/test_integration_e2e.py:299`) since `_build_examples` only copies grids without validating their shape or contents (`arc/symbolic/solver.py:922-936`).
- Running `pytest tests/symbolic/test_regression.py` hard-fails before any regression assertion because `_build_budget` never seeds a `beam_width`, yet the default strategy is `beam`, so `BeamSearchStrategy` raises (see `arc/symbolic/solver.py:951-960` and `arc/symbolic/search/enumerators.py:109`), leaving seventeen regressions untested (`tests/symbolic/test_regression.py:38-211`).
- Documentation advertised in `docs/MODULES/symbolic_enhancements.md` references many files under `docs/symbolic/*.md` (e.g. lines 30-465), but the `docs/` tree has no such directory, so those links are all broken.
- Optimization features such as ILP/CP-SAT e-graph extraction are only stubs—the code logs `TODO` and silently falls back to A* (`arc/symbolic/egraph/extractor.py:73-118`) even though the enhancements doc promises multi-algorithm extraction for cost-optimal results.

The following phases sequence the repair and optimization work so that critical correctness issues are addressed before deeper enhancements.

## Phase 1 – Correctness Hardening & Task Validation
**Goal:** make the solver return truthful statuses and pass the failing integration test by validating inputs before search starts.

1. **Grid/task sanitisation pipeline**
   - Add structural validation (rectangularity, min example count, consistent dimensions) inside `_build_examples` before generating `TrainingExample` objects (`arc/symbolic/solver.py:922-940`).
   - Normalize or reject malformed grids by returning an early `failed` status with diagnostics rather than letting the search treat garbage data as a solved task.
   - Backfill fixtures in `tests/symbolic/test_integration_e2e.py` to assert both the failure status and the emitted telemetry for invalid grids (`tests/symbolic/test_integration_e2e.py:299-321`).
2. **Status plumbing & diagnostics**
   - Introduce a dedicated error path that sets `summary["status"]` to `failed`/`no_solution` when validation fails, and capture the offending example metadata via `_write_diagnostics`.
   - Ensure coordination and library managers receive the failure feedback (see hooks at `arc/symbolic/solver.py:874-905`) so other lanes can react appropriately.

**Exit criteria:** `pytest tests/symbolic/test_integration_e2e.py` passes with the invalid-grid case reporting `failed` (or `no_solution`), and the solver never emits `success` without at least one validated example.

## Phase 2 – Regression Shielding & Configuration Defaults
**Goal:** unblock the regression suite and prevent similar configuration regressions.

1. **Beam search defaults & fallbacks**
   - Provide a safe default `beam_width` (e.g. configurable minimum of 8–16) when the user selects beam search but omits the width (`arc/symbolic/solver.py:951-960`).
   - Alternatively, auto-switch to DFS/IDDFS when `beam_width` is absent and log the downgrade so CI still exercises regressions.
   - Expand `tests/symbolic/test_regression.py` to assert that `SymbolicSolver(base_config)` automatically enables a valid search budget (`tests/symbolic/test_regression.py:24-70`).
2. **Regression gating job**
   - Create a lightweight `scripts/check_symbolic_regressions.py` wrapper (or a `pytest -m symbolic_regression` target) so CI always executes the previously skipped regression file.
   - Capture the current failure by adding a temporary xfail marker referencing this phase, then remove it once the defaulting logic lands.
3. **Result telemetry consistency**
   - Ensure `SolverResult.telemetry` always contains elapsed time and node counters, even when early validation failure short-circuits (protects assertions such as `result.telemetry.elapsed_s < 10.0` in `tests/symbolic/test_regression.py:63`).

**Exit criteria:** `pytest tests/symbolic/test_regression.py` passes without manual config tweaks, and CI includes this target so future search-strategy changes cannot silently disable regressions.

## Phase 3 – Search Optimization & E-graph Quality
**Goal:** deliver the optimization promises from `docs/MODULES/symbolic_enhancements.md` by implementing the missing extraction algorithms and instrumentation.

1. **Implement ILP & CP-SAT extraction backends**
   - Replace the placeholders in `arc/symbolic/egraph/extractor.py:73-118` with real formulations (PuLP/OR-Tools backed) that respect rewrite costs and e-class constraints.
   - Add configuration flags in `symbolic.egraph.extraction_method` to choose between `astar`, `ilp`, `cp_sat`, and introduce unit tests that assert parity across methods for small fixtures (`tests/symbolic/test_egraph_enhancements.py` can host these cases).
2. **Rule scheduling & saturation metrics**
   - Surface the tiered-rule statistics gathered in `EGraph._saturate` (hot/cold counters at `arc/symbolic/egraph/engine.py:182-231`) up to the solver summary so the evaluation harness can correlate rewrite costs with downstream accuracy.
3. **Benchmark & performance validation**
   - Extend `scripts/run_symbolic_evaluation.py` to accept `--extractor {astar,ilp,cp_sat}` and emit delta metrics (pass@k, rewrite counts) so optimization gains are measurable.

**Exit criteria:** selecting `extraction_method="ilp"` or `"cp_sat"` changes solver behaviour (no longer silently falling back), new tests cover those code paths, and evaluation reports include optimizer stats.

## Phase 4 – Documentation & Configuration Realignment
**Goal:** align published documentation with the actual repository layout and configuration knobs so onboarding engineers do not follow dead links.

1. **Rehydrate the missing doc tree**
   - Either create the promised specs (`docs/symbolic/ir_spec.md`, `docs/symbolic/library_spec.md`, etc.) or update `docs/MODULES/symbolic_enhancements.md:30-465` to point at the existing `docs/MODULES/symbolic/*.md` files.
   - Add a simple link-check script (or a `tox` doc job) that fails CI when a referenced Markdown path does not exist.
2. **Configuration reference cleanup**
   - Consolidate the duplicated path `docs/docs/symbolic/configuration.md` into a single authoritative location and link it from `docs/MODULES/SYMBOLIC.md` and the README.
3. **Communicate new defaults**
   - Document the new beam search default/fallback behaviour and input-validation expectations so downstream modules know how statuses change.

**Exit criteria:** `rg "docs/symbolic/" -n docs` returns zero matches, every reference resolves locally, and the configuration guide matches the actual schema returned by `symbolic.default_config`.

---

**Recommended verification cadence**
1. Phase 1 & 2: `pytest tests/symbolic/test_integration_e2e.py tests/symbolic/test_regression.py`.
2. Phase 3: add targeted unit tests plus `scripts/run_symbolic_evaluation.py --preset regression --extractor {astar,ilp,cp_sat}`.
3. Phase 4: run the doc link checker and regenerate any documentation index.

Tracking these phases in order keeps the module shippable while we layer in the promised optimizations.
