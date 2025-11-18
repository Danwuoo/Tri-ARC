# Symbolic Program Synthesis Module

The symbolic lane is the precision backbone of Tri-ARC. It searches a domain-specific language (DSL) for programs that exactly reproduce the provided ARC task examples and remain interpretable for post-hoc analysis.

## Responsibilities
- Enumerate and evaluate DSL programs under tight time budgets.
- Incorporate neural heuristics (NS-CEGIS) to steer search toward promising partial programs.
- Compress redundant candidates with e-graph equivalence saturation.
- Emit verifiably correct programs with execution traces for the arbitrator.

### Implementation Highlights (Phase 3)
- **Search budget orchestration**: `arc/symbolic/search/budget.py` tracks depth, node, and time ceilings with deterministic seeding. Strategies (`dfs`, `iddfs`, `beam`) live in `arc/symbolic/search/enumerators.py` and plug into the shared `SearchStrategy` base.
- **Solver coordination**: `arc/symbolic/solver.py` ties enumerators, heuristics, and verification together. It streams JSONL telemetry to `logs/symbolic/symbolic_frontier.log`, writes structured progress to `logs/symbolic/solve_progress.jsonl`, and emits Markdown frontier reports in `reports/symbolic/`.
- **Heuristic blend**: Rule-based scoring (`arc/symbolic/heuristics/rule_based.py`) complements the neural model loader (`arc/symbolic/heuristics/neural.py`). Configuration lives under the `symbolic.heuristics` block in `docs/CONFIG_DEFAULTS.yaml`, letting ablations toggle weighting without code edits.
- **E-graph rewriting**: `arc/symbolic/egraph/engine.py` provides rewrite saturation with built-in simplification rules (`arc/symbolic/egraph/rules.py`). Rewrite histories land in `logs/symbolic/egraph/` for post-hoc analysis. Fragment mining for DreamCoder-style compression is scaffolded in `arc/symbolic/egraph/compression.py`.
- **Tooling pipeline**: CLI helpers (`tools/inspect_frontier.py`, `tools/replay_symbolic.py`, `tools/compare_heuristics.py`, `tools/mine_dreamcoder.py`) surface search telemetry, calibration deltas, and fragment mining summaries, while `scripts/run_symbolic_bench.py` executes curated suites and produces benchmark summaries under `reports/symbolic_benchmark_<date>.md`.

## NS-CEGIS Loop
1. **Neural guidance**: A lightweight policy network ranks partial programs using task features (grid size, color histogram, object counts).
2. **Synthesis step**: The enumerator expands the highest-ranked partials by applying DSL production rules while respecting depth and cost limits.
3. **Counterexample check**: Synthesised programs are executed on the known examples; failures are logged as counterexamples.
4. **Learner update**: The neural model ingests counterexamples to refine its ranking, pruning low-potential branches early.
5. **Iteration** continues until a program satisfies all I/O pairs or the module budget expires.

## E-Graph Integration
- **Equivalence saturation** merges syntactically different but semantically identical sub-programs (e.g., commutative reorderings) to avoid redundant exploration.
- **Rewrite library** stores algebraic identities, symmetry rules, and DSL-specific simplifications discovered during prior solutions.
- **Cost-based extraction** selects the minimal-cost representative when multiple equivalents are found, improving interpretability.
- **Telemetry**: Rewrite histories are written as JSONL streams for replay via `tools/replay_symbolic.py --egraph-history logs/symbolic/egraph/egraph_history.jsonl`.

## DSL Interface
- **Inputs**: Normalised grid tensors, derived object graphs, task metadata, and the active DSL library snapshot.
- **Outputs**: Candidate programs expressed in the DSL, annotated with cost, complexity, and the examples they have been validated against.
- **Library evolution**: High-frequency program fragments from successful solutions are abstracted into new primitives via a DreamCoder-inspired compression pass. Promotions require consensus from ablation logs to avoid overfitting.

## Coordination With Scheduler And Arbitrator
- The scheduler sets depth limits, beam widths, and time caps based on task features. It can request greedy search, iterative deepening, or stochastic sampling modes.
- The module streams intermediate successes to the arbitrator as soon as they pass internal checks, enabling early termination if a high-confidence program emerges.
- When no exact solution is found, the module emits best-effort programs plus diagnostics that help generate adversarial training tasks.

## Performance Considerations
- Search frontiers are bounded to protect memory; low-scoring branches are discarded proactively.
- CPU-heavy operations (equivalence checks, rewrite rule application) run in parallel worker pools while GPU kernels handle neural scoring.
- Profiling targets mean frontier size, average rewrite hits, and counterexample density to prioritise optimisation.
- The symbolic solver appends per-task metrics to `solve_progress.jsonl` and `metrics.jsonl`. Use `tools/inspect_frontier.py --log logs/symbolic/symbolic_frontier.log` to triage large searches quickly.

