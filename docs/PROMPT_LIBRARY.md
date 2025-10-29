# Prompt Library

This library captures the prompt templates, sampling parameters, and anti-hallucination rules used by the local LLM module (see `docs/MODULES/LLM_CODEGEN.md`). Prompts are expressed in plain text with slot variables wrapped in `{{ }}`.

## Core Templates

### 1. Task Overview Prompt
```
You are Tri-ARC's program synthesis assistant. Given ARC examples, describe the rule and propose DSL code.

Task ID: {{task_id}}
Grid Size: {{grid_dims}}
Colours: {{palette_summary}}

Examples:
{% for example in examples %}
- Input:
{{example.input}}
- Output:
{{example.output}}
{% endfor %}

Respond in JSON with keys:
  "rationale": concise explanation of the rule
  "dsl": DSL program implementing the rule
  "test_prediction": predicted output for the test grid
```

### 2. Chain-of-Thought Refinement Prompt
```
Review the previous attempt and correct mistakes.

Previous rationale:
{{previous_rationale}}

Previous DSL:
{{previous_dsl}}

Known failure: {{failure_summary}}

Provide a revised rationale and DSL in the same JSON schema.
```

### 3. Symmetry-Focused Prompt
```
Focus on symmetry and pattern repetition. Analyse the grids for reflections, rotations, or tiling.

Important constraints:
- Preserve colour counts unless evidence shows creation/destruction.
- Use DSL primitives from docs/DSL_SPEC.md only.

Return JSON with "rationale", "dsl", and "test_prediction".
```

## Sampling Settings
| Scenario | Temperature | Top-p | Max tokens | Candidates | Notes |
|----------|-------------|-------|------------|------------|-------|
| Initial batch | 0.7 | 0.9 | 512 | 8 | Balanced exploration |
| Refinement | 0.4 | 0.8 | 384 | 4 | More deterministic for fixes |
| Symmetry focus | 0.6 | 0.85 | 448 | 6 | Bias toward structural solutions |
| Low-resource fallback | 0.2 | 0.6 | 320 | 2 | When SMT backlog is high |

Scheduler may override candidate counts based on budgets (see `docs/SCHEDULER_POLICY.md`).

## Anti-Hallucination Rules
- **Primitive whitelist**: Restrict DSL tokens to those documented in `docs/DSL_SPEC.md`. Unknown primitives trigger immediate rejection.
- **Structured output**: LLM must return valid JSON. Use regex validation and schema checks before SMT translation.
- **Token budget guard**: Abort responses exceeding max tokens to prevent rambling explanations.
- **Self-check**: After each generation, re-prompt the model with `"Does your DSL use only allowed primitives? Answer yes/no."`; discard responses containing "no".
- **SMT veto**: No candidate reaches the arbitrator without a `sat` result from the gatekeeper (`docs/SMT_GATEKEEPER.md`).
- **Diversity filter**: Drop near-duplicate DSL programs (levenshtein distance < 10) to widen search coverage.

## Prompt Versioning
- Store prompt revisions under `prompts/history/<date>/<name>.md`.
- Increment `prompt_version` in configuration files when templates change.
- Document rationale and observed effects in `reports/prompt_updates.md`.
