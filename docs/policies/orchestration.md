# Orchestration Policies

Consolidates scheduler, arbitrator, and SMT gatekeeper policies for quick reference.

## Scheduler Policy

The scheduler orchestrates Tri-ARC's three solving lanes (symbolic, TTT, LLM) plus the SMT gatekeeper. It converts quick task diagnostics into resource allocations, priority queues, and timeout configuration so every puzzle finishes inside the 12-hour envelope.

## Feature Extraction
- **Grid shape**: row and column counts, aspect ratio, sparsity.
- **Palette stats**: number of colours, entropy, dominant hues.
- **Object metrics**: connected component counts, size histogram, symmetry scores.
- **Temporal context**: historical solve time for similar tasks, module success rates.
- **Budget context**: remaining global wall-clock time and per-device utilisation.

These features are extracted once in the coordinator ingestion stage (see `docs/handbook/architecture.md`) and cached for scheduler decisions.

## Resource Mapping
| Feature pattern | Symbolic allocation | TTT allocation | LLM allocation | Notes |
|-----------------|--------------------|----------------|----------------|-------|
| Small grids (<=10x10) with high symmetry | 45% GPU0, deeper search | 20% GPU1 | 15% GPU2 | Symbolic search excels; LLM held in reserve |
| Large grids (>15x15) with noisy palette | 25% GPU0 | 45% GPU1, longer adaptation | 20% GPU2, higher temperature | TTT emphasised for pattern smoothing |
| Sparse objects, few colours | 40% GPU0 | 20% GPU1 | 25% GPU2 | Symbolic and LLM run in parallel; SMT quota increased |
| Historical symbolic failures | 20% GPU0 | 40% GPU1 | 30% GPU2, more candidates | Scheduler biases toward adaptive and generative routes |

Percentages express initial time and device slices; they can shift dynamically via donations from early finishes.

## Priority Queue Strategy
1. **Primary lane**: The module predicted to succeed fastest receives the highest priority queue slot and immediate access to cached features.
2. **Secondary lane**: Receives a staggered start (typically 5-10 seconds later) unless the task is flagged as high-risk, in which case all lanes start together.
3. **SMT throughput**: The gatekeeper is provisioned CPU threads proportional to the number of LLM candidates plus symbolic program branches pending verification.

Priority scores are recomputed whenever a module reports progress (e.g., new candidate found) or stalls (no update for a configurable interval).

## Timeout And Pre-emption Policy
- **Per-lane soft timeout**: Default 90 seconds; can extend to 150 seconds if global slack remains.
- **Hard timeout**: 240 seconds per task per lane. On breach, the lane is paused and lower-compute fallbacks trigger.
- **Back-off ladder**:
  1. Reduce search depth (symbolic) or learning rate (TTT) and resume with half the previous budget.
  2. Switch to cached heuristics or template solvers.
  3. If no consistent answer emerges, yield partial results to the arbitrator for mixed-module voting.
- **Pre-emption triggers**: Low GPU utilisation, verification backlog, or other lanes reporting confirmed solutions. Pre-empted lanes checkpoint state for potential resume on another task batch.

## Budget Feedback Loop
- Scheduler logs per-task actual runtimes, candidate counts, and verification latency.
- Aggregated metrics update the feature-to-budget lookup at the end of every 20 tasks.
- Confidence intervals on module success rates shrink or expand budgets. For example, if the symbolic lane solves >70% of tasks in a category, future tasks in that bucket get additional depth before TTT is launched.

## Implementation Notes
- Policies are encoded as YAML configuration with overrides loaded at runtime; hot updates do not require notebook restarts.
- The scheduler exposes introspection hooks for `docs/operations/troubleshooting.md` so operators can trace allocation rationale.
- Integration points:
  - `docs/MODULES/SYMBOLIC.md` for depth, beam, and rewrite limits.
  - `docs/MODULES/TTT.md` for learning rate, step count, and augmentation recipes.
  - `docs/MODULES/LLM_CODEGEN.md` for batch size and temperature schedules.

## Arbitrator Rules

The arbitrator consolidates outputs from the symbolic solver, TTT adaptor, and LLM code generator. It enforces strict example consistency, manages voting, and produces up to two answers per ARC task to satisfy pass@2 scoring.

