# Local LLM Code Generation Module

The LLM lane contributes creative program hypotheses that complement the structured search and adaptive learning routes. It operates entirely offline using quantized weights packaged with the Tri-ARC submission.

## Goals
- Generate diverse, high-quality DSL or Python snippets that explain the observed I/O examples.
- Remain resource-efficient through low-bit quantisation without sacrificing reasoning ability.
- Deliver only candidates that satisfy all known examples by coupling generation with formal verification.

## Model Configuration
- **Backbone**: Qwen‑2.5 Coder 7B (Instruct) running locally in 4‑bit NF4 via BitsAndBytes. The loader defaults to `backend=auto`, attempting Qwen first and falling back to a stub engine when GPU resources are absent.
- **Quantisation**: 4‑bit weights with bfloat16 compute; max context trimmed to 1,536 tokens to avoid OOM on 24 GB GPUs. Other bit widths are supported when explicitly requested in the config.
- **Prompt scaffolding**: The `PromptBuilder` feeds canonicalised grids, palette summaries, and rationalised instructions into three chain‑of‑thought variants (planner / symmetry / contrast). Each prompt emits JSON containing `rationale`, `dsl`, `confidence`, and `test_outputs`.

## Generation Strategy
1. **Variant round-robin**: Eight samples per task are distributed proportionally across the bundled prompt variants so that symmetry-heavy and object-count focused chains receive dedicated budget.
2. **Sampling controls**: Temperatures/top‑p values inherit from the configuration (defaults: 0.7 / 0.9) and max new tokens are clamped to 512 to bound latency.
3. **Structured output**: Every completion must be valid JSON. The parser extracts the DSL string, rationale, model‑reported confidence, and evaluation predictions before downstream checks run.
4. **Cache-friendly metadata**: Prompt hashes, variant names, token usage, and runtime per completion are stored in `cache_namespace['llm_generations']` for replay tooling.

## SMT-Based Filtering
- **DSL Interpreter**: Generated programs are parsed with `arc.symbolic.dsl.parser`, linted, and executed via `DSLInterpreter`. Candidates that fail static checks or runtime evaluation are labeled `note="failed_verification"` and excluded unless `keep_failed_candidates` is enabled.
- **Virtual SMT tokens**: Passing candidates receive deterministic `smt_token`s derived from `llm.smt.token_prefix`, satisfying the arbitrator's attestation gate.
- **Ranking**: Verified programs are ordered by blended confidence (`0.35 * model_confidence + 0.65 * train_accuracy`) before the refinement cap is applied.

## Interface With The Rest Of Tri-ARC
- Scheduler inputs map directly to `initial_candidates`, `temperature_initial`, and `top_p_initial`. Setting `backend: stub` keeps smoke tests cheap while real runs load the quantised Qwen weights.
- Each candidate exposes rich metadata (prompt version, variant focus, prompt hash, token usage, rationale, DSL lint issues, per-example execution logs) so the arbitrator and diagnostics dashboards can understand LLM provenance.
- Rejected generations (JSON errors, duplicates, verification failures) are preserved under `cache_namespace['llm_failures']` to guide future prompt tweaks.

## Resource Management
- 4‑bit quantisation keeps the 7B model within a single 24 GB GPU. Sampling is executed sequentially per prompt request to avoid surprise memory spikes on Kaggle GPUs.
- Stub backend remains available for CI environments without GPUs; it emits deterministic identity programs for contract checks.
- Interpreter executions stay on CPU, allowing the GPU to remain saturated with generation work while verification results stream back incrementally.

## Roadmap
- Integrate curriculum-learned prompts derived from historical failure clusters.
- Add lightweight consistency models that pre-filter clearly invalid generations before SMT.
- Explore LLM-to-symbolic feedback loops where high-quality generations propose new DSL abstractions directly.

## SolverModule Contract Snapshot
- `arc/llm/__init__.py` now initialises `PromptBuilder`, `QwenCoderEngine`, and `DSLInterpreter` inside the `SolverModule` lifecycle, returning **program** candidates annotated with prompt/verification metadata and SMT tokens.
- Module summaries record generated/verified counts plus a failure histogram (`failure_reasons`) so regressions can be triaged quickly.
- `arc/llm/mocks.py` keeps a stubbed subclass for deterministic tests, while `backend: stub` offers a config-level bypass without swapping implementations.
