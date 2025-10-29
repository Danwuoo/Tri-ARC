# Ablation Study Guide

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
5. **Error tagging**: Apply taxonomy from `docs/ERROR_TAXONOMY.md` to all failures.

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
