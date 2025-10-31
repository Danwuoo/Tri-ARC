# Smoke Log Archive

This directory stores per-run smoke validation artefacts. Each entry should follow the naming convention:

- `YYYYMMDD_local_smoke.md` for local workstation runs.
- `YYYYMMDD_kaggle_smoke.md` for Kaggle notebook runs.

## Capture Checklist
1. Provision environment using the scripts in `scripts/`.
2. Record environment fingerprints (`pip_freeze.txt`, `gpu_info.txt`, self-test markdown).
3. Execute the smoke pass once the evaluation harness is available:
   ```bash
   python run_eval.py --split smoke --max_tasks 5 --config docs/CONFIG_DEFAULTS.yaml
   ```
4. Copy the relevant log excerpts:
   - `logs/runtime.log`
   - `metrics.jsonl` (first 10 lines)
   - `reports/setup_verification_<date>.md`
5. Summarise pass/fail counts and key timings in the markdown template below.

## Template Snippet
```markdown
# Smoke Validation — <environment> — <date>
- Commit: <git sha>
- Environment manifest: reports/setup_verification_<date>.md
- Asset inventory: reports/offline_inventory_<date>.json

## Results
- Tasks executed: 5
- Passes: <count>
- Failures: <count> (list task IDs)
- Max latency: <value>
- GPU util snapshot: <nvidia-smi summary>

## Notes
- Observations, anomalies, corrective actions.
```
