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
- **Tooling pipeline**: Two CLI helpers—`tools/inspect_frontier.py` and `tools/replay_symbolic.py`—surface search telemetry, while `scripts/run_symbolic_bench.py` executes curated suites and produces benchmark summaries under `reports/symbolic_benchmark_<date>.md`.

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

## Planned Extensions
- Integrate scheduler feedback loops so failure analytics adjust rewrite priorities.
- Expand the rewrite set with automatically learned equivalences mined from the e-graph corpus.
- Explore symbolic-LLM co-design where the LLM proposes rewrite rules or heuristics for novel task families.
