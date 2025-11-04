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

## Phase 1 - Setup And Environment Preparation
**Objectives**
- Mirror the Kaggle offline runtime with a deterministic Python 3.11 / CUDA 12.1 stack, PyTorch 2.3, and Z3 4.12 using the process in `docs/ENV_SETUP.md`.
- Establish repository scaffolding (entrypoints, directories, configs) so later phases can plug in without touching the environment or logging substrate.

**Scope And Interfaces**
- Uses dependency manifests (`requirements.txt`, `environments/conda/environment.yml`) and device defaults from `docs/CONFIG_DEFAULTS.yaml`.
- Produces reproducible artefacts required by `docs/EVAL_PROTOCOL.md`, including environment snapshots, inventory manifests, and offline bundles.

### Workstream A - Environment Bootstrapping
- Validate hardware prerequisites (four GPUs, >=64 CPU cores, >=128 GB RAM) and record availability in `reports/hardware_inventory.md`.
- Build the local Conda or virtualenv via `bash scripts/setup_local_env.sh`; capture `pip freeze > reports/pip_freeze.txt` and `nvidia-smi > reports/gpu_info.txt` as prescribed in `docs/ENV_SETUP.md`.
- Pre-download Python wheels with `bash scripts/build_wheel_cache.sh`, store them under `vendor/wheels/`, and generate checksum manifests (`sha256sum`) for Kaggle uploads.
- Run `python scripts/check_gpu.py` to confirm CUDA compatibility and append results to `reports/setup_verification_<date>.md`.

### Workstream B - Repository And Execution Scaffold
- Create directory skeletons (`cache/`, `logs/`, `reports/`, `profiles/`, `vendor/wheels/`) with placeholder `.gitkeep` files to support logging expectations from `docs/DEBUG_PLAYBOOK.md`.
- Implement a minimal `run_eval.py` or CLI entry that loads config defaults, seeds RNGs, initialises logging (`logs/runtime.log`, `metrics.jsonl`), and performs a basic ARC input/output round-trip.
- Stub module packages (`arc/symbolic/`, `arc/ttt/`, `arc/llm/`, `arc/scheduler/`) with interface contracts and config hooks to unblock Phase 2 development.
- Ensure configuration loaders honour Kaggle path overrides (`/kaggle/working/Tri-ARC`, `/kaggle/temp/`) and mirror device maps from `docs/CONFIG_DEFAULTS.yaml`.

### Workstream C - Offline Assets And Data Packaging
- Stage ARC-AGI-2 datasets and ARC-Forge seeds per `docs/DATASETS.md`, verifying directory hashes prior to packaging.
- Run `python scripts/package_data.py --output dist/data_bundle.tar.gz` and capture the asset manifest with `python scripts/inventory_assets.py --json reports/offline_inventory_<date>.json`.
- Complete the third-party licence review for redistributed assets and store approvals in `docs/compliance/LICENCE_LOG.md`.

### Workstream D - Verification, Instrumentation, And Sign-Off
- Execute `python scripts/self_test.py --output reports/setup_verification_<date>.md` to validate imports, CUDA kernels, and Z3 availability.
- Run `python run_eval.py --split smoke --max_tasks 1` to exercise logging, metrics, and deterministic seeding; archive results under `reports/smoke_logs/`.
- Dry run `bash scripts/setup_kaggle_env.sh` in a clean container to prove that wheel caches and data bundles install without network access.
- Establish observability defaults: create `logs/smt/`, `logs/llm/`, and rotation policy for `logs/runtime.log` aligned with `docs/DEBUG_PLAYBOOK.md`.

**Milestones And Gating Checks**
| Checkpoint | Target Outcome | Evidence / Artefact |
|------------|----------------|---------------------|
| ENV-1: Local environment bootstrapped | Conda env, wheel cache, and GPU checks complete | `reports/pip_freeze.txt`, `reports/gpu_info.txt`, `vendor/wheels/manifest.sha256` |
| ENV-2: Repository scaffold | Entry script, module skeletons, and logging directories present | `run_eval.py`, `arc/*/__init__.py`, placeholder logs |
| ENV-3: Offline bundles assembled | Data archive and inventory ready for Kaggle upload | `dist/data_bundle.tar.gz`, `reports/offline_inventory_<date>.json` |
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
**Goals**
- Finalise DSL primitives capable of representing core ARC transformations while keeping search tractable.
- Implement interpreter and verification loop shared by symbolic solver and arbitrator.

