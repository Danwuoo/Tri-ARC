# Tri-ARC Config A Development Plan

This plan turns the symbolic-only roadmap into an execution guide that anchors daily work, check-ins, and validation for the Tri-ARC baseline (Config A). It combines the eight development phases with operational requirements captured across `docs/ARCHITECTURE.md`, `docs/ENV_SETUP.md`, `docs/SCHEDULER_POLICY.md`, `docs/ARBITRATOR_RULES.md`, `docs/PERF_BUDGET.md`, `docs/DEBUG_PLAYBOOK.md`, and `docs/EVAL_PROTOCOL.md`.

## Purpose And Scope
- Deliver a deterministic, offline-ready symbolic solver that satisfies the 12-hour evaluation limit and pass@2 submission format.
- Lay modular foundations so TTT and LLM lanes can plug in later without rework.
- Produce reproducible artefacts (code, configs, logs, metrics) suitable for Kaggle offline submission and internal audits.

## Canonical References
- Architecture: `docs/ARCHITECTURE.md`
- Environment bootstrapping: `docs/ENV_SETUP.md`
- Scheduler policies and budgets: `docs/SCHEDULER_POLICY.md`, `docs/PERF_BUDGET.md`
- Arbitration behaviour: `docs/ARBITRATOR_RULES.md`
- Debugging workflows: `docs/DEBUG_PLAYBOOK.md`
- Evaluation and pass@2 protocol: `docs/EVAL_PROTOCOL.md`
- Configuration defaults: `docs/CONFIG_DEFAULTS.yaml`

## Milestone Overview
| Phase | Focus | Primary Outputs | Reference Docs |
|-------|-------|-----------------|----------------|
| 1 | Kaggle-compatible environment | Reproducible scaffold, offline dependency bundle | `docs/ENV_SETUP.md`, `docs/PERF_BUDGET.md` |
| 2 | DSL + interpreter | DSL spec, interpreter unit tests, verification harness | `docs/DSL_SPEC.md`, `docs/ARCHITECTURE.md` |
| 3 | Symbolic solver | Search engine with heuristics, sample solved tasks | `docs/MODULES/SYMBOLIC.md`, `docs/DEBUG_PLAYBOOK.md` |
| 4 | Modular interfaces | `SolverModule` contract, symbolic lane refactor, config toggles | `docs/ARCHITECTURE.md`, `docs/CONFIG_DEFAULTS.yaml` |
| 5 | Shared scheduler | Time-budgeted task runner with preprocessing cache | `docs/SCHEDULER_POLICY.md`, `docs/PERF_BUDGET.md` |
| 6 | Arbitration | Candidate verifier, pass@2 emitter, fallback logic | `docs/ARBITRATOR_RULES.md`, `docs/EVAL_PROTOCOL.md` |
| 7 | Performance hardening | Profiling report, caching, guardrails | `docs/PERF_BUDGET.md`, `docs/DEBUG_PLAYBOOK.md` |
| 8 | Evaluation harness | Batch runner, metrics ledger, reproducibility checks | `docs/EVAL_PROTOCOL.md`, `docs/ARBITRATOR_RULES.md` |

## Cross-Phase Guardrails
- **Offline compliance**: Package all wheels and assets upfront (`docs/ENV_SETUP.md`), validate no network calls via Kaggle dry run.
- **Determinism**: Seed `numpy`, `torch`, and Python RNG once per run; log seeds and device map from `docs/CONFIG_DEFAULTS.yaml`.
- **Performance envelope**: Enforce budgets from `docs/PERF_BUDGET.md`; schedule asserts cumulative ETA within 12 hours.
- **Observability**: Maintain `logs/runtime.log`, `metrics.jsonl`, profiler exports, and SMT dumps as specified in `docs/DEBUG_PLAYBOOK.md`.
- **Documentation hygiene**: Update module docs and changelog when behaviour, interfaces, or budgets shift.

---

## Phase 1 - Setup And Environment Preparation - Done
**Objectives**
- Mirror the Kaggle offline runtime with a deterministic Python 3.11 / CUDA 12.1 stack, PyTorch 2.3, and Z3 4.12 using the process in `docs/ENV_SETUP.md`.
- Establish repository scaffolding (entrypoints, directories, configs) so later phases can plug in without touching the environment or logging substrate.

**Scope And Interfaces**
- Uses dependency manifests (`requirements.txt`, `environments/conda/environment.yml`) and device defaults from `docs/CONFIG_DEFAULTS.yaml`.
- Produces reproducible artefacts required by `docs/EVAL_PROTOCOL.md`, including environment snapshots, inventory manifests, and offline bundles.

### Workstream A - Environment Bootstrapping
- Validate hardware prerequisites (four GPUs, >=64 CPU cores, >=128 GB RAM) and record availability in `reports/hardware_inventory.md`.
- Build the local Conda or virtualenv via `bash scripts/setup_local_env.sh`; capture `pip freeze > reports/pip_freeze.txt` and `nvidia-smi > reports/gpu_info.txt` as prescribed in `docs/ENV_SETUP.md`.
- Pre-download Python wheels with `bash scripts/build/build_wheel_cache.sh`, store them under `vendor/wheels/`, and generate checksum manifests (`sha256sum`) for Kaggle uploads.
- Run `python scripts/check_gpu.py` to confirm CUDA compatibility and append results to `reports/setup_verification_<date>.md`.

