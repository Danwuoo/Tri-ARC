# Stage 1 — Environment Landing Runbook

Use this runbook to reproduce the Stage 1 deliverables end-to-end.

## 1. Prepare Offline Assets
- Ensure the Tri-ARC repository, `model/` weights, and datasets are available locally.
- From an internet-enabled machine run:
  ```bash
  bash scripts/build_wheel_cache.sh
  ```
- Verify the cache:
  ```bash
  python scripts/inventory_assets.py
  ```

## 2. Provision Local Environment
```bash
bash scripts/setup_local_env.sh
```
This script:
- Creates/refreshes the conda environment defined in `environments/conda/environment.yml`.
- Installs Python dependencies via the offline wheel cache when present.
- Captures `pip_freeze`, `conda_env_history.yaml`, `gpu_info.txt`.
- Executes `scripts/self_test.py` and `scripts/inventory_assets.py`, storing reports under `reports/`.

## 3. Provision Kaggle Notebook
- Upload the repository bundle and `vendor/wheels/` as Kaggle datasets.
- In the Kaggle notebook:
  ```bash
  cd /kaggle/working/Tri-ARC
  bash scripts/setup_kaggle_env.sh
  ```
- The script mirrors the local provisioning flow and drops reports in `reports/`.

## 4. Verify & Archive
- Inspect Markdown/JSON outputs in `reports/` for both environments.
- Document findings or anomalies in `reports/smoke_logs/<date>_<env>_smoke.md`.
- Append any missing packages to `requirements.txt` and rebuild wheels if gaps remain.

## 5. Next Steps
- Proceed to Stage 2 (`Smoke Validation`) using the prepared environments.
- Keep wheel caches and logs under source control to enable reproducible deployments.
