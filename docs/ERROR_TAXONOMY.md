# Error Taxonomy

Tri-ARC logs every unsolved or low-confidence task using a shared taxonomy so ablations, regressions, and ARC-Forge synthesis can target the right failure modes. Annotators should apply the criteria below consistently; ambiguous cases receive multiple tags ordered by prevalence.

## Tagging Guidelines
- **Granularity**: Assign at least one high-level category (Symbolic, TTT, LLM, Cross-Module, Infrastructure). Add sub-tags when evidence is clear.
- **Evidence first**: Use module logs, SMT traces, and grid diffs to justify each label. Avoid speculation.
- **Order**: List tags from most to least causal. For example, `Symbolic:RuleInteraction`, `CrossModule:Arbitration`.
- **Severity**: Mark `Critical` when the failure blocks evaluation (no output, crash). Otherwise mark `Major` (incorrect output) or `Minor` (correct but slow/low confidence).
- **Example snapshots**: Save before/after grids or program snippets in `reports/errors/<task_id>/`.

## Category Definitions And Examples

### Symbolic
- **RuleInterpretation**: Synthesised program misses the underlying rule (e.g., misidentifies the target object).  
  *Example*: Program paints the second-largest object instead of the largest; counterexample shows incorrect region mask.*
- **RuleInteraction**: Partial rules conflict or stack incorrectly (e.g., symmetry plus recolour).  
  *Example*: E-graph rewrite drops an order constraint, leading to swapped operations.*
- **SearchTimeout**: Beam search exhausts budget before finding a consistent program.
- **LibraryGap**: Required primitive absent; solver attempts to emulate with verbose alternative and fails.

### Test-Time Training (TTT)
- **OverfitSupport**: Adapted model matches support examples but diverges on test grid; loss spikes on held-out validation sample.
- **GradientDivergence**: Training blows up (NaNs, exploding gradients) causing reset.
- **Underadaptation**: Early stopping triggers before loss plateau due to conservative scheduler settings.

### LLM
- **PromptDrift**: Generated explanation misreads task schema; SMT rejects all candidates.
- **SyntaxError**: Output malformed (unclosed parentheses, invalid DSL tokens).
- **HallucinatedPrimitive**: References DSL primitive that does not exist in `docs/DSL_SPEC.md`.
- **LowConfidence**: All candidates pass SMT but arbitrator score below threshold due to high complexity/logprob penalty.

### Cross-Module
- **ArbitrationConflict**: Two high-scoring candidates disagree; tie-breaker selects wrong answer.
- **SchedulerBudget**: Budgets misallocated, starving the successful lane (document relevant metrics from `docs/SCHEDULER_POLICY.md`).
- **SMTBottleneck**: Verifier backlog prevents timely evaluation, causing modules to timeout.

### Infrastructure
- **IOFailure**: Dataset read/write issues, missing cache files, corrupted JSON.
- **OOM**: GPU or CPU memory exhaustion leading to aborted run (see `docs/PERF_BUDGET.md` for mitigation).
- **TimeoutGlobal**: Run exceeds 12-hour limit, leaving tasks unsolved.

## Annotation Template
```
task_id: XXXXX
severity: Major
tags:
  - Symbolic:RuleInteraction
  - CrossModule:Arbitration
evidence:
  - symbolic_log: reports/program_XXXXX.dsl
  - arbitrator_score: primary=0.58 secondary=0.54
notes: "Symbolic program applied reflect before recolor; secondary TTT output correct but deprioritised."
actions:
  - investigate e-graph rewrite priority
  - adjust arbitrator diversity bonus
```

## Usage In Experiments
- Regression suites consume tags to ensure previously fixed categories remain solved.
- Ablations (see `docs/ABLATIONS.md`) group errors by category to explain performance deltas.
- ARC-Forge prioritises generating tasks from categories with the highest unresolved counts.