### Workstream B - Repository And Execution Scaffold
- Create directory skeletons (`cache/`, `logs/`, `reports/`, `profiles/`, `vendor/wheels/`) with placeholder `.gitkeep` files to support logging expectations from `docs/DEBUG_PLAYBOOK.md`.
- Implement a minimal `scripts/run_eval.py` entry that loads config defaults, seeds RNGs, initialises logging (`logs/runtime.log`, `metrics.jsonl`), and performs a basic ARC input/output round-trip.
- Stub module packages (`arc/symbolic/`, `arc/ttt/`, `arc/llm/`, `arc/scheduler/`) with interface contracts and config hooks to unblock Phase 2 development.
- Organise repository tooling so build utilities live under `scripts/build/` and ad-hoc diagnostics under `scripts/tmp/`.
- Ensure configuration loaders honour Kaggle path overrides (`/kaggle/working/Tri-ARC`, `/kaggle/temp/`) and mirror device maps from `docs/CONFIG_DEFAULTS.yaml`.

### Workstream C - Offline Assets And Data Packaging
- Stage ARC-AGI-2 datasets and ARC-Forge seeds per `docs/DATASETS.md`, verifying directory hashes prior to packaging.
- Run `python scripts/package_data.py --output dist/data_bundle.tar.gz` and capture the asset manifest with `python scripts/inventory_assets.py --json reports/offline_inventory_<date>.json`.
- Complete the third-party licence review for redistributed assets and store approvals in `docs/compliance/LICENCE_LOG.md`.

### Workstream D - Verification, Instrumentation, And Sign-Off
- Execute `python scripts/self_test.py --output reports/setup_verification_<date>.md` to validate imports, CUDA kernels, and Z3 availability.
- Run `python scripts/run_eval.py --split smoke --max_tasks 1` to exercise logging, metrics, and deterministic seeding; archive results under `reports/smoke_logs/`.
- Dry run `bash scripts/setup_kaggle_env.sh` in a clean container to prove that wheel caches and data bundles install without network access.
- Establish observability defaults: create `logs/smt/`, `logs/llm/`, and rotation policy for `logs/runtime.log` aligned with `docs/DEBUG_PLAYBOOK.md`.
- Publish DSL verification utilities (`arc/symbolic/dsl/verify.py`, `scripts/run_dsl.py`) with logs in `logs/verification/` and benchmarks under `reports/dsl_benchmarks_<date>.md`; back them with `tests/dsl/`.

**Milestones And Gating Checks**
| Checkpoint | Target Outcome | Evidence / Artefact |
|------------|----------------|---------------------|
| ENV-1: Local environment bootstrapped | Conda env, wheel cache, and GPU checks complete | `reports/pip_freeze.txt`, `reports/gpu_info.txt`, `vendor/wheels/manifest.sha256` |
| ENV-2: Repository scaffold | Entry script, module skeletons, and logging directories present | `scripts/run_eval.py`, `arc/*/__init__.py`, placeholder logs |
| ENV-3: Offline bundles assembled | Data archive and inventory ready for Kaggle upload | `dist/data_bundle.tar.gz`, `reports/offline_inventory_<date>.json`, `docs/compliance/LICENCE_LOG.md` |
| ENV-4: Smoke + Kaggle dry run | Self-test, smoke eval, and Kaggle setup script succeed | `reports/setup_verification_<date>.md`, `reports/smoke_logs/`, dry-run checklist |

**Risks And Mitigations**
- GPU driver or CUDA drift: maintain a pinned CUDA 12.1 image and rerun `scripts/check_gpu.py` after updates.
- Missing wheel or dependency in offline cache: enforce checksum review and add a CI smoke job that attempts an offline install using `vendor/wheels/`.
- Dataset bundle exceeds Kaggle quota: trim ARC-Forge subsets or split archives by priority per `docs/DATASETS.md`.

**Exit Criteria**
- Deterministic "hello world" ARC task runs offline with seeded RNGs, logging to `logs/runtime.log` and `metrics.jsonl`.
- Wheel cache, dataset bundles, compliance logs, and inventory manifests exist with validated checksums.
- Environment snapshot (`reports/setup_verification_<date>.md`, `reports/pip_freeze.txt`, `reports/gpu_info.txt`) is published to the team, enabling Phase 2 to begin without blockers.

---

## Phase 2 - DSL And Interpreter Implementation
**Objectives**
- Finalise DSL primitives that cover core ARC transformation families while keeping the symbolic search space tractable.
- Deliver a deterministic interpreter and verification loop shared by the symbolic solver, scheduler, and arbitrator lanes.

**Scope And Interfaces**
- Evolves the draft grammar, type system, and semantics in `docs/DSL_SPEC.md`, aligning operator contracts with interface guidance in `docs/ARCHITECTURE.md`.
- Consumes grid representations, logging scaffolds, and config defaults surfaced during Phase 1 (`arc/common/grid.py`, `docs/CONFIG_DEFAULTS.yaml`, `logs/runtime.log`).
- Surfaces instrumentation outputs to `metrics.jsonl`, `logs/runtime.log`, and verification reports that downstream lanes consume.

### Workstream A - DSL Specification And Governance
- Audit existing primitive and combinator definitions; align normative semantics with scheduler constraints from `docs/ARCHITECTURE.md` and capture approvals in `docs/changelog.md`.
- Formalise grammar expansions, typing rules, and operator contracts in `docs/DSL_SPEC.md`, describing preconditions, failure modes, and deterministic evaluation notes.
- Produce canonical examples (input grid, DSL program, output grid) for every primitive and combinator; persist them in `docs/DSL_PRIMER.md` and `fixtures/dsl/spec_examples/`.
- Document static validation rules covering arity, bounds, colour palette, and region guards, and publish them as a lint checklist for interpreter preflight.
- Stand up a governance workflow (semantic versioning, review template, release notes) that enforces spec changes to be ratified before interpreter updates merge.