**Key Tasks**
- Align DSL grammar with `docs/DSL_SPEC.md`; draft supporting documentation with examples.
- Implement interpreter translating DSL programs into grid operations (numpy-first for determinism).
- Build verification harness comparing candidate outputs across all examples.
- Create unit tests covering primitive semantics, failure modes, and negative checks.

**Dependencies**
- Grid representations defined during Phase 1; architecture interface hints from `docs/ARCHITECTURE.md`.

**Deliverables / Exit Criteria**
- DSL spec reviewed and versioned; interpreter passes unit suite and benchmarks within millisecond-scale per grid.
- Verification harness reports clear diffs for mismatches (feeds retry logic in later phases).
- Sample DSL programs solving canonical patterns committed as fixtures.

**Instrumentation & Observability**
- Log interpreter timings to `metrics.jsonl` to support later profiling.
- Capture failure traces for mismatched outputs to feed `docs/DEBUG_PLAYBOOK.md` workflows.

---

## Phase 3 - Core Symbolic Solver
**Goals**
- Build enumerative / heuristic search that discovers DSL programs solving easy-to-medium tasks within ~90 s.
- Integrate optional neural guidance using local weights, respecting offline constraints.

**Key Tasks**
- Implement search loop (DFS/IDDFS/beam) with pruning hooks; modularise heuristics per `docs/MODULES/SYMBOLIC.md`.
- Load heuristic model from `models/symbolic/heuristic.pt`, ensuring inference sticks to GPU0 (see `docs/CONFIG_DEFAULTS.yaml`).
- Instrument search frontier statistics and backtracking events for debugging.
- Validate solver on representative ARC tasks; document solve time, depth, and program cost.

**Dependencies**
- Phase 2 interpreter + verification; environment devices from Phase 1.

**Deliverables / Exit Criteria**
- Solve >50% of chosen smoke tasks in <120 s, emitting verified programs.
- Frontier pruning proven sound (no known solutions skipped in tests).
- Search exposes hooks for scheduler (pause/resume, progress metrics).

**Instrumentation & Observability**
- Emit `symbolic_frontier.log` and candidate statistics feeding the Issue Matrix in `docs/DEBUG_PLAYBOOK.md`.
- Record per-task search depth, branch factor in `metrics.jsonl`.

---

## Phase 4 - Modular Interfaces And Codebase Structure
**Goals**
- Define stable module contracts so symbolic, TTT, and LLM lanes share lifecycle patterns.
- Centralise task context, caching, and result packaging.

**Key Tasks**
- Introduce `SolverModule` base class with `initialize(task_ctx)`, `solve(budget)`, `status()` signatures aligned with `docs/ARCHITECTURE.md`.
- Refactor symbolic solver to implement the interface without regressions.
- Stub TTT and LLM classes returning "not implemented" while exercising scheduler hooks.
- Extend configuration system (`hydra` or YAML) to toggle modules and budgets (`docs/CONFIG_DEFAULTS.yaml`).

**Dependencies**
- Working symbolic solver (Phase 3); knowledge of upcoming modules from architecture doc.

**Deliverables / Exit Criteria**
- Symbolic module runs end-to-end through new interface and maintains baseline performance.
- Dummy modules integrate cleanly, enabling multi-lane orchestration tests.
- Config toggles allow enabling/disabling modules without code edits.

**Instrumentation & Observability**
- Ensure module lifecycle events are logged with provenance tags for arbitrator and scheduler.
- Update documentation in `docs/MODULES/` to reflect interface contract.

---

## Phase 5 - Shared Scheduler Implementation
**Goals**
- Coordinate module execution, enforce time budgets, and expose shared preprocessing cache.
- Prepare concurrency model for future multi-lane execution while supporting Config A' s single lane.

**Key Tasks**
- Implement task ingestion + feature extraction pipeline informed by `docs/SCHEDULER_POLICY.md`.
- Create preprocessing cache (grid tensors, symmetry descriptors) reusable across modules.
- Enforce soft/hard timeouts (90 s / 150 s) via cooperative checks; add cancellation hooks.
- Simulate multi-lane scheduling with dummy modules to validate priority queues and donations.

**Dependencies**
- Module interfaces (Phase 4), feature extraction details from `docs/ARCHITECTURE.md`.

**Deliverables / Exit Criteria**
- Scheduler processes task batches sequentially with accurate timing and logging.
- Timeout scenarios handled gracefully (solver stops, fallback triggered).
- Shared cache accessible and released between tasks.

**Instrumentation & Observability**
- Log allocation decisions, queue states, and budget donations in `logs/runtime.log`.
- Capture scheduler metrics (queue backlog, elapsed time) into `metrics.jsonl` for perf feedback loops.

