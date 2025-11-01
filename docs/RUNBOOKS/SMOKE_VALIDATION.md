# Stage 2 - Smoke Validation Runbook

Use this runbook after Stage 1 provisioning to validate that GPU, SMT, and package wiring work in each offline environment.

## Goal
- Exercise the smoke validation suite (`tri_arc.smoke`) end-to-end.
- Produce Markdown and JSON artefacts under `reports/smoke_logs/` with timestamped filenames.
- Capture failures with actionable notes so fixes can roll back into Stage 1 provisioning.

## Prerequisites
- Stage 1 environment landing completed (`scripts/setup_local_env.sh` or `scripts/setup_kaggle_env.sh`).
- `reports/setup_verification_*.md` and `reports/offline_inventory_*.json` available for cross-reference.
- Dataset staged under `data/arcagi2/` (or mounted equivalent).
- Wheel cache accessible locally (`vendor/wheels/`) or via Kaggle dataset (`/kaggle/input/tri-arc-wheels`).

## Local Execution
1. Activate the conda environment (`conda activate tri-arc`).
2. From the repository root run:
   ```bash
   python scripts/run_smoke.py --env local
   ```
3. Inspect the console summary for pass/warn/fail counts.
4. Review generated files in `reports/smoke_logs/`:
   - `<timestamp>_local_smoke.json`
   - `<timestamp>_local_smoke.md`
5. For failures, note missing packages, dataset gaps, or solver issues. Feed corrective actions back into Stage 1 scripts.

## Kaggle Notebook Execution
1. Upload the repository bundle plus the wheel cache dataset.
2. In the Kaggle notebook shell:
   ```bash
   cd /kaggle/working/Tri-ARC
   python scripts/run_smoke.py --env kaggle --wheel-root /kaggle/input/tri-arc-wheels
   ```
3. Copy resulting artefacts from `reports/smoke_logs/` to the competition output directory for download.
4. Record the Kaggle runtime commit SHA and GPU allocation in the Markdown log.

## Failure Triage
- Use `docs/DEBUG_PLAYBOOK.md` for module-specific probes.
- Tag issues with `docs/ERROR_TAXONOMY.md` categories inside the Markdown log.
- Typical failure modes:
  - Missing `z3` or CUDA packages -> revisit Stage 1 install scripts.
  - Dataset absence -> confirm `data/arcagi2/` path matches `docs/CONFIG_DEFAULTS.yaml`.
  - Wheel cache empty -> repack wheels using `scripts/build_wheel_cache.sh`.
- Document remediation steps in the `## Notes` section of each smoke log.

## Exit Criteria
- All smoke tests report `pass` (allowing `warn` only for optional checks like `nvidia-smi` on CPU-only machines).
- Markdown and JSON artefacts stored under `reports/smoke_logs/` for both environments.
- Outstanding issues tracked for follow-up before proceeding to Stage 3.

## Next Steps
- When both environments pass the smoke suite, move to Stage 3 (`Data & Evaluation Loop`) and begin wiring the evaluation harness.