### Workstream B - Interpreter Implementation
- Design the interpreter package layout (`arc/symbolic/dsl/interpreter.py`, `arc/symbolic/dsl/runtime/`) with pure evaluation cores, context objects, and deterministic RNG seeding hooks.
- Implement numpy-first execution for all primitives, reusing `arc/common/grid.py` validators for shape/type checks and raising structured `InterpreterFailure` objects.
- Support composite constructs (map, reduce, control forms) with explicit evaluation order, memoisation guards, and zero hidden global state.
- Integrate per-operator timing, coverage, and failure logging via the shared logging substrate so every run appends to `metrics.jsonl` and `logs/runtime.log`.
- Author micro-benchmarks and tracing scripts that benchmark hot primitives, publishing results to `reports/dsl_benchmarks_<date>.md` for scheduler calibration.

### Workstream C - Verification Harness And Test Suite
- Implement the verification harness (`arc/symbolic/dsl/verify.py`) that executes programs against train examples, returning success flags, diffs, and metadata for the arbitrator.
- Emit structured diff artefacts into `logs/verification/` and maintain roll-up summaries in `reports/verification_summary_<date>.md` for downstream analytics.
- Create fixture-driven unit tests under `tests/dsl/test_spec_examples.py` covering positive paths, error cases, and regression grids drawn from canonical examples.
- Add guard-rail validation tests in `tests/dsl/test_validation.py` stressing argument semantics, grid shapes, and deterministic guarantees, gating them in CI smoke runs.
- Wire the full DSL suite into the default CI invocation (`python -m pytest tests/dsl --maxfail=1 --durations=10`) and block spec merges on green results.

### Workstream D - Tooling And Fixtures For Downstream Consumers
- Ship the CLI utility `scripts/run_dsl.py` that loads JSON/YAML programs, executes them deterministically, and emits reports to stdout and `reports/dsl_runs/`.
- Curate a catalogue of exemplar programs demonstrating canonical ARC patterns; store fixtures in `fixtures/dsl/` and reference them from `docs/DSL_PRIMER.md`.
- Document interpreter APIs and scheduler touchpoints in `docs/ARCHITECTURE.md`, adding quick-start examples and troubleshooting notes for downstream teams.
- Extend `docs/DEBUG_PLAYBOOK.md` with DSL-specific logging guidance, metric field descriptions, and tips for inspecting structured failure objects.
- Ensure all tooling honours Phase 1 configuration defaults (seeds, cache paths, offline mode) and validates metrics output before returning success.

**Milestones And Gating Checks**
| Checkpoint | Target Outcome | Evidence / Artefact |
|------------|----------------|---------------------|
| DSL-1: Spec locked | Versioned grammar, primitives, and canonical examples reviewed and published | `docs/DSL_SPEC.md`, `docs/DSL_PRIMER.md`, `docs/changelog.md` entry |
| DSL-2: Interpreter core | Interpreter passes deterministic unit + benchmark suite with instrumentation enabled | `arc/symbolic/dsl/interpreter.py`, `tests/dsl/test_spec_examples.py`, `reports/dsl_benchmarks_<date>.md` |
| DSL-3: Verification loop | Harness generates diff artefacts and CI job succeeds on canonical tasks | `logs/verification/`, `reports/verification_summary_<date>.md`, CI run log |
| DSL-4: Downstream readiness | CLI + fixtures integrated; symbolic solver consumes interpreter API without adapters | `scripts/run_dsl.py`, `fixtures/dsl/`, `arc/symbolic/interpreter_adapter.py` |

**Dependencies And Coordination**
- Align instrumentation schema with Phase 1 logging defaults and Phase 5 scheduler metrics expectations.
- Coordinate with the Phase 3 symbolic solver team to prioritise primitive coverage and expose gaps early.
- Partner with the arbitration lane so verification metadata matches `docs/ARBITRATOR_RULES.md` requirements.
- Work with CI owners to schedule DSL suite runs in nightly smoke jobs and as a pre-merge requirement.

**Risks And Mitigations**
- DSL scope creep inflates the symbolic search space: require governance board approval and scheduler sign-off before adding new primitives.
- Non-deterministic numpy operations or hidden state leaks: centralise RNG seeding and enforce property tests that catch ordering differences.
- Instrumentation overhead slows evaluation: profile with micro-bench reports and gate verbose logging behind debug flags.
- Example coverage gaps lead to mis-specified semantics: maintain a backlog in `docs/DSL_PRIMER.md` and review with solver leads each sprint.

**Exit Criteria**
- `docs/DSL_SPEC.md` publishes a tagged release with canonical examples and a validation checklist that downstream tooling consumes.
- Interpreter implementation emits structured metrics, raises deterministic failures, and passes `python -m pytest tests/dsl`.
- Verification harness produces diff artefacts and `scripts/run_dsl.py` executes sample programs end-to-end with logs and metrics populated.
- Property-based and regression suites run green in CI, unblocking the Phase 3 symbolic solver integration.

---

