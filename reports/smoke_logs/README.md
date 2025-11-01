# Smoke Log Archive

This directory stores per-run smoke validation artefacts. Each entry should follow the naming convention:

- `YYYYMMDD_local_smoke.md` for local workstation runs.
- `YYYYMMDD_kaggle_smoke.md` for Kaggle notebook runs.

## Capture Checklist
1. Provision environment using the scripts in `scripts/`.
2. Record environment fingerprints (`pip_freeze.txt`, `gpu_info.txt`, self-test markdown).
3. Run the dedicated smoke suite:
   ```bash
   python scripts/run_smoke.py --env <local|kaggle> [--wheel-root <cache_path>]
   ```
4. Archive the generated JSON and Markdown files under `reports/smoke_logs/`.
5. Summarise pass/warn/fail counts and remediation notes in the log body.

## Template Snippet
```markdown
# Smoke Validation - <environment> - <date>
- Commit: <git sha>
- Environment manifest: reports/setup_verification_<date>.md
- Asset inventory: reports/offline_inventory_<date>.json

## Results
- Overall status: <PASS|WARN|FAIL>
- Passed: <count>
- Warned: <count>
- Failed: <count>
- Total duration: <seconds>
- GPU util snapshot: <nvidia-smi summary>

## Notes
- Observations, anomalies, corrective actions.
```
