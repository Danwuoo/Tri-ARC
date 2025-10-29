# Release Checklist

Use this checklist before publishing a Tri-ARC release candidate or Kaggle submission. The process assumes a fully offline environment.

## Preflight
- [ ] Verify local repository is clean (`git status`).
- [ ] Update `docs/CONFIG_DEFAULTS.yaml` with final hyperparameters.
- [ ] Bump version in `CHANGELOG.md` and tag commits to be included.
- [ ] Regenerate dependency locks:
  - [ ] `pip freeze > reports/pip_freeze.txt`
  - [ ] `conda env export > reports/conda_env.yaml`

## Full 12-Hour Validation
- [ ] Execute `python run_eval.py --split evaluation --max_hours 12 --config docs/CONFIG_DEFAULTS.yaml`.
- [ ] Confirm wall-clock time <= 11.5 hours (buffer for Kaggle variance).
- [ ] Validate pass@2 >= target threshold (85% goal).
- [ ] Ensure timeout rate < 5%.
- [ ] Archive metrics (`metrics.jsonl`) and logs (`logs/runtime.log`, `logs/smt/`).
- [ ] Tag all failures using `docs/ERROR_TAXONOMY.md`; document in `reports/release_failures.md`.

## Ablations
- [ ] Run configs A-E (see `docs/ABLATIONS.md`) on evaluation subset.
- [ ] Store results in `reports/ablation_<date>.md`.
- [ ] Summarise deltas and confirm no regression vs previous release.

## Performance Audit
- [ ] Capture GPU utilisation via Nsight/NVProf snapshot.
- [ ] Update `docs/PERF_BUDGET.md` if bottlenecks differ from defaults.
- [ ] Verify SMT queue lengths and success rates stay within planned bounds.

## Packaging
- [ ] Run `scripts/package_data.py` to produce dataset tarballs.
- [ ] Bundle code with `scripts/package_code.py --output dist/Tri-ARC-<version>.zip`.
- [ ] Include:
  - [ ] `docs/` directory
  - [ ] `models/` (weights, quantised files)
  - [ ] `scripts/`, `configs/`, `run_eval.py`
  - [ ] `requirements.txt` or wheelhouse in `vendor/`
- [ ] Validate archive contents on a clean machine using `docs/RUNBOOKS/QUICKSTART.md`.

## Final Documentation
- [ ] Update `docs/EVAL_PROTOCOL.md` with version references.
- [ ] Record environment details in `reports/release_env.md`.
- [ ] Append release summary to `CHANGELOG.md` under new version heading.

## Submission / Release
- [ ] Push tags and release branch.
- [ ] Upload Kaggle notebook bundle with packaged data.
- [ ] Run smoke test on Kaggle to confirm execution.
- [ ] Announce release with summary of metrics, ablation highlights, and known issues.