## Phase 3 - Core Symbolic Solver
**Objectives**
- Engineer the enumerative and heuristic search pipeline described in `docs/MODULES/SYMBOLIC.md` so Config A consistently solves easy-to-medium ARC tasks within the budget envelope codified in `docs/PERF_BUDGET.md`.
- Operationalise neural guidance, e-graph rewriting, and DreamCoder-style compression without violating offline packaging or deterministic requirements from `docs/ENV_SETUP.md` and `docs/CONFIG_DEFAULTS.yaml`.
- Expose scheduler- and arbitrator-friendly telemetry (frontier metrics, checkpoints, partial programs) that downstream phases can consume without additional integration debt.

**Scope And Interfaces**
- Builds on the Phase 2 interpreter (`arc/symbolic/dsl/interpreter.py`, `arc/symbolic/dsl/verify.py`) and Phase 1 logging scaffold (`logs/runtime.log`, `metrics.jsonl`).
- Touches `arc/symbolic/search/`, `arc/symbolic/egraph/`, `models/symbolic/`, and configuration defaults for GPU affinity and budget knobs.
- Publishes candidate programs, progress updates, and diagnostics via the interfaces declared in `docs/ARCHITECTURE.md` and scheduler hooks from `docs/SCHEDULER_POLICY.md`.

### Workstream A - Search Architecture And Frontier Management
- Implement modular enumerators (DFS, IDDFS, beam) with consistent interfaces so heuristics and cutoffs are swappable per `docs/MODULES/SYMBOLIC.md`.
- Encode pruning heuristics, depth/width caps, and solver budgets drawn from `docs/PERF_BUDGET.md`, ensuring soft and hard stop conditions surface structured statuses to the scheduler.
- Persist frontier snapshots, explored program counts, and search seeds to `reports/symbolic/frontier_*.md` so debugging and replay match `docs/DEBUG_PLAYBOOK.md`.
- Integrate deterministic seeding, resume checkpoints, and pause/resume hooks to satisfy scheduler cooperative multitasking requirements.

### Workstream B - Neural Guidance And Rewrite Systems
- Package heuristic models (`models/symbolic/heuristic.pt`) with integrity checksums and load-time validation referenced in `docs/ENV_SETUP.md`; ensure inference pinning to GPU0 follows `docs/CONFIG_DEFAULTS.yaml`.
- Blend neural scoring with rule-based priors, calibrating beam ordering against evaluation fixtures and logging deltas for later ablations (`reports/heuristic_comparison_<date>.md`).
- Stand up the e-graph rewrite engine (pattern library, cost functions, saturation controls) described in `docs/MODULES/SYMBOLIC.md`, gating aggressive rewrites behind configuration flags.
- Automate DreamCoder-inspired compression runs that mine frequent fragments, file promotion requests under `docs/changelog.md`, and notify the DSL governance board before merging new primitives.

### Workstream C - Verification And Scheduler Integration
- Wrap Phase 2 verification (`arc/symbolic/dsl/verify.py`) into the solver loop so every emitted candidate carries pass/fail metadata in the schema expected by `docs/ARBITRATOR_RULES.md`.
- Implement incremental progress reporting (`solve_progress.jsonl`, gRPC/local queue) that the scheduler consumes for dynamic budget recalibration.
- Provide cooperative cancellation checkpoints and state export so the scheduler can suspend/resume search mid-task without violating determinism.
- Ensure failure diagnostics (counterexamples, first-difference coordinates) are serialised to `logs/symbolic/diagnostics/` for Phase 6 fallbacks and ARC-Forge ingestion (`docs/DATASETS.md`).

### Workstream D - Tooling And Operational Diagnostics
- Author CLI tooling (`tools/inspect_frontier.py`, `tools/replay_symbolic.py`) that replays search sessions, visualises e-graph rewrites, and conforms to `docs/DEBUG_PLAYBOOK.md` workflows.
- Extend `scripts/run_symbolic_bench.py` to execute curated smoke suites, storing timing curves and solution quality in `reports/symbolic_benchmark_<date>.md`.
- Add log parsers that condense `symbolic_frontier.log` into incident-ready summaries, integrating with the Issue Matrix templates.
- Update `docs/MODULES/SYMBOLIC.md` with operating modes, configuration tables, and troubleshooting notes after each milestone.

**Risks And Mitigations**
- Frontier or e-graph explosion exceeding memory budgets: enforce adaptive pruning thresholds, surface early warnings into scheduler telemetry, and run frequent stress tests with large-grid fixtures.
- Neural heuristic drift or offline weight corruption: freeze model hashes, add load-time validation tests, and maintain a rollback catalogue of previous heuristics.
- Determinism regressions when pausing/resuming search: instrument RNG seeding and include property-based tests that compare resumed vs fresh runs.
- Rewrite library regressions overriding correct programs: gate new rewrites behind feature flags, run ablation comparisons, and require arbitrator acceptance tests before activation.

**Exit Criteria**
- Symbolic solver clears >50% of the smoke suite within 120 seconds per task, logging verified DSL programs and counterexamples for failures.
- Search exposes pause/resume, budget consumption, and progress metrics compatible with Phase 5 scheduler integration.
- Neural guidance and rewrite systems are optional but shippable; toggling them on/off yields predictable performance differences recorded in benchmark reports.
- Tooling (`tools/inspect_frontier.py`, `scripts/run_symbolic_bench.py`) is documented and incorporated into daily/weekly reporting.

**Instrumentation & Observability**
- Emit structured search traces to `symbolic_frontier.log`, including frontier depth, beam width, and prune counts per tick.
- Append solver-level metrics (expansions per second, verified solutions, cache hit rates) to `metrics.jsonl` with module provenance tags.
- Upload replayable artefacts (checkpoints, e-graph dumps, heuristic deltas) under `logs/symbolic/` and archive according to `docs/DEBUG_PLAYBOOK.md`.

