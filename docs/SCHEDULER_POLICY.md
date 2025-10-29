# Scheduler Policy

The scheduler orchestrates Tri-ARC's three solving lanes (symbolic, TTT, LLM) plus the SMT gatekeeper. It converts quick task diagnostics into resource allocations, priority queues, and timeout configuration so every puzzle finishes inside the 12-hour envelope.

## Feature Extraction
- **Grid shape**: row and column counts, aspect ratio, sparsity.
- **Palette stats**: number of colours, entropy, dominant hues.
- **Object metrics**: connected component counts, size histogram, symmetry scores.
- **Temporal context**: historical solve time for similar tasks, module success rates.
- **Budget context**: remaining global wall-clock time and per-device utilisation.

These features are extracted once in the coordinator ingestion stage (see `docs/ARCHITECTURE.md`) and cached for scheduler decisions.

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
- The scheduler exposes introspection hooks for `docs/DEBUG_PLAYBOOK.md` so operators can trace allocation rationale.
- Integration points:
  - `docs/MODULES/SYMBOLIC.md` for depth, beam, and rewrite limits.
  - `docs/MODULES/TTT.md` for learning rate, step count, and augmentation recipes.
  - `docs/MODULES/LLM_CODEGEN.md` for batch size and temperature schedules.