---

## Phase 6 - Arbitration And Solution Verification
**Goals**
- Validate candidate outputs independently, manage pass@2 submissions, and ensure fallbacks.

**Key Tasks**
- Implement arbitrator per `docs/ARBITRATOR_RULES.md`: candidate intake, consistency verification, scoring, and diversity checks.
- Integrate fallback answer generation when no consistent candidate exists.
- Serialize final answers (JSON) matching `docs/EVAL_PROTOCOL.md` submission format.
- Log provenance, scores, and verification latency for each task.

**Dependencies**
- Interpreter/verifier (Phase 2), scheduler hand-off (Phase 5), scoring priors from config.

**Deliverables / Exit Criteria**
- Arbitrator double-checks symbolic solutions and rejects corrupted candidates reliably.
- Pass@2 emission produces one or two outputs for every task, never exceeding two.
- Fallback pathway documented and exercised in tests.

**Instrumentation & Observability**
- Append arbitration summaries to `metrics.jsonl`; store detailed decisions under `logs/arbitrator/`.
- Flag low-confidence tasks for follow-up, feeding workflows in `docs/DEBUG_PLAYBOOK.md`.

---

## Phase 7 - Performance Profiling And Safeguards
**Goals**
- Confirm runtime, memory, and logging adhere to `docs/PERF_BUDGET.md`; implement caches and guardrails.

**Key Tasks**
- Profile representative task batches (>=20) capturing per-module timing, GPU/CPU utilisation, and memory snapshots.
- Add feature, SMT clause, and interpreter result caches where profitable without breaking determinism.
- Implement memory hygiene (clear search structures, call `torch.cuda.empty_cache()`), and enforce global time tracking.
- Integrate alerting thresholds (timeout rate, SMT backlog) tied to scheduler adjustments.

**Dependencies**
- Full pipeline operational (Phases 1-6).

**Deliverables / Exit Criteria**
- Profiling report (`reports/perf_notes.md`) highlighting hotspots and resolutions.
- Average symbolic solve time <=120 s; peak GPU0 usage <=12 GB.
- Global run ETA estimate stays under 12-hour cap with buffer.

**Instrumentation & Observability**
- Persist profiler traces under `profiles/`; rotate logs per `docs/DEBUG_PLAYBOOK.md`.
- Update performance dashboards pulling from `metrics.jsonl`.

---

## Phase 8 - Experimentation And Evaluation Harness
**Goals**
- Automate batch evaluation, collect metrics, and guarantee reproducibility baselines.

**Key Tasks**
- Implement evaluation runner (`run_eval.py`) iterating over splits with configurable module sets (Config A default).
- Capture per-task metrics (pass@2 success, runtime, memory) and aggregate summaries aligned with `docs/EVAL_PROTOCOL.md`.
- Store artefacts: `outputs/pass2.json`, `reports/eval_summary.md`, `metrics.jsonl`, and run metadata (seeds, configs).
- Add scripts for ablations and regression (e.g., `tools/ablate.py`, smoke suites).

**Dependencies**
- Stable pipeline and logging (Phases 1-7).

**Deliverables / Exit Criteria**
- End-to-end run over evaluation split completes <12 hours with deterministic repeatability.
- Summary report includes accuracy, timeout rate, resource usage, and unresolved tasks list.
- Harness supports toggling modules (for future Configs B-E) without code changes.

**Instrumentation & Observability**
- Finalise log rotation and archival strategy; compress runs older than 24 h.
- Feed unresolved tasks into ARC-Forge pipeline per `docs/DATASETS.md`.

---

## Operational Checklist
- [ ] Environment snapshot updated and committed with date stamp.
- [ ] Smoke tests (`python run_eval.py --split smoke --max_tasks 5`) pass before pushing changes.
- [ ] `metrics.jsonl` and `logs/` cleansed of PII before sharing.
- [ ] Documentation synced: update relevant `docs/MODULES/*.md` after interface or budget changes.
- [ ] Regression suite rerun after every change affecting solver correctness or timing.

## Reporting Cadence
- **Daily**: Sync status against phase deliverables, review `metrics.jsonl` deltas, and flag issues via `docs/DEBUG_PLAYBOOK.md` templates.
- **Weekly**: Refresh profiling notes, update scheduler lookup tables, and ensure evaluation harness reproduces latest results.
- **Pre-release**: Freeze seeds/configs, regenerate asset manifest (`scripts/inventory_assets.py`), and archive run artefacts for Kaggle submission.