---

## Phase 4 - Modular Interfaces And Codebase Structure
**Objectives**
- Define the `SolverModule` lifecycle and shared contracts so symbolic, TTT, and LLM lanes follow the orchestration patterns outlined in `docs/ARCHITECTURE.md`.
- Centralise task context hand-off, caching, and result packaging to minimise bespoke glue across modules.
- Provide configuration toggles and documentation that let future Configs (B–E) slot in without refactoring Config A.

**Scope And Interfaces**
- Introduces base interfaces in `arc/core/module_base.py` (or equivalent), updates `docs/MODULES/*.md`, and wires module registration into `scripts/run_eval.py`.
- Depends on Phase 3 symbolic implementation and prepares the surface area for upcoming TTT/LLM modules while respecting defaults in `docs/CONFIG_DEFAULTS.yaml`.
- Touches orchestration utilities (`arc/core/context.py`, `arc/core/results.py`), scheduler/albitrator adapters, and logging hooks shared with Phase 1 infrastructure.

### Workstream A - Contract Definition And Base Class
- Draft lifecycle diagrams and method signatures (`initialize`, `prepare_task`, `solve`, `shutdown`) cross-checked with `docs/ARCHITECTURE.md` and reviewed with module owners.
- Implement base telemetry hooks (start/stop timestamps, status enums, error channels) that write to the shared logging sinks defined earlier.
- Provide capability flags (supports_partial_results, supports_resume, requires_gpu) so scheduler policies adapt at runtime.
- Write contract-focused unit tests ensuring subclasses raising `NotImplementedError` fail fast with actionable error messages.

### Workstream B - Symbolic Module Migration
- Wrap the Phase 3 solver inside the new base class, mapping progress callbacks, checkpoints, and diagnostics onto standardised events.
- Maintain feature parity by running the symbolic smoke suite before/after migration, logging diffs to `reports/module_interface_migration.md`.
- Stub adapters that let legacy entry points call into the new interface while deprecating older paths on a controlled timeline.
- Ensure configuration overrides (beam width, rewrite limit, heuristic flags) are exposed via module kwargs rather than global variables.

### Workstream C - Configuration Surface And Dependency Injection
- Extend the configuration system (Hydra or YAML) so modules register via declarative config blocks with validation against `docs/CONFIG_DEFAULTS.yaml`.
- Implement module registry discovery that instantiates modules, wires dependencies (e.g., interpreter handles), and enforces device affinity rules.
- Add CLI flags/env vars for enabling/disabling modules, adjusting budgets, and selecting mock implementations for CI smoke runs.
- Create schema validation tests to prevent misconfigured deployments from starting (missing weights, mismatched devices).

### Workstream D - Documentation And Onboarding
- Update `docs/MODULES/` with interface reference tables, lifecycle diagrams, and quick-start guides for new module authors.
- Publish onboarding walkthroughs showing how to implement a module against the base contract, including sample code snippets.
- Synchronise `docs/DEBUG_PLAYBOOK.md` with new module lifecycle events so operators know where to inspect hangs.
- Capture lessons learned in `docs/changelog.md`, noting required adjustments for future Config revisions.

**Risks And Mitigations**
- Interface churn causing merge conflicts: stabilise method signatures via lightweight RFCs and semantic versioning captured in `docs/changelog.md`.
- Hidden coupling to legacy globals: add integration tests that instantiate modules in isolation and fail if disallowed globals are accessed.
- Configuration sprawl: enforce schema validation, ship example configs with doc references, and gate merges on configuration lint.
- Documentation drift: pair doc updates with code changes via PR checklist items and reviewer sign-off.

**Exit Criteria**
- Symbolic solver runs end-to-end through the base interface with no regression in solve rate or telemetry.
- Dummy TTT/LLM modules implement the contract (returning stub results) and participate in scheduler dry runs.
- Configuration toggles enable/disable modules without code changes; misconfigurations fail fast with actionable logs.
- Updated documentation and onboarding assets are published and cross-linked from `docs/ARCHITECTURE.md`.

**Instrumentation & Observability**
- Module lifecycle events emit structured logs (`module_start`, `module_stop`, `module_error`) tagged with module and task IDs.
- `metrics.jsonl` includes per-module counters (invocations, successes, runtime) feeding scheduler and performance dashboards.
- Health checks and heartbeat events surface to the Issue Matrix templates for early detection of stalled modules.

---

## Phase 5 - Shared Scheduler Implementation
**Objectives**
- Build the scheduler described in `docs/SCHEDULER_POLICY.md` that coordinates module execution, enforces the time budgets from `docs/PERF_BUDGET.md`, and prepares for multi-lane expansion.
- Deliver reproducible feature extraction, caching, and prioritisation pipelines so Config A stays within the 12-hour evaluation limit.
- Provide inspection tooling and configuration levers so operators can audit scheduling decisions quickly.

**Scope And Interfaces**
- Extends preprocessing pipelines (`arc/scheduler/ingest.py`, `arc/scheduler/features.py`), the scheduling core (`arc/scheduler/core.py`), and shared caches.
- Consumes module contracts from Phase 4 and publishes allocation events to `logs/runtime.log`, `metrics.jsonl`, and arbitrator hooks.
- Coordinates with the SMT gatekeeper, performance budgets, and profiling guidance from `docs/PERF_BUDGET.md` and `docs/DEBUG_PLAYBOOK.md`.

