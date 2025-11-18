# Evaluation & Benchmarking Suite

Collects datasets, evaluation protocol, ablation plans, performance budgets, and prompt templates.

## Datasets & Benchmarks

Tri-ARC consumes three primary data sources: the official ARC-AGI-2 training set, the ARC-AGI-2 public evaluation set, and the internally generated ARC-Forge adversarial suite. This document outlines directory layouts, loading APIs, and synthesis workflows.

## ARC-AGI-2 Dataset Structure
- **Root layout** (relative to the repository workspace):
  ```
  data/
    arcagi2/
      train/
        task_xxxxx.json
      evaluation/
        task_yyyyy.json
  ```
- **File format**: Each JSON file contains `train` and `test` arrays. Entries provide `input` and `output` grids represented as nested integer lists.
- **Naming**: File IDs map to Kaggle task identifiers; keep them stable for reproducibility and cross-referencing.
- **Metadata cache**: During preprocessing, the coordinator writes per-task metadata (grid size, palette stats, object metrics) to `cache/meta/<task_id>.json` to avoid repeated parsing.

## Data Loading Interface
- Use `arc.data.DatasetLoader` to iterate deterministic task streams and materialise scheduler-ready payloads.
  - `iter_split(split="train")` yields dictionaries with `train_examples`, `test_examples`, and provenance metadata (split, checksum, relative path).
  - `load_task(split, task_id)` retrieves a single task with identical structuring.
- The loader calculates optional SHA-256 checksums, normalises example shapes, and preserves lazy file access to minimise disk I/O during long runs.
- Augmentations for TTT (symmetry flips, colour remaps) are defined in `arc/data/augment.py` to keep training logic separate from dataset parsing.

## ARC-Forge Generation Pipeline
1. **Seeding**: Start from failure cases logged by the arbitrator. Extract rules or primitives that caused difficulty.
2. **Program synthesis**: Use DSL templates to create new puzzle programs that emphasise the failure pattern (e.g., multi-step symmetry).
3. **Validation**: Automatically check generated tasks for human solvability heuristics (bounded size, limited colours) and ensure they are not duplicates.
4. **Filtering**: Run baseline solvers to keep only tasks that current Tri-ARC configurations fail or solve near timeout.
5. **Packaging**: Store generated tasks under `data/arc_forge/<date>/` with metadata describing the originating failure mode.

ARC-Forge tasks feed curriculum learning and ablation experiments. They remain separate from the official evaluation split to avoid contamination.

## Offline Deployment Considerations
- All datasets must be packaged with the final Kaggle notebook; no downloads are allowed once execution starts.
- Use `scripts/package_data.py` to assemble tarballs and verify checksums before upload.
- Disk quotas require pruning obsolete ARC-Forge batches; keep only the most informative subsets referenced by experiments.

## Provenance Logging
- Each task processed logs its origin (`arcagi2_train`, `arcagi2_eval`, `arc_forge`), version hash, and preprocessing timestamp.
- Logs integrate with this evaluation suite so reproduction steps can rehydrate identical data snapshots.

## Evaluation Protocol

Tri-ARC evaluation mirrors ARC-AGI-2 competition constraints: offline execution, a 12-hour wall-clock limit, and pass@2 scoring. Follow this guide to run reproducible assessments.

## Scoring
- **Metric**: pass@2 accuracy. A task is correct if either of the two submitted outputs matches the ground truth exactly.
- **Submission format**: For each task, emit a JSON list containing up to two output grids in the order chosen by the arbitrator (see `docs/policies/orchestration.md`).
- **Reporting**: Aggregate accuracy over the evaluation split, plus per-module solve rates and average verification latency.

## Offline Environment
- **Runtime**: Kaggle Notebook (or equivalent 4xGPU server) with no internet access.
- **Hardware assumption**: Up to four GPUs (A100 or L4 class), 48-64 CPU cores, and 96-128 GB system RAM.
- **Software stack**:
  - Python 3.11
  - PyTorch with CUDA support
  - Z3 binaries compatible with CUDA environment
  - Auxiliary tools (`torch.profiler`, Nsight CLI, `ripgrep`) bundled locally
- **Determinism**: Seed numpy, torch, and Python RNGs at startup. Record seeds in run metadata.