## Configuration Notes
- Disable the neural heuristic for CPU-only environments by setting `symbolic.heuristics.neural.enabled: false` (the `configs/eval/smoke.yaml` preset applies this automatically so smoke tests run without a GPU).
- Keep `symbolic.telemetry.*` paths aligned with evaluation presets; the `run_eval.py` entry point will expand them under the active run directory.

## Planned Extensions
- Integrate scheduler feedback loops so failure analytics adjust rewrite priorities.
- Expand the rewrite set with automatically learned equivalences mined from the e-graph corpus.
- Explore symbolic-LLM co-design where the LLM proposes rewrite rules or heuristics for novel task families.

## SolverModule Contract Integration
- The symbolic lane now derives from the shared `SolverModule` base (`arc/core/module_base.py`), exposing lifecycle hooks (`initialize`, `prepare_task`, `solve`, `shutdown`) with structured telemetry. Instantiation is handled by `ModuleRegistry` (`arc/core/registry.py`), which injects the shared cache and metrics sink defined in `scripts/run_eval.py`.
- Capability flags (`supports_partial_results`, `supports_resume`, `requires_gpu`) are declared on the class and enforced during registry bootstrap; mismatched device affinities emit warnings for quick triage.
- `prepare_task` centralises cache hydration under `shared_cache["symbolic"][<task_id>]`, making per-task diagnostics and result summaries accessible to sibling lanes and the arbitrator without bespoke glue.
- `solve` returns a standard `ModuleResult`, tagging lane metadata, summary counters, and telemetry snapshots so downstream consumers can reason about success / failure states uniformly.
- Lifecycle events emit `module_start`, `module_stop`, and `module_error` records into the global metrics stream. These entries power the new observability dashboards and anchor the troubleshooting flows documented in `docs/operations/troubleshooting.md`.


## Enhancements (v1.0.0 - 2025-11-12)

The symbolic synthesis module has been comprehensively enhanced with advanced techniques for program search, optimization, and verification. See `docs/MODULES/symbolic_enhancements.md` for complete details.

### Key Enhancements

#### 1. IR Layer (Intermediate Representation)
- **Grid ↔ ObjectGraph ↔ DSL** bidirectional mappings
- Object-centric reasoning and decomposition
- Program sketch generation from I/O examples
- Implementation: `arc/symbolic/ir/`
- Documentation: `docs/MODULES/symbolic/decomposition.md`

#### 2. DSL Library Management
- Automatic fragment mining from successful programs
- Rule learning from equivalence examples
- A/B testing and versioning
- Usage-based pruning
- Implementation: `arc/symbolic/library/`
- Documentation: `docs/MODULES/symbolic/library.md`

#### 3. Enhanced E-graph
- Tiered rule application (hot/warm/cold)
- E-class analysis for early pruning
- Optimal extraction (ILP/CP-SAT/A*)
- Automatic rule discovery
- Implementation: `arc/symbolic/egraph/`
- Documentation: `docs/MODULES/symbolic/egraph.md`

#### 4. CEGIS & Verification
- Counter-example guided inductive synthesis
- Automatic counterexample minimization
- Invariant checking (color conservation, topology)
- Program repair for partial solutions
- Implementation: `arc/symbolic/verification/`
- Documentation: `docs/api/symbolic_verifier.md`

#### 5. SMT Gateway
- Formal verification using Z3/CVC5
- Batch and incremental verification
- Witness function generation
- BDD support for grid operations
- Implementation: `arc/symbolic/smt/`
- Documentation: `docs/api/symbolic_verifier.md`

#### 6. Symmetry & Normalization
- Canonical color relabeling
- Symmetry detection (reflection, rotation, dihedral)
- Quotient search over equivalence classes
- Step sequence normalization
- Implementation: `arc/symbolic/symmetry/`

#### 7. Advanced Search Strategies
- Sketch-guided synthesis with VSA
- Abstract interpretation for early pruning
- PCFG-based probabilistic enumeration
- Monte Carlo Tree Search (MCTS)
- Diversity control
- Implementation: `arc/symbolic/search/`
- Documentation: `docs/api/symbolic_synthesizer.md`

#### 8. Decomposition & Composition
- Object-centric task decomposition
- Parallel synthesis of commutative substeps
- Block-level operations (concatenation, tiling)
- Implementation: `arc/symbolic/decomposition/`

#### 9. Module Coordination
- Integration with TTT module (invariants, relations)
- Integration with LLM module (macros, sketches)
- Asynchronous message passing
- Failure feedback loops
- Implementation: `arc/symbolic/coordination/`
- Documentation: `docs/policies/orchestration.md`

