# Local LLM Code Generation Module

The LLM lane contributes creative program hypotheses that complement the structured search and adaptive learning routes. It operates entirely offline using quantized weights packaged with the Tri-ARC submission.

## Goals
- Generate diverse, high-quality DSL or Python snippets that explain the observed I/O examples.
- Remain resource-efficient through low-bit quantisation without sacrificing reasoning ability.
- Deliver only candidates that satisfy all known examples by coupling generation with formal verification.

## Model Configuration
- **Backbone**: A 30B-class causal decoder fine-tuned on ARC-style program traces and grid transformations.
- **Quantisation**: 4-bit or 8-bit QLoRA checkpoints loaded via tensor parallelism to fit within a single GPU (<=24 GB).
- **Prompt scaffolding**: Inputs include task metadata, canonicalised grids, symbolic summaries, and prior solution sketches sourced from the shared cache.

## Generation Strategy
1. **Multi-agent prompting**: Spawn several prompt variants (chain-of-thought, toolformer, DSL-first) to widen hypothesis coverage.
2. **Sampling controls**: Use moderate temperatures (0.6-0.8), nucleus sampling (p~=0.9), and enforce max token budgets to bound latency.
3. **Structured output**: Request JSON-like envelopes that separate natural language reasoning, DSL code, and predicted outputs for easier post-processing.
4. **Self-reflection**: Optionally re-prompt the model with its own critique of earlier attempts to refine subsequent samples.

## SMT-Based Filtering
- **Translation layer** converts generated DSL or Python to a constraint system expressed for Z3.
- **Satisfiability check** ensures each candidate reproduces every provided example exactly; unsatisfiable programs are discarded before runtime execution.
- **Ranking** combines SMT verification status, heuristic scores (program length, primitive usage), and the model's own log-probabilities.

## Interface With The Rest Of Tri-ARC
- The scheduler allocates batch size, number of candidates, and temperature schedules according to task difficulty and remaining time.
- Verified programs, along with optional natural language rationales, are streamed to the arbitrator as soon as they pass SMT checks.
- Failed attempts plus SMT diagnostics are logged and can seed DSL rewrite discovery or new ARC-Forge adversarial tasks.

## Resource Management
- Generation runs on a dedicated GPU; large batches fall back to staggered micro-batches to respect memory caps.
- KV caches are reused across prompt variants when compatible to lower latency.
- SMT solving executes on CPU cores with configurable parallelism, leaving GPU time for additional sampling.

## Roadmap
- Integrate curriculum-learned prompts derived from historical failure clusters.
- Add lightweight consistency models that pre-filter clearly invalid generations before SMT.
- Explore LLM-to-symbolic feedback loops where high-quality generations propose new DSL abstractions directly.

## SolverModule Contract Snapshot
- `arc/llm/__init__.py` exposes the lane as a `SolverModule` stub. It prepares task-local cache slots, records prompt configuration, and surfaces partial results so orchestration paths can be exercised ahead of the full generation stack.
- Module metadata and telemetry now flow through the shared logging pipeline, emitting lifecycle events (`module_start`, `module_stop`, `module_error`) and per-task summaries in `metrics.jsonl`.
- Mock implementations (`arc/llm/mocks.py`) can be activated via CLI or configuration for deterministic smoke tests that validate scheduler, arbitrator, and logging behaviour without loading heavyweight checkpoints.
