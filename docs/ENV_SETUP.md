# Environment Setup

Tri-ARC runs fully offline on Kaggle notebooks and local workstations that mirror the competition constraints. Follow the steps below to configure both environments.

## Common Requirements
- **Python**: 3.11.x
- **CUDA**: 12.1 (driver >= 535) or matching version supported by Kaggle runtime.
- **PyTorch**: 2.3 with CUDA support.
- **Z3**: 4.12 CLI and Python bindings.
- **Auxiliary tools**: `torchvision`, `numpy`, `scipy`, `networkx`, `hydra-core`, `pyyaml`, `rg` (ripgrep), `nsys`, `ncu`.
- Install dependencies via `pip install -r requirements.txt` or `conda env create -f environment.yml`.
- Verify GPU availability with `python scripts/check_gpu.py`.

## Kaggle Notebook Setup
1. **Enable GPUs**: In the notebook settings, choose four GPUs (A100 or L4 when available).
2. **Offline data**: Upload dataset archives produced by `scripts/package_data.py`. Place them under `/kaggle/input/tri-arc-data/`.
3. **Repository**: Upload the code bundle as a Kaggle dataset or copy from the competition data tab. Extract to `/kaggle/working/Tri-ARC/`.
4. **Environment bootstrap**:
   ```
   cd /kaggle/working/Tri-ARC
   pip install --no-index --find-links vendor/wheels -r requirements.txt
   ```
   (All wheels must be pre-packaged; internet access is disabled.)
5. **GPU pinning**: Use `CUDA_VISIBLE_DEVICES=0,1,2,3 python run_eval.py ...` to align with the device map in `docs/CONFIG_DEFAULTS.yaml`.
6. **Logging**: Redirect logs to `/kaggle/temp/` to avoid quota issues on `/kaggle/working/`.

## Local Offline Setup
1. **Hardware**: Workstation with >=4 GPUs (A100, L40, or similar), 64 CPU cores, 128 GB RAM.
2. **Clone repository**: `git clone git@.../Tri-ARC.git` (offline mirror). Verify submodules if used.
3. **Conda environment**:
   ```
   conda env create -f environment.yml
   conda activate tri-arc
   ```
4. **GPU assignment**: Export `CUDA_VISIBLE_DEVICES=0,1,2,3`. For split deployments (e.g., limited GPUs), edit `docs/CONFIG_DEFAULTS.yaml` to reflect available devices.
5. **Data staging**: Place datasets under `data/arcagi2/` and ARC-Forge outputs in `data/arc_forge/`. Ensure paths match config.
6. **Licences**: Confirm third-party licences are compatible with offline redistribution.

## Version Pinning
- Capture dependency hashes using `pip freeze > reports/pip_freeze.txt`.
- Record `nvidia-smi` output in `reports/gpu_info.txt`.
- Tag repository with `env-<date>` when environment changes and update `CHANGELOG.md`.

## Verification
1. Run `python scripts/self_test.py` to confirm module imports, CUDA kernels, and Z3 availability.
2. Execute `python run_eval.py --split smoke --max_tasks 5` to validate end-to-end operation within 15 minutes.
3. Log outputs in `reports/setup_verification_<date>.md`.