## Responsibilities
- Validate candidate programs or grids against all provided input-output pairs.
- Score and rank consistent candidates using reliability priors and confidence signals.
- Select primary and secondary answers for submission, ensuring diversity when helpful.
- Generate provenance logs for evaluation and debugging (see `docs/operations/troubleshooting.md`).

## Consistency Verification
1. **Execution harness**: Run each candidate on every provided example. For symbolic and LLM programs, execution is done through the shared interpreter; TTT outputs are already concrete grids.
2. **Delta analysis**: Compare candidate outputs with ground-truth examples. Any mismatch disqualifies the candidate.
3. **Constraint traces**: Capture failure reasons (first mismatching coordinate, violated invariant) and forward them to the originating module for potential retries.
4. **SMT attestation**: LLM candidates must carry a success token from the SMT gatekeeper (see `docs/policies/orchestration.md`). Symbolic programs optionally carry e-graph proof summaries when rewrites were applied.

Only candidates that pass these checks enter the voting stage.

## Candidate Scoring
- **Module priors**: Each lane maintains a rolling success rate; higher rates increase the base score.
- **Confidence metrics**:
  - Symbolic: program complexity cost (lower is better) and e-graph stability.
  - TTT: ensemble variance and final loss magnitude.
  - LLM: log-probability of the emitted program and SMT solver slack.
- **Runtime penalty**: Candidates produced near the hard timeout incur a small penalty to prevent late, potentially unstable answers from overriding earlier confident solutions.
- **Diversity bonus**: Solutions with distinct transformation signatures (different DSL primitives, different grid edits) receive a bonus when building pass@2 submissions.

Scores are normalised to [0, 1] before ranking.

## Voting And Selection
1. Sort candidates by score.
2. Choose the top candidate as the primary answer if it exceeds a confidence threshold (default 0.65). If no candidate meets the threshold, select the highest-scoring option and flag the task as low confidence for analysis.
3. For pass@2:
   - If a second candidate exists whose score is within 10% of the primary and differs in transformation signature, emit it as the secondary answer.
   - Otherwise, run diversification heuristics (e.g., request an alternative from the next-best module) until a suitable secondary candidate is found or the budget expires.
4. Record the module provenance, score, and any supporting rationale strings for both answers.

## Conflict Resolution
- If two candidates tie within numerical tolerance, prefer the one from the module with higher recent success.
- If modules produce identical outputs, the arbitrator keeps a single entry but retains provenance of all contributing modules for traceability.
- If no candidate survives consistency checks, trigger fallback templates or return a conservative guess while logging a failure event.

## Logging And Telemetry
- Every decision includes timestamps, candidate identifiers, score breakdown, and verification latency.
- Logs feed `docs/handbook/evaluation_suite.md` dashboards and inform scheduler feedback loops.
- Failure cases automatically enqueue for ARC-Forge adversarial task generation (see `docs/handbook/evaluation_suite.md`).
- Structured decision summaries live under `logs/arbitrator/decisions/`, with verification traces in `logs/arbitrator/verification/` for counterexample replay.
- Daily markdown reports (`reports/arbitration_summary_<date>.md`) and health dashboards (`reports/arbitrator_health_<date>.md`) track fallback usage, confidence distribution, and latency trends.

## SMT Gatekeeper

The SMT gatekeeper filters candidate programs from the symbolic and LLM lanes by proving they satisfy all known input-output constraints before the arbitrator invests further time. It relies on Z3 to reason about grid transformations encoded in the Tri-ARC DSL.

## Objectives
- Translate DSL or Python-like candidate programs into solvable logical constraints.
- Dispatch verification queries to Z3 with tight time limits and capture model evidence.
- Provide actionable diagnostics when satisfiability checks fail or time out.

## I/O Constraint Modelling
1. **Grid encoding**: Encode each grid as a 2D array of integer variables with domains `[0, 9]`.
2. **Primitive semantics**: Expand DSL primitives using pre-defined rewrite templates (see `docs/reference/dsl_reference.md`). For example, `rotate` remaps coordinates, `paint_region` asserts colour equality over a mask, and `compose` sequences constraints.
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
- **Constraint explosion**: Detect excessive node counts; trigger early abort and log for performance tuning (see `docs/handbook/evaluation_suite.md`).

## Telemetry
- Track per-candidate solve time, success rate by module, and failure reasons.
- Feed aggregated metrics back to the scheduler so SMT thread pools scale with demand.
- Store solver seeds and emitted constraints for reproducibility within the offline environment described in `docs/handbook/evaluation_suite.md`.