## 12-Hour Limit Management
- Scheduler monitors elapsed wall-clock time and adjusts per-task budgets (see `docs/policies/orchestration.md`).
- Profiling hooks capture average runtime per module; if estimates exceed the remaining budget, the coordinator reduces candidate generators and prioritises high-confidence solves.
- Periodic checkpoints (every 30 minutes) persist intermediate outputs so interrupted runs can resume without restarting solved tasks.

## Reproduction Steps
1. **Prepare environment**:
   - Clone the repository or unpack the competition bundle.
   - Verify data directories as described earlier in this handbook.
   - Install dependencies from `environment.yml` or `requirements.txt`.
2. **Launch evaluation**:
   - Execute `python scripts/run_eval.py --preset evaluation --split evaluation --run-id eval-<tag>`.
   - Use `--preset smoke` for quick sanity checks or `--resume-from <run_dir>` to continue an interrupted run.
   - The harness initialises scheduler, modules, the SMT gatekeeper, and the arbitrator, creating a dedicated run directory under `reports/eval_runs/<tag>`.
3. **Monitor progress**:
   - Tail `<run_dir>/logs/runtime.log` for scheduler allocations and arbitrator decisions.
   - Watch `<run_dir>/metrics.jsonl` (and the consolidated `reports/eval_summary.md`) for rolling accuracy, fallback usage, and latency.
   - Inspect `<run_dir>/run_state.json` for resumable checkpoints.
4. **Collect results**:
   - Kaggle-ready outputs are written to `<run_dir>/outputs/pass2.json`.
   - Reproducibility metadata lives in `<run_dir>/reports/eval_manifest_<tag>.md` alongside the copied `eval_summary.md` and `eval_history.md` snapshots.
   - Packaged artefacts (logs, metrics, outputs) are assembled automatically at `<run_dir>/archives/<run_id>_artefacts.zip`.
5. **Validate reproducibility**:
   - Re-run with identical seeds and confirm metric parity (difference <=0.1%).
   - Compare successive runs with `python tools/compare_runs.py <run_a> <run_b>`; deltas are also recorded in `reports/eval_delta_<run_id>.md`.

## Post-Evaluation Checks
- Run ablation suites with `python tools/ablate.py --preset smoke --split smoke` to isolate module contributions; consolidated results are written to `reports/ablations/`.
- Review `reports/eval_history.md` (rendered from the JSONL ledger) for trends across nightly smoke and weekly full runs.
- Generate side-by-side comparisons with `tools/compare_runs.py`, especially before shipping new configs.
- Feed unsolved tasks (listed in each run manifest) into the ARC-Forge generator pipeline to expand adversarial training datasets.

## Ablation Catalog

Tri-ARC evaluations include five canonical configurations to isolate module contributions and optimisation effects. Use this guide to plan, run, and report ablation experiments consistently.

## Standard Configurations
| ID | Modules Enabled | Optimisations | Purpose |
|----|-----------------|---------------|---------|
| A | Symbolic | Baseline DSL, no TTT, no LLM | Establish pure symbolic capability |
| B | Symbolic + TTT | Baseline DSL, no LLM | Measure gain from test-time adaptation |
| C | Symbolic + LLM | Baseline DSL, no TTT | Quantify benefit of generative proposals |
| D | Symbolic + TTT + LLM | Optimisations disabled | Assess raw collaboration without extras |
| E | Full Tri-ARC | Optimisations enabled (DSL growth, e-graph, SMT gating, caching) | Target production performance |

Optimisations include dynamic scheduler policies, DSL library growth, e-graph rewrites, SMT gatekeeping, cache warm-up, and quantised LLM weights.

## Experiment Checklist
1. **Prepare configs**: Copy `configs/base.yaml` (placeholder) and toggle modules via keys defined in `docs/CONFIG_DEFAULTS.yaml`.
2. **Seed control**: Use identical random seeds across runs for comparability.
3. **Dataset splits**: Evaluate on ARC-AGI-2 train subset (dev), evaluation set (public), and ARC-Forge challenge set.
4. **Runtime tracking**: Collect per-module runtime, SMT queue length, and GPU utilisation for each run.
5. **Error tagging**: Apply taxonomy from `docs/operations/troubleshooting.md` to all failures.

