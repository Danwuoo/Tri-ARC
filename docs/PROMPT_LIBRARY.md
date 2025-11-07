# Prompt Library

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
  "dsl": DSL pipeline compliant with docs/DSL_SPEC.md
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

Scheduler may override candidate counts based on budgets (see `docs/SCHEDULER_POLICY.md`).

## Anti-Hallucination Rules
- **Interpreter-first rejection**: Programs that fail parsing, linting, or deterministic interpreter evaluation on training examples are tagged `note="failed_verification"` and never forwarded.
- **Primitive whitelist**: The prompt explicitly references `docs/DSL_SPEC.md`. Unknown operators trip the validation step.
- **Structured output**: JSON parsing is strict; anything outside the schema counts as `json_missing` and is recorded for debugging.
- **Token budget guard**: Requests exceeding the `max_input_tokens` budget are truncated and surfaced via `truncated_prompt` metadata.
- **Virtual SMT tokens**: Every surviving candidate receives a deterministic token, so the arbitrator's SMT gatekeeper can continue to enforce module provenance.
- **Diversity filter**: DSL strings are hashed; duplicates (hash match) are skipped before verification to widen coverage.

## Prompt Versioning
- Store prompt revisions under `prompts/history/<date>/<name>.md`.
- Increment `prompt_version` in configuration files when templates change.
- Document rationale and observed effects in `reports/prompt_updates.md`.
