# ARC Thin Slice Development Plan

## Scope
Establish an end-to-end ARC solving skeleton with the minimum viable modules required for iterative development. The goal is to support offline execution on Kaggle notebooks and local workstations, using Qwen2.5-Coder-7B-Instruct as the standing LLM during this phase. Every stage ensures the system remains runnable, evaluable, and observable.

## Stage Breakdown

### Stage 1 — Environment Landing
- Lock down offline Kaggle and local conda/docker environments using the published dependency manifest.
- Verify GPU availability, CUDA drivers, Z3 installation, and packaged wheel caches.
- Produce an offline wheel/model weight inventory with completeness checks to guard against notebook outages.
- Deliverable: reproducible environment scripts + `smoke` test run logs.

### Stage 2 - Smoke Validation
- **Objective**: Prove that the Stage 1 environments are fully runnable by exercising GPU, SMT, and core package wiring using the automated smoke suite.
- **Tooling**:
  - `tri_arc.smoke` module powering targeted checks (CUDA visibility, Z3 solver round-trip, dataset presence, wheel cache inventory, logging probe).
  - `scripts/run_smoke.py` CLI to collect JSON/Markdown artefacts under `reports/smoke_logs/` with timestamped filenames per environment.
- **Execution Flow**:
  - Local: `python scripts/run_smoke.py --env local`.
  - Kaggle: `python scripts/run_smoke.py --env kaggle --wheel-root /kaggle/input/tri-arc-wheels`.
  - Reference runbook: `docs/RUNBOOKS/SMOKE_VALIDATION.md`.
- **Failure Handling**:
  - Tag root causes using `docs/ERROR_TAXONOMY.md` and capture remediation notes in the Markdown log.
  - Loop fixes into Stage 1 provisioning scripts (`scripts/setup_local_env.sh`, `scripts/setup_kaggle_env.sh`) and rerun until the suite is green.
  - Leverage `docs/DEBUG_PLAYBOOK.md` for module-level diagnostics when GPU or SMT probes fail.
- **Deliverables**:
  - Passing smoke logs (`<timestamp>_<env>_smoke.md/json`) for both environments committed under `reports/smoke_logs/`.
  - Updated provisioning artefacts reflecting any fixes uncovered during validation.

### Stage 3 — Data & Evaluation Loop
- Implement dataset loaders, evaluation split handling, and deterministic sampling.
- Build an evaluation harness that emits `pass2.json` and a summary report matching benchmark expectations.
- Deliverable: `eval.sh`/notebook cell that runs the harness offline and archives artifacts.

### Stage 4 — Architecture & Contract Draft
- Document module responsibilities, I/O schemas, concurrency model, and dataflow in `docs/SMT_GATEKEEPER.md` extension sections.
- Define DSL syntax, supported primitives, and serialization format for downstream modules.
- Deliverable: signed-off design doc excerpts with interface tables.

### Stage 5 — Module API Freeze
- Translate the contract into lightweight Python dataclasses / typed dicts for message passing.
- Stub out module entrypoints with logging-only implementations to verify wiring.
- Deliverable: skeleton package compiling with CI linting and type checks.

### Stage 6 — Symbolic Baseline
- Implement a shallow-depth symbolic search without e-graph enhancements, emitting DSL-compliant candidates.
- Ensure deterministic seeding and resource accounting hooks.
- Deliverable: module returning at least one candidate for reference puzzles within 10s.

### Stage 7 — TTT Baseline
- Integrate the TTT model with fixed-step adapter tuning; freeze weights for the thin slice.
- Provide grid predictions with confidence scores and log intermediate tensors for debugging.
- Deliverable: serialized adapter checkpoint + inference script callable from the scheduler.

### Stage 8 — LLM Candidate Generator
- Embed Qwen2.5-Coder-7B-Instruct (quantized) with prompt templates aligned to the DSL schema.
- Generate a bounded set of candidates; validate JSON schema before passing downstream.
- Add an LLM→SMT streaming verification path that validates each candidate inline before enqueuing it.
- Deliverable: offline prompt pack + sampler producing <=5 candidates per task in <60s.

### Stage 9 — SMT Gatekeeper Core
- Implement translation of core primitives to SMT queries with a 2s soft timeout per candidate.
- Classify solver outcomes (`sat`, `unsat`, `unknown`, `timeout`) and annotate with metadata.
- Deliverable: gatekeeper CLI that wraps candidates and outputs structured verdicts.

### Stage 10 — Arbitrator Skeleton
- Create a pipeline that normalizes candidate outputs, filters duplicates, scores fidelity, and emits the top two solutions.
- Integrate fallback heuristics when SMT verdict is `unknown`.
- Score using SMT pass status + module prior reliability + program length regularization with dedupe/equivalence checks.
- Deliverable: arbitrator module returning ordered candidate list + score explanations.

### Stage 11 — Scheduler & Resource Guardrails
- Configure feature-to-resource mapping tables, module budgets (90s soft / 150s hard), and timeout propagation.
- Implement pooled resource tracking with reallocation when modules finish early.
- Deliverable: scheduler logs evidencing enforcement across representative puzzles.

### Stage 12 — Telemetry & Debug Surfaces
- Wire structured logging, metrics emission, and failure taxonomy tags across modules.
- Build replay tooling to reproduce module sequences from archived traces.
- Deliverable: telemetry dashboard notebook + replay CLI covering at least one failure case.

### Stage 13 — Contribution Workflow
- Establish branching strategy, mandatory `smoke` + evaluation gates, and change-log template.
- Set up pre-commit hooks, lint/type/test automation, and PR checklist.
- Deliverable: CONTRIBUTING update + CI configuration with documented thresholds.

### Stage 14 — Thin Slice Sign-off
- Run full evaluation loop producing pass@2, mean latency, timeout rate, and VRAM peak metrics.
- Review dashboards, update change log, and circulate the readiness report for parallel module enhancement.
- Deliverable: signed evaluation packet + backlog of follow-on improvements.

## Parallelization Notes
- Maintain the evaluation harness and telemetry as shared dependencies; schedule work so they are ready before module deep dives.
- Symbolic, TTT, LLM tracks can iterate in parallel once the scheduler skeleton and contracts are stable (post Stage 5).
- Dedicate daily syncs to align on resource budgets and failure taxonomies; feed insights into ARC-Forge regression generation.

## Working Agreements
- No change merges without passing `smoke` + evaluation and updating the change log with metric diffs.
- Always log timeout adjustments or candidate count increases alongside compensating budget changes.
- Use failure classification to prioritize DSL, prompt, and training updates in subsequent cycles.