## Results Template
```
| Config | pass@2 (%) | Avg Time/Task (s) | Timeout Rate (%) | GPU Peak VRAM (GB) | Top Failure Tags |
|--------|------------|-------------------|------------------|--------------------|------------------|
| A      |            |                   |                  |                    |                  |
| B      |            |                   |                  |                    |                  |
| C      |            |                   |                  |                    |                  |
| D      |            |                   |                  |                    |                  |
| E      |            |                   |                  |                    |                  |
```
Follow with a short narrative summarising key deltas (e.g., B vs A shows +7% accuracy with +15 s runtime).

## Conclusion Template
```
### Key Findings
- [Headline results: e.g., Full Tri-ARC achieves 86.2% pass@2, +14.5% over symbolic baseline.]
- [Highlight trade-offs: e.g., LLM adds 18 s per task but halves symbolic failure rate.]

### Recommendation
- [Decide which configuration to adopt for production/testing.]

### Action Items
- [List follow-up work such as enriching DSL primitives or tuning scheduler weights.]
```

## Archival
- Store raw metrics under `experiments/ablations/<date>/<config>.json`.
- Commit summary reports (`reports/ablation_<date>.md`) referencing config IDs and seeds.
- Reference these results in release notes and project updates.

## Performance Budget

Tri-ARC must solve the full ARC-AGI-2 evaluation suite within 12 hours on four GPUs. This document codifies time quotas, memory ceilings, concurrency plans, caching practices, and observed bottlenecks.

## Time Allocation
| Component | Default per-task budget | Notes |
|-----------|------------------------|-------|
| Scheduler + preprocessing | 5 s | Feature extraction, cache warm-up |
| Symbolic solver | 90 s soft, 150 s max | Depth and beam width tuned per task |
| TTT adaptor | 90 s soft, 150 s max | Includes adaptation, ensemble inference |
| LLM generation + SMT | 90 s soft, 150 s max | Covers sampling, SMT filtering |
| Arbitration + logging | 10 s | Verification, scoring, telemetry |

Unspent budget is pooled and redistributed by the scheduler (see `docs/policies/orchestration.md`). Hard caps ensure cumulative time stays under the 12-hour limit.

## Memory Budget
| Device | Allocation |
|--------|------------|
| GPU0 | Symbolic neural heuristics, e-graph acceleration kernels (<=12 GB) |
| GPU1 | TTT model, adapters, optimiser state (<=18 GB with mixed precision) |
| GPU2 | LLM weights (4-bit) and KV cache (<=24 GB) |
| GPU3 | Overflow workspace for large SMT batches or parallel TTT runs (<=18 GB) |
| CPU RAM | Dataset cache, SMT contexts, logging buffers (<=64 GB) |

Regular memory snapshots ensure the LLM does not exceed VRAM; if it does, batch size is reduced automatically.

## Concurrency Layout
- **GPU binding**: Modules pin to dedicated devices to avoid contention. GPU3 can temporarily host a module when its primary device is saturated.
- **Thread pools**:
  - SMT workers: 16 CPU threads by default, scaled according to candidate backlog.
  - Data loader: 8 threads prefetched to keep TTT input queues full.
  - Logging: 2 asynchronous writers to avoid blocking arbitrator decisions.
- **Pipeline overlap**: While one task is in arbitration, the scheduler can start preprocessing the next task if GPU bandwidth is available.

## Cache Strategy
- **Feature cache**: Task metadata stored in RAM; invalidated only when DSL library updates change derived features.
- **Model cache**: TTT checkpoints and LLM KV caches reused when tasks share similar structure.
- **SMT clause cache**: Primitive encodings held in memory to speed repeated solver calls.
- **Disk cache**: Intermediate grids saved under `cache/grids/` to support debugging replays without recomputation.

