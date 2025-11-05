# Tri-ARC Architecture Overview

Tri-ARC targets ARC-AGI-2 excellence under a strict offline, 12-hour evaluation window. The system is engineered for pass@2 accuracy above 85%, deterministic replay, and four-GPU self-containment with no external services.

## System Goals And Constraints
- **Benchmark alignment**: Solve ARC puzzles from a handful of input-output grids, delivering up to two verified answers per task.
- **Reproducibility**: All stochastic operations expose fixed seeds so Kaggle notebook runs can be reproduced byte-for-byte.
- **Resource ceiling**: Execution fits on four NVIDIA-class GPUs (A100 or L4 equivalents) alongside the competition CPU and RAM budget.
- **Offline deployment**: All weights, DSL assets, and solvers ship with the submission; nothing reaches out to the internet.

## High-Level Topology
1. **Task ingest** parses each puzzle, capturing grid dimensions, palette size, symmetry hints, and object statistics that drive downstream heuristics.
2. **Shared preprocessing** builds tensors, object graphs, and symmetry descriptors once per task and caches them for reuse across modules.
3. **Parallel solving lanes** run simultaneously:
   - **Symbolic Program Synthesis** searches the DSL with an NS-CEGIS loop guided by neural heuristics and e-graph saturation.
   - **Test-Time Training (TTT)** adapts a differentiable grid interpreter using self-supervised losses aligned with ARC invariants.
   - **Local LLM Code Generation** samples diverse candidate programs from a quantized offline LLM and submits them to SMT consistency checks.
4. **Arbitration core** executes candidates against the provided examples, filters inconsistent outputs, and ranks survivors by module reliability priors and confidence.
5. **Result emission** serializes the chosen answer, keeps a secondary fallback for pass@2, and logs provenance, runtime, and verification evidence.

## Data Flow Narrative
```
ARC task -> feature extractor -> shared cache
                                     |-> symbolic solver -> candidates -
                                     |-> TTT adaptor     -> candidates --\
                                     |-> LLM generator   -> candidates ---+-> consistency verifier -> arbitrator -> answers
```
Each lane consumes the shared cache, emits program hypotheses plus execution traces, and receives verifier feedback. When a lane fails to produce a consistent result within its budget, the scheduler can trigger bounded retries (e.g., deeper search, alternative prompts, or different augmentation seeds).

### Scheduler Feature Extraction
- The ingestion stage derives deterministic **grid statistics** (min/max rows and columns, mean cell count, sparsity) from every train example input/output pair so allocation rules can reason about scale quickly.
- **Palette statistics** aggregate across the same examples, tracking the unique colour count, entropy, dominant colour, and a histogram that powers palette-aware heuristics.
- **Symmetry metrics** compute horizontal, vertical, and rotational overlap scores (0–1 range) to identify tasks that favour symbolic solvers versus adaptive pipelines.
- Lightweight **object descriptors** estimate connected components, average component size, and the largest component footprint to approximate structural complexity without invoking the full DSL toolchain.
- Historical success rates per lane (`scheduler_history` metadata) are normalised into 0–1 signals so the feedback loop can bias allocations toward the most promising modules without bespoke per-task overrides.
- Features are cached under `cache/scheduler/features_cache.jsonl` via an LRU with TTL to guarantee reproducible reuse between runs while keeping within the performance budgets outlined in `docs/PERF_BUDGET.md`.

## Concurrency Model And Scheduling
- **Static partitioning** assigns GPUs 0-2 to symbolic, TTT, and LLM lanes respectively; GPU 3 remains a flex slot for SMT bursts or large-batch TTT updates. SMT solving and e-graph operations primarily use CPU threads.
- **Dynamic scheduler** scores task difficulty from metadata and allocates time slices per module; symmetry-heavy tasks bias toward symbolic time, while color-dense grids grant more budget to TTT and LLM lanes.
- **Cooperative timeboxing** gives each module an initial quota (for example 90 seconds). Early successes donate leftover time to the shared pool; stalled lanes can be pre-empted to protect the 12-hour deadline.
- **Shared queues** connect solvers, verifier, and arbitrator via lock-free structures so candidates flow without contention and the arbitrator can request more samples when confidence is low.

## Resource Management Strategies
- **Memory control** relies on 4-bit or 8-bit LLM weights, streamed activation checkpoints, capped symbolic frontiers, and arena-allocated e-graph nodes to keep per-device VRAM within limits.
- **Profiling feedback** from torch.profiler and Nsight traces tunes batch sizes, SMT concurrency, and I/O prefetch depth prior to submission freeze.
- **Fault tolerance** ensures module timeouts or crashes fall back to simplified heuristics, guaranteeing that two answers are always produced within pass@2 allowances.

## Coordination With Evaluation And Analytics
- Module outputs, verifier logs, and runtimes feed an experiment ledger that powers ablations and failure categorisation.
- Scheduler decisions and arbitrator choices are persisted so analysts can trace why specific answers were selected.
- Clear module boundaries make it straightforward to swap in future upgrades (dynamic scheduler, curriculum policies, richer explanations) without changing the overall pipeline.

Together, these architectural choices deliver a reproducible, multi-paradigm solver that balances symbolic precision, adaptive learning, and generative exploration while staying squarely inside ARC-AGI-2's operational envelope.