### Workstream A - Ingestion And Feature Extraction
- Implement the feature extraction map (grid sizes, palette entropy, symmetry metrics) detailed in `docs/SCHEDULER_POLICY.md`, storing results in a reusable cache.
- Validate derived features against golden fixtures (`fixtures/scheduler/features/*.json`) and document their definitions in `docs/ARCHITECTURE.md`.
- Ensure ingestion respects determinism (consistent ordering, seeded randomness) and logs anomalies to `logs/scheduler/ingest.log`.
- Integrate data checks that abort scheduling if required task metadata is missing or malformed.

### Workstream B - Budget Allocation And Feedback Loops
- Encode initial budget lookup tables, soft/hard timeout ladders, and donation rules per `docs/SCHEDULER_POLICY.md`.
- Implement runtime feedback (success rates, runtime deltas) that adjusts future allocations, persisting snapshots to `reports/scheduler_budget_<date>.md`.
- Surface cooperative pause/resume requests to modules and ensure they honour budget expirations cleanly.
- Add safeguard logic that halts new tasks if the 12-hour global budget is at risk, alerting operators through the logging pipeline.

### Workstream C - Shared Cache And Resource Pools
- Build caching layers for preprocessed grids, symmetry descriptors, and module-specific warm starts, respecting memory ceilings from `docs/PERF_BUDGET.md`.
- Manage GPU/CPU worker pools, tracking utilisation and enforcing affinity rules encoded in `docs/CONFIG_DEFAULTS.yaml`.
- Establish cache eviction and invalidation policies when DSL libraries or models update, propagating changes to dependent modules.
- Provide instrumentation summarising cache hit rates and resource contention for performance audits.

### Workstream D - Simulation, Testing, And Tooling
- Develop scheduler smoke tests that simulate multi-lane execution with stub modules, asserting queue fairness, donation behaviour, and timeout handling.
- Create replay tooling (`tools/inspect_schedule.py`) that visualises allocations and routing decisions for specific tasks.
- Run scenario tests covering risk cases (long-running symbolic solve, simultaneous module completion, SMT backlog) and document outcomes in `reports/scheduler_simulations.md`.
- Integrate scheduler unit/integration tests into CI, blocking merges on regressions.

**Risks And Mitigations**
- Mis-calibrated budgets starving successful modules: leverage feedback loops and weekly profiling reviews to tune lookup tables.
- Cache invalidation bugs causing stale features: add versioned cache keys tied to DSL/library hashes and automate purge routines triggered by migrations.
- Pre-emption deadlocks or race conditions: adopt cooperative concurrency primitives, add fuzz tests that randomise event ordering, and instrument thread pools.
- Overhead from excessive telemetry: batch scheduler metrics, allow configurable sampling, and compress historical logs.

**Exit Criteria**
- Scheduler processes smoke and adversarial task batches, maintaining timing accuracy within ±5% of actual runtime.
- Budget donation, pre-emption, and cancellation paths are validated through automated tests and documented drills.
- Shared caches demonstrate measurable hit rates and stay within the memory ceilings defined in `docs/PERF_BUDGET.md`.
- Operators can inspect and explain allocation decisions using shipped tooling within minutes.

**Instrumentation & Observability**
- Scheduler appends structured events (allocation, donation, timeout, resume) to `logs/runtime.log` and dedicated JSONL streams.
- Metrics capture queue depth, per-module wait times, cache hits, and global budget consumption for dashboards.
- Simulation outputs and budget snapshots are archived to `reports/` for retrospective analysis.

---

## Phase 6 - Arbitration And Solution Verification
**Objectives**
- Implement the arbitrator blueprint from `docs/ARBITRATOR_RULES.md`, ensuring every candidate passes deterministic verification before inclusion in pass@2 submissions.
- Coordinate provenance tracking, scoring, and fallback pathways so Config A never emits more than two answers and always logs rationale.
- Provide tooling and documentation so operators can audit decisions and triage low-confidence tasks rapidly.

**Scope And Interfaces**
- Builds `arc/arbitration/` modules, integrates with the shared interpreter, scheduler outputs, SMT gatekeeper, and evaluation harness.
- Consumes module metadata and progress events from Phases 3–5 while emitting final answers in the format mandated by `docs/EVAL_PROTOCOL.md`.
- Updates documentation and playbooks for verification workflows, failure handling, and incident escalation.

### Workstream A - Verification Pipeline And Gatekeeping
- Wrap interpreter executions in sandboxed runners that validate every candidate across all examples, logging failure traces per `docs/ARBITRATOR_RULES.md`.
- Integrate SMT attestation for LLM programs, verifying tokens from `docs/SMT_GATEKEEPER.md` and rejecting candidates without proof.
- Support batched verification to control throughput while respecting CPU and memory budgets.
- Emit structured rejection reasons and counterexamples to `logs/arbitrator/verification/` for module feedback loops.

### Workstream B - Scoring, Voting, And Diversity
- Implement scoring calculators blending module priors, confidence signals, runtime penalties, and diversity bonuses as specified in `docs/ARBITRATOR_RULES.md`.
- Encode tie-breaking rules, low-confidence thresholds, and diversity heuristics that request alternates when necessary.
- Maintain a rolling success rate ledger feeding back into scheduler budgets and weekly reporting.
- Add regression tests that simulate conflicting candidates to ensure deterministic selection.

