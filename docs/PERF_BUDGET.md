# Performance Budget

Tri-ARC must solve the full ARC-AGI-2 evaluation suite within 12 hours on four GPUs. This document codifies time quotas, memory ceilings, concurrency plans, caching practices, and observed bottlenecks.

## Time Allocation
| Component | Default per-task budget | Notes |
|-----------|------------------------|-------|
| Scheduler + preprocessing | 5 s | Feature extraction, cache warm-up |
| Symbolic solver | 90 s soft, 150 s max | Depth and beam width tuned per task |
| TTT adaptor | 90 s soft, 150 s max | Includes adaptation, ensemble inference |
| LLM generation + SMT | 90 s soft, 150 s max | Covers sampling, SMT filtering |
| Arbitration + logging | 10 s | Verification, scoring, telemetry |

Unspent budget is pooled and redistributed by the scheduler (see `docs/SCHEDULER_POLICY.md`). Hard caps ensure cumulative time stays under the 12-hour limit.

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