## Known Bottlenecks
| Bottleneck | Symptoms | Mitigation |
|------------|----------|------------|
| SMT saturation | Solver queue grows >50 pending jobs | Reduce LLM candidate count, extend CPU thread pool, prioritise symbolic proofs |
| TTT divergence | Loss oscillates, exceeding soft timeout | Lower learning rate, constrain trainable parameters, enable early stopping |
| LLM VRAM spikes | CUDA OOM during sampling | Drop to 8 candidates per batch, prune KV cache, offload logits to CPU |
| E-graph explosion | Symbolic memory usage >10 GB | Tighten rewrite agenda, cap equivalence classes, flush low-value nodes |
| Logging backpressure | Arbitrator waits on disk writes | Switch to buffered logging, compress logs post-run |

## Monitoring
- Use `metrics.jsonl` for rolling averages of per-module runtime and memory.
- Enable Nsight sampling at 30-minute intervals to capture GPU utilisation profiles.
- Integrate alerts when any module exceeds its hard budget or when overall ETA threatens the 12-hour cap.

## Prompt Library

This library captures the prompt templates, sampling parameters, and anti-hallucination rules used by the local LLM module (see `docs/MODULES/LLM_CODEGEN.md`). Prompts are expressed in plain text with slot variables wrapped in `{{ }}`.

## Core Templates

### 1. Task Overview Prompt
```
You are Tri-ARC's DSL synthesis assistant. Think step-by-step inside the rationale field and emit strictly valid JSON.

Task ID: {{task_id}}
Focus: {{variant.focus}}

Reasoning Checklist:
{% for step in variant.instructions %}
  {{loop.index}}. {{step}}
{% endfor %}

Examples:
{% for example in examples %}
{{example.summary}}
{% endfor %}

Evaluation inputs (predict outputs under test_outputs):
{% for example in eval_examples %}
{{example.summary}}
{% endfor %}

Respond with a JSON object containing:
  "rationale": chain-of-thought explanation (no markdown)
  "dsl": DSL pipeline compliant with docs/reference/dsl_reference.md
  "confidence": float in [0, 1]
  "test_outputs": list of predicted grids matching the eval order
```

### 2. Variant Specialisations

| Name | Focus | Key Instructions |
|------|-------|------------------|
| `planner` | General pattern discovery | Contrast input/output deltas, translate reasoning into primitive-friendly stages, mentally verify before emitting DSL. |
| `symmetry` | Rotations/reflections/tiling | Identify axes, describe colour mappings under those transforms, compose reflect/rotate/crop primitives accordingly. |
| `contrast` | Object counting and palette rules | Track object counts, bounding boxes, and colour substitutions; prefer filter_objects/paint primitives and justify replacements. |

Each sampling round distributes requests proportionally across these variants so at least one covers symmetry-dominant puzzles.

## Sampling Settings
| Variant | Temperature | Top-p | Max tokens | Default share | Notes |
|---------|-------------|-------|------------|---------------|-------|
| planner | 0.70 | 0.90 | 512 | 4/8 | Baseline CoT reasoning, tends to generalise. |
| symmetry | 0.65 | 0.85 | 480 | 2/8 | Prioritises reflections/rotations and palette preservation. |
| contrast | 0.75 | 0.92 | 520 | 2/8 | Focused on object counting, foreground/background swaps. |

Set `prompt_variants` in the config to rebalance weights or override temperatures for experiment-specific runs.

Scheduler may override candidate counts based on budgets (see `docs/policies/orchestration.md`).

## Anti-Hallucination Rules
- **Interpreter-first rejection**: Programs that fail parsing, linting, or deterministic interpreter evaluation on training examples are tagged `note="failed_verification"` and never forwarded.
- **Primitive whitelist**: The prompt explicitly references `docs/reference/dsl_reference.md`. Unknown operators trip the validation step.
- **Structured output**: JSON parsing is strict; anything outside the schema counts as `json_missing` and is recorded for debugging.
- **Token budget guard**: Requests exceeding the `max_input_tokens` budget are truncated and surfaced via `truncated_prompt` metadata.
- **Virtual SMT tokens**: Every surviving candidate receives a deterministic token, so the arbitrator's SMT gatekeeper can continue to enforce module provenance.
- **Diversity filter**: DSL strings are hashed; duplicates (hash match) are skipped before verification to widen coverage.

## Prompt Versioning
- Store prompt revisions under `prompts/history/<date>/<name>.md`.
- Increment `prompt_version` in configuration files when templates change.
- Document rationale and observed effects in `reports/prompt_updates.md`.
