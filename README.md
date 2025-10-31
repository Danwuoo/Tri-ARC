# Tri-ARC

Tri-ARC is an offline-first ARC solver stack that targets Kaggle notebooks and local multi-GPU workstations. This repository currently focuses on **Stage 1 — Environment Landing** from the development plan: locking down reproducible environments, validating hardware availability, and preparing offline assets.

## Stage 1 Deliverables
- Dependency manifests: `requirements.txt`, `environments/conda/environment.yml`.
- Provisioning scripts:
  - `scripts/setup_local_env.sh` — create/update the local conda environment and capture reports.
  - `scripts/setup_kaggle_env.sh` — bootstrap offline Kaggle runtimes using pre-packaged wheels.
  - `scripts/build_wheel_cache.sh` — download wheel artefacts into `vendor/wheels/` for offline installs.
- Verification utilities:
  - `scripts/self_test.py` — environment health check (PyTorch, CUDA, Z3, wheels, model weights).
  - `scripts/check_gpu.py` — concise GPU diagnostic output.
  - `scripts/inventory_assets.py` — JSON manifest covering wheels, weights, and datasets.
- Log staging: `reports/` captures `pip_freeze`, `gpu_info`, self-test markdown summaries, and smoke log templates.

Subsequent stages (smoke validation, data/evaluation loop, etc.) will build on this foundation.

## Quick Start
1. **Build wheel cache (online machine only)**
   ```bash
   bash scripts/build_wheel_cache.sh
   ```
2. **Provision local environment**
   ```bash
   bash scripts/setup_local_env.sh
   ```
3. **Run health checks**
   ```bash
   python scripts/self_test.py --output reports/setup_verification_$(date +%Y%m%d).md
   python scripts/inventory_assets.py --json reports/offline_inventory_$(date +%Y%m%d).json
   ```
4. **Prepare Kaggle bundle**
   - Include `vendor/wheels/`, `model/`, `docs/`, and `reports/`.
   - In the Kaggle notebook:
     ```bash
     cd /kaggle/working/Tri-ARC
     bash scripts/setup_kaggle_env.sh
     ```

See `docs/ENV_SETUP.md` for detailed instructions, `docs/RUNBOOKS/ENVIRONMENT_LANDING.md` for the Stage 1 runbook, and `docs/RUNBOOKS/QUICKSTART.md` for the smoke evaluation workflow.
