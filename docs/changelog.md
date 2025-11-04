# Tri-ARC Change Log

This change log captures spec, interpreter, and governance updates that require ratification before downstream consumers adopt them. Each entry records the proposal owner, reviewers, approvals, and validation artefacts.

## 2025-11-04 - DSL Specification v0.2.0
- formalised grammar, typing rules, and primitive catalogue for the deterministic interpreter.
- published canonical examples and fixtures backing the automated DSL tests.
- introduced governance workflow, lint checklist, and instrumentation requirements for Phase 2.
- emitted fixtures, verification harness hooks, and CLI scaffolding to unblock downstream integration.

**Proposed by:** Phase 2 DSL working group

**Reviewed by:** Scheduler, Symbolic Solver, Arbitration leads

**Approvals:** [approved] Scheduler - [approved] Symbolic Solver - [approved] Arbitration

**Validation artefacts:**
- `docs/DSL_SPEC.md`
- `docs/DSL_PRIMER.md`
- `fixtures/dsl/spec_examples/`

---

## Template for Future Entries

```
## YYYY-MM-DD - <Component> vX.Y.Z
- summary of change
- impact to downstream teams
- migration or rollout notes

**Proposed by:** Name / team

**Reviewed by:** List reviewers

**Approvals:** [approved] Reviewer 1 - [approved] Reviewer 2 - [approved] Reviewer 3

**Validation artefacts:**
- path/to/artifact
- optional links or report identifiers
```

