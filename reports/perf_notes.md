<!-- Auto-generated performance profiling notes scaffold. -->

# Performance Notes

## Usage
- Monitor interpreter, scheduler, and SMT cache hit/miss metrics via `dsl_cache`, `scheduler_feature_cache`, and `smt_clause_cache` events.
- Run `python tools/profile.py --module symbolic --variant default` after significant solver changes to capture a fresh baseline.
- Add `--variant no_heuristics` or `--variant no_cache` to compare configurations; artefacts are saved under `profiles/`.
- Enable `--torch-profiler` when GPU modules are exercised to emit Chrome traces for Nsight/Torch analysis.

## Baseline Checklist
- [ ] `profiles/` contains JSON artefacts for symbolic, TTT, LLM, and arbitrator modules.
- [ ] `reports/perf_notes.md` is refreshed weekly with runtime deltas and observed bottlenecks.
- [ ] `metrics.jsonl` entries expose `extras.perf` with RSS/GPU deltas for every module stage.
- 2025-11-05 12:22:28Z | module=symbolic variant=default elapsed=0.0103s rss_delta=0.1446MB