### Workstream C - Fallbacks, Packaging, And Compliance
- Build fallback strategies (template solvers, conservative guesses) triggered when no consistent candidate survives verification.
- Serialize outputs into `outputs/pass2.json` with metadata (module provenance, scores) required by `docs/EVAL_PROTOCOL.md`.
- Record run manifests (`reports/arbitration_summary_<date>.md`) detailing answers, fallbacks, and unresolved tasks for ARC-Forge escalation.
- Validate JSON schema and pass Kaggle submission dry runs to guarantee compliance.

### Workstream D - Telemetry, Tooling, And Incident Response
- Extend `docs/DEBUG_PLAYBOOK.md` with arbitrator-specific diagnostics and failure checklists.
- Provide CLI utilities (`tools/inspect_arbitrator.py`) to replay decision logs, inspect candidate scores, and regenerate submissions.
- Automate alerts for high rejection rates, fallback usage spikes, or verification latency breaches, surfacing notifications to runtime logs.
- Document escalation procedures and integrate with incident templates to track arbitration-related bugs.

**Risks And Mitigations**
- Verification bottlenecks causing backlog: parallelise executor pools, cache intermediate results, and tune SMT batch sizes.
- Score calibration errors leading to suboptimal pass@2 outputs: run controlled experiments, recalibrate thresholds, and review weekly with module owners.
- Fallback overuse masking upstream issues: instrument fallback triggers, require follow-up tickets, and add dashboards that highlight rising trends.
- Logging gaps hindering audits: enforce schema validation on decision logs and integrate checks into CI.

**Exit Criteria**
- Arbitrator processes smoke suite tasks, producing at most two outputs with full provenance and zero unchecked candidates.
- Decision logs can be replayed end-to-end to reconstruct scoring and selection steps within `tools/inspect_arbitrator.py`.
- Fallback pathways are exercised in tests, and incident playbooks capture remediation steps.
- Submission artefacts pass offline validation and align with `docs/EVAL_PROTOCOL.md` expectations.

**Instrumentation & Observability**
- Append arbitration summaries (scores, provenance, decision rationale) to `metrics.jsonl` with consistent schema.
- Store verification transcripts, SMT attestations, and fallback traces under `logs/arbitrator/` with daily rotation.
- Generate periodic dashboards (`reports/arbitrator_health_<date>.md`) summarising accuracy, fallback rates, and latency.

---

## Phase 7 - Performance Profiling And Safeguards
**Objectives**
- Validate runtime, memory, and logging adherence to the constraints in `docs/PERF_BUDGET.md`, instrumenting the entire pipeline for bottleneck diagnosis.
- Implement caches, guardrails, and hygiene routines that keep Config A comfortably inside the 12-hour and memory envelopes.
- Establish continuous profiling and alerting so regressions surface before evaluation runs.

**Scope And Interfaces**
- Exercises full-pipeline runs across representative task sets, leveraging scheduler telemetry, module metrics, and profiling tools enumerated in `docs/DEBUG_PLAYBOOK.md`.
- Introduces caching layers, resource throttles, and guardrails in modules and scheduler components without breaking determinism.
- Coordinates with logging infrastructure to ensure traces and metrics are collected, rotated, and archived efficiently.

### Workstream A - Baseline Profiling And Instrumentation
- Capture baseline performance using Nsight, PyTorch profiler, and custom timers; store reports in `profiles/` and `reports/perf_notes.md`.
- Instrument per-module timing, memory, and I/O metrics, ensuring consistent tags across `metrics.jsonl`.
- Benchmark solver variants (with/without heuristics, caching) and summarise findings for scheduler calibration.
- Validate profiling overhead stays within acceptable limits via smoke runs.

### Workstream B - Optimisation And Caching
- Introduce caches for interpreter results, symmetry descriptors, and SMT clauses, measuring hit rates and verifying determinism.
- Identify hotspots (rewrite evaluation, feature extraction) and implement targeted optimisations, documenting before/after metrics.
- Tune GPU/CPU resource allocation (stream priorities, batch sizes) in line with `docs/PERF_BUDGET.md`.
- Add adaptive logging levels to reduce I/O pressure in production runs.

### Workstream C - Guardrails, Alerts, And Hygiene
- Implement watchdog timers, timeout escalations, and memory guards that trigger graceful degradation instead of crashes.
- Automate log rotation, compression, and retention policies described in `docs/DEBUG_PLAYBOOK.md`.
- Configure alerts for KPI breaches (timeout rate, SMT backlog, cache miss spikes) and route them to operator dashboards.
- Ensure all guardrails respect deterministic execution by covering them with regression tests.

### Workstream D - Reliability Drills And Regression Testing
- Run stress scenarios (extended evaluation loops, worst-case tasks) weekly, capturing deviations in `reports/perf_regression_<date>.md`.
- Maintain a regression suite that compares current metrics against baselines, failing CI when thresholds regress.
- Coordinate with module owners to triage regressions, open follow-up issues, and document mitigations.
- Feed insights back into scheduler policies and module configs, keeping `docs/PERF_BUDGET.md` updated.

**Risks And Mitigations**
- Profiling noise leading to false positives: standardise task subsets, use statistical smoothing, and document measurement variance.
- Optimisations breaking determinism: gate changes behind feature flags and validate with repeat runs.
- Alert fatigue from noisy thresholds: calibrate detection logic, aggregate metrics, and review weekly with ops leads.
- Cache-induced memory leaks: instrument usage, add eviction policies, and include leak tests in CI.

**Exit Criteria**
- Comprehensive profiling reports identify hotspots with actionable remediation steps; follow-up fixes land or are tracked.
- Average runtime and memory metrics meet or beat budgets with a 10% buffer; alerts remain within configured thresholds.
- Guardrail mechanisms are tested and proven to prevent catastrophic failures during extended runs.
- Regression dashboards show stable or improving trends across the monitored KPIs.

