# Scheduler Simulation Notes

This document captures the smoke simulations and automated checks performed while bringing up the Phase 5 scheduler.

## Test Harness
- Unit tests under `tests/scheduler/` validate deterministic feature extraction against golden fixtures and ensure policy rules, feedback loops, and halt conditions behave as intended.
- Scheduler core scenarios exercise:
  - Policy preference for symmetry-heavy tasks (symbolic lane prioritised, staggered start delays).
  - Runtime feedback adjustments increasing module weight after consistent success.
  - Global budget guard rails halting new scheduling when the configurable risk threshold is exceeded.
- Feature cache persistence is verified for both cache hits and ingestion abort paths.

## Observability
- Metrics emitted from the scheduler are aggregated in `metrics.jsonl` and can be inspected via `tools/inspect_schedule.py --list` or `--task-id <id>`.
- Scheduler budget snapshots (`reports/scheduler_budget_<timestamp>.md`) now contain cache hit rates and resource utilisation summaries drawn from the shared resource tracker.

## Next Scenarios
- Extend smoke simulations to incorporate parallel stub modules that donate unused budgets mid-flight.
- Add fuzzed event ordering tests covering cooperative pause/resume and SMT backlog pressure.
