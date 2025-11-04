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

## 2025-11-04 - DSL Tooling Refresh
- moved the interpreter runtime under `arc/symbolic/dsl/` and added `arc/symbolic/interpreter_adapter.py` for downstream integration.
- shipped verification harness (`arc/symbolic/dsl/verify.py`), CLI tooling (`scripts/run_dsl.py`), and fixture-backed tests (`tests/dsl/`) to gate Phase 2 deliverables.
- regenerated offline artefacts (`vendor/wheels/manifest.sha256`, `dist/data_bundle.tar.gz`, `reports/offline_inventory_20251104.json`) and documented licence coverage in `docs/compliance/LICENCE_LOG.md`.
- updated developer playbooks and plans with verification workflows, benchmark reports, and smoke expectations.

**Proposed by:** Phase 2 DSL working group

**Reviewed by:** Symbolic Solver, Dev Productivity

**Approvals:** [approved] Symbolic Solver - [approved] Dev Productivity

**Validation artefacts:**
- `arc/symbolic/dsl/verify.py`
- `scripts/run_dsl.py`
- `reports/dsl_benchmarks_20251104.md`
- `logs/verification/verification_*.jsonl`
- `tests/dsl/`

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