#### 10. Engineering Infrastructure
- Semantic caching with LRU eviction
- Adaptive budget allocation
- Circuit breaker for fault tolerance
- Comprehensive telemetry
- Artifact management
- Implementation: `arc/symbolic/engineering/`
- Documentation: `docs/MODULES/symbolic/engineering.md`

#### 11. Evaluation Infrastructure
- Comprehensive metrics collection
- Ablation study support
- Baseline comparison framework
- Dashboard data generation
- Implementation: `arc/symbolic/evaluation/`

### Configuration

All enhancements are configurable via YAML. Example:

```yaml
symbolic:
  enabled: true
  device: "cuda:2"
  
  egraph:
    enabled: true
    rewrite_limit: 5000
    extraction_method: "ilp"
    
  cegis:
    enabled: true
    max_iterations: 10
    
  smt:
    enabled: true
    timeout_per_candidate: 2.0
    witness_functions:
      enabled: true
      
  symmetry:
    color_normalization: true
    symmetry_detection: true
    
  library:
    fragment_mining:
      enabled: true
    rule_learning:
      enabled: true
    pruning:
      enabled: true
```

See `docs/MODULES/symbolic/configuration.md` for complete configuration reference.

### Beam Search Defaults & Fallbacks

- `SymbolicSolver` samples the minimum beam width from `symbolic.beam_width_minimum`,
  `symbolic.min_beam_width`, or `symbolic.default_beam_width` (in that order), clamps
  it to an integer `>= 1`, and falls back to `16` if parsing fails.
- Whenever `search_strategy` resolves to beam search but `symbolic.beam_width` is
  absent, non-positive, or unparsable, that minimum takes effect automatically and
  the solver logs the enforced width per task.
- The enforced width also feeds the search budget, so downstream tools that read
  `solve_progress.jsonl` or module summaries see the exact fallback that was used.

### Input Validation & Status Semantics

- Tasks must provide at least one mapping-style training example with rectangular
  `input` and `output` grids (lists of lists or `Grid` objects). Non-iterable rows,
  ragged shapes, or missing grids raise `TaskValidationError`.
- Validation failures return `status: "failed"` with `reason: "invalid_task"` plus a
  `validation_errors` array describing the offending indices and grid roles.
- Before leaving `solve`, the module dispatches `invalid_task` feedback to TTT/LLM
  coordinators, ensuring no retry happens with the same payload until the producer
  fixes the input structure.

### Performance Impact

Expected improvements based on design goals:
- **Pass@2 Accuracy**: +5-10% (from 65% to 70-75%)
- **Average Solve Time**: -20-30% (from 120s to 85-95s)
- **Timeout Rate**: -15-20% (from 25% to 20-21%)
- **Memory Usage**: Stable (8-10GB)

### Usage

```python
from arc.symbolic import SymbolicSolver

# Initialize with enhancements
config = load_config("configs/symbolic/enhanced.yaml")
solver = SymbolicSolver(config)

# Solve task
result = solver.solve(task)

if result.status == "success":
    print(f"Found: {result.best_program.to_dsl_string()}")
    print(f"E-graph optimized: {result.metadata.get('egraph_optimized')}")
    print(f"SMT verified: {result.metadata.get('smt_verified')}")
```

### Testing

```bash
# Run all enhancement tests
pytest tests/symbolic/

# Run specific enhancement tests
pytest tests/symbolic/test_ir.py
pytest tests/symbolic/test_library.py
pytest tests/symbolic/test_egraph.py
pytest tests/symbolic/test_verification.py
pytest tests/symbolic/test_smt.py
```

### Evaluation

```bash
# Full evaluation with enhancements
python scripts/run_symbolic_evaluation.py --preset evaluation

# Ablation studies
python scripts/run_symbolic_evaluation.py --preset ablation-no-egraph
python scripts/run_symbolic_evaluation.py --preset ablation-no-witness
```

### Documentation

- **Getting Started**: `docs/MODULES/SYMBOLIC.md#usage`
- **Configuration**: `docs/MODULES/symbolic/configuration.md`
- **Troubleshooting**: `docs/operations/troubleshooting.md`
- **API Reference**: `docs/api/symbolic_synthesizer.md`
- **Documentation Hub**: `docs/MODULES/SYMBOLIC.md`

For subsystem-specific guidance (coordination, decomposition, e-graph, SMT, etc.),
see the curated set under `docs/MODULES/symbolic/` plus the corresponding
implementation reports in `docs/MODULES/symbolic/implementation/`.
- **Enhancements Overview**: `docs/MODULES/symbolic_enhancements.md`

### Migration

Enhancements are backward compatible. Existing code continues to work with default settings. To enable specific enhancements, update configuration as shown above.

### References

- Requirements: `.kiro/specs/symbolic-synthesis-enhancement/requirements.md`
- Design: `.kiro/specs/symbolic-synthesis-enhancement/design.md`
- Implementation: `arc/symbolic/`
- Tests: `tests/symbolic/`