**Instrumentation & Observability**
- Persist profiler artefacts and regression snapshots under `profiles/` and `reports/`, tagging them with commit hashes.
- Expand `metrics.jsonl` schema to include cache stats, alert counts, and guardrail activations.
- Provide weekly roll-ups summarising performance health to stakeholders.

---

## Phase 8 - Experimentation And Evaluation Harness
**Objectives**
- Ship the evaluation and experimentation harness defined in `docs/EVAL_PROTOCOL.md`, enabling deterministic batch runs, ablations, and reproducibility checks.
- Automate artefact management (metrics, logs, submissions) so Config A prepares Kaggle-compliant deliverables with minimal manual effort.
- Provide tools for comparative studies (module on/off, heuristic variants) to guide future Config development.

**Scope And Interfaces**
- Enhances `scripts/run_eval.py`, adds tooling under `tools/` for ablations and regression comparisons, and integrates with module/scheduler/arbitrator APIs.
- Leverages logging, metrics, and artefact storage conventions from prior phases to produce reproducible run folders.
- Coordinates with dataset management (`docs/DATASETS.md`) to schedule nightly/weekly evaluation suites.

### Workstream A - Evaluation Runner And Batch Orchestration
- Implement CLI and configuration plumbing that selects splits, task subsets, and module configurations per `docs/EVAL_PROTOCOL.md`.
- Support resumable runs by checkpointing progress, storing partial outputs, and respecting global time limits.
- Expose hooks for scheduler warm-ups, module preloading, and log directory initialisation.
- Add smoke and evaluation presets (`configs/eval/*.yaml`) with documented defaults in `docs/ARCHITECTURE.md`.

### Workstream B - Metrics, Reporting, And Dashboards
- Aggregate per-task metrics into summary reports (`reports/eval_summary.md`, `reports/eval_delta_<date>.md`) covering accuracy, runtime, resource usage, and fallback frequency.
- Generate comparative dashboards that show module contributions, solver variants, and trend lines across runs.
- Ensure `metrics.jsonl` entries are annotated with evaluation context (split, config version) for downstream analytics.
- Publish quick-look notebooks or scripts that plot pass@2 trajectories and highlight regressions.

### Workstream C - Reproducibility, Artefact Management, And Compliance
- Record run metadata (commit hash, config fingerprint, seeds, environment manifest) in `reports/eval_manifest_<date>.md`.
- Automate packaging of outputs (`outputs/pass2.json`), logs, and metrics into timestamped archives ready for Kaggle submission.
- Verify offline compliance by running dry runs with network disabled and comparing checksums against stored wheel/dataset manifests.
- Document the full reproduction script in `docs/EVAL_PROTOCOL.md`, ensuring newcomers can replicate results end-to-end.

### Workstream D - Regression Suites And Ablations
- Develop ablation tooling (`tools/ablate.py`, `tools/compare_runs.py`) that toggles modules, heuristics, and scheduler policies for controlled experiments.
- Schedule nightly smoke runs and weekly full evaluations, capturing trends in `reports/eval_history.md`.
- Integrate evaluation suites into CI (as optional long-running jobs) to detect regressions before releases.
- Feed unresolved tasks and failure cases into the ARC-Forge pipeline or module backlogs.

**Risks And Mitigations**
- Evaluation drift due to configuration changes: pin configs, version manifests, and alert when defaults change.
- Offline incompatibilities slipping through: run regular Kaggle notebook simulations and maintain a checklist tied to `docs/ENV_SETUP.md`.
- Artefact sprawl overwhelming storage: enforce retention policies, compress archives, and mirror critical artefacts to long-term storage.
- Metric misinterpretation: include definitions, confidence intervals, and context in reports to avoid erroneous conclusions.

**Exit Criteria**
- Full evaluation split completes within 12 hours, produces reproducible metrics, and generates Kaggle-ready submission files.
- Smoke, nightly, and weekly run cadences are automated with alerts on failure.
- Ablation tooling delivers clear comparative insights logged in `reports/eval_history.md`.
- Documentation and manifests enable another developer to reproduce a run without oral history.

**Instrumentation & Observability**
- Evaluation runs emit structured phase markers (ingest, scheduler, arbitration, wrap-up) to `logs/runtime.log`.
- Metadata, run manifests, and summaries are archived per run with checksums and retention tags.
- Dashboards and history reports track accuracy, runtime, and resource trends over time, flagging regressions proactively.

---

## Operational Checklist
- [ ] Environment snapshot updated and committed with date stamp.
- [ ] Smoke tests (`python scripts/run_eval.py --split smoke --max_tasks 5`) pass before pushing changes.
- [ ] `metrics.jsonl` and `logs/` cleansed of PII before sharing.
- [ ] Documentation synced: update relevant `docs/MODULES/*.md` after interface or budget changes.
- [ ] Regression suite rerun after every change affecting solver correctness or timing.

## Reporting Cadence
- **Daily**: Sync status against phase deliverables, review `metrics.jsonl` deltas, and flag issues via `docs/DEBUG_PLAYBOOK.md` templates.
- **Weekly**: Refresh profiling notes, update scheduler lookup tables, and ensure evaluation harness reproduces latest results.
- **Pre-release**: Freeze seeds/configs, regenerate asset manifest (`scripts/inventory_assets.py`), and archive run artefacts for Kaggle submission.
