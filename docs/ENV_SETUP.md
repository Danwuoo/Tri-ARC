# Environment Setup

Tri-ARC runs fully offline on Kaggle notebooks and local workstations that mirror the competition constraints. Follow the steps below to configure both environments.

## Common Requirements
- **Python**: 3.11.x
- **CUDA**: 12.1 (driver >= 535) or matching version supported by Kaggle runtime.
- **PyTorch**: 2.3 with CUDA support.
- **Z3**: 4.12 CLI and Python bindings.
- **Auxiliary tools**: `torchvision`, `numpy`, `scipy`, `networkx`, `hydra-core`, `pyyaml`, `rg` (ripgrep), `nsys`, `ncu`.
- Dependency manifests live in `requirements.txt`, `environments/conda/environment.yml`, and `environments/docker/Dockerfile`.
- Use `scripts/build/build_wheel_cache.sh` to pre-download wheels into `vendor/wheels/` and refresh `vendor/wheels/manifest.sha256` for offline installs. Override `PIP_PYTHON_VERSION`, `PIP_PLATFORM`, or `PIP_NO_BINARY` when targeting non-default environments.
- Verify GPU availability with `python scripts/check_gpu.py`.
- Capture the environment snapshot with `python scripts/self_test.py --output reports/setup_verification_<date>.md`.

## Kaggle Notebook Setup
1. **Enable GPUs**: In the notebook settings, choose four GPUs (A100 or L4 when available).
2. **Offline data**: Upload dataset archives produced by `scripts/package_data.py`. Place them under `/kaggle/input/tri-arc-data/`.
3. **Repository**: Upload the code bundle as a Kaggle dataset or copy from the competition data tab. Extract to `/kaggle/working/Tri-ARC/`.
4. **Environment bootstrap**:
   ```
   cd /kaggle/working/Tri-ARC
   bash scripts/setup_kaggle_env.sh
   ```
   (All wheels must be pre-packaged; upload `vendor/wheels/` as a Kaggle dataset.)
5. **GPU pinning**: Use `CUDA_VISIBLE_DEVICES=0,1,2,3 python scripts/run_eval.py ...` to align with the device map in `docs/CONFIG_DEFAULTS.yaml`.
6. **Logging**: Redirect logs to `/kaggle/temp/` to avoid quota issues on `/kaggle/working/`.

## Local Offline Setup
1. **Hardware**: Workstation with >=4 GPUs (A100, L40, or similar), 64 CPU cores, 128 GB RAM.
2. **Clone repository**: `git clone git@.../Tri-ARC.git` (offline mirror). Verify submodules if used.
3. **Conda environment**:
   ```
   bash scripts/setup_local_env.sh
   ```
4. **GPU assignment**: Export `CUDA_VISIBLE_DEVICES=0,1,2,3`. For split deployments (e.g., limited GPUs), edit `docs/CONFIG_DEFAULTS.yaml` to reflect available devices.
5. **Data staging**: Place datasets under `data/arcagi2/` and ARC-Forge outputs in `data/arc_forge/`. Ensure paths match config.
6. **Licences**: Confirm third-party licences are compatible with offline redistribution.

## Version Pinning
- Capture dependency hashes using `pip freeze > reports/pip_freeze.txt`.
- Record `nvidia-smi` output in `reports/gpu_info.txt`.
- Tag repository with `env-<date>` when environment changes and update `CHANGELOG.md`.

## Verification
1. Run `python scripts/self_test.py --output reports/setup_verification_<date>.md` to confirm module imports, CUDA kernels, and Z3 availability.
2. Generate the asset manifest with `python scripts/inventory_assets.py --json reports/offline_inventory_<date>.json`.
3. Execute `python scripts/run_eval.py --split smoke --max_tasks 5` to validate end-to-end operation within 15 minutes (Stage 2 onwards).
4. Log outputs in `reports/smoke_logs/`.
5. Update `docs/compliance/LICENCE_LOG.md` with new bundles before publishing artifacts.

## Symbolic Heuristic Weights
- Build deterministic TorchScript weights for the neural heuristic with `python scripts/build/build_symbolic_heuristic.py`. The script emits `models/symbolic/heuristic.pt` and a checksum manifest `models/symbolic/heuristic.sha256`.
- The checksum manifest records the SHA256 hash and metadata (seed, layer layout). Upload both files with the offline bundle so `docs/MODULES/SYMBOLIC.md` requirements are satisfied.
- On CPU-only hosts, override the symbolic lane device via `python tools/compare_heuristics.py --seed 1337 --output ...` (or set `symbolic.device: cpu` in config) before running calibration jobs.
