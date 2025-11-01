# Tri-ARC

Tri-ARC is an offline-first ARC solver stack that targets Kaggle notebooks and local multi-GPU workstations. This repository currently covers **Stage 1 - Environment Landing** and **Stage 2 - Smoke Validation** from the development plan: establishing reproducible environments and confirming they are runnable with automated smoke checks.

## Stage 1 - Environment Landing
- Dependency manifests: `requirements.txt`, `environments/conda/environment.yml`.
- Provisioning scripts:
  - `scripts/setup_local_env.sh` - create/update the local conda environment and capture reports.
  - `scripts/setup_kaggle_env.sh` - bootstrap offline Kaggle runtimes using pre-packaged wheels.
  - `scripts/build_wheel_cache.sh` - download wheel artefacts into `vendor/wheels/` for offline installs.
- Verification utilities:
  - `scripts/self_test.py` - environment health check (PyTorch, CUDA, Z3, wheels, model weights).
  - `scripts/check_gpu.py` - concise GPU diagnostic output.
  - `scripts/inventory_assets.py` - JSON manifest covering wheels, weights, and datasets.
- Log staging: `reports/` captures `pip_freeze`, `gpu_info`, self-test markdown summaries, and smoke log templates.

## Stage 2 - Smoke Validation
- Smoke suite module: `tri_arc.smoke` (CUDA, Z3, dataset, wheel cache, logging probes).
- Runner CLI: `python scripts/run_smoke.py --env <local|kaggle> [--wheel-root <path>]`.
- Artefacts: JSON and Markdown logs under `reports/smoke_logs/<timestamp>_<env>_smoke.*`.
- Runbook: `docs/RUNBOOKS/SMOKE_VALIDATION.md` outlines local and Kaggle execution plus failure triage against `docs/ERROR_TAXONOMY.md` and `docs/DEBUG_PLAYBOOK.md`.

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
4. **Run smoke validation (after provisioning)**
   ```bash
   python scripts/run_smoke.py --env local
   ```
   - For Kaggle notebooks: `python scripts/run_smoke.py --env kaggle --wheel-root /kaggle/input/tri-arc-wheels`
5. **Prepare Kaggle bundle**
   - Include `vendor/wheels/`, `model/`, `docs/`, and `reports/`.
   - In the Kaggle notebook:
     ```bash
     cd /kaggle/working/Tri-ARC
     bash scripts/setup_kaggle_env.sh
     ```

See `docs/ENV_SETUP.md` for detailed instructions, `docs/RUNBOOKS/ENVIRONMENT_LANDING.md` for the Stage 1 runbook, `docs/RUNBOOKS/SMOKE_VALIDATION.md` for Stage 2 operations, and `docs/RUNBOOKS/QUICKSTART.md` once the evaluation harness is available.
