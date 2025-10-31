#!/usr/bin/env bash
set -euo pipefail

# This script provisions the Tri-ARC conda environment on a local workstation.
# It assumes Mambaforge/Conda is available and CUDA-capable drivers are already installed.

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/environments/conda/environment.yml"
REQUIREMENTS_FILE="${ROOT_DIR}/requirements.txt"
VENDOR_WHEELS="${ROOT_DIR}/vendor/wheels"
ENV_NAME="tri-arc"

if ! command -v conda >/dev/null 2>&1; then
  echo "[ERROR] Conda is not available on PATH. Install Mambaforge (recommended) before running this script."
  exit 1
fi

echo "[INFO] Creating conda environment '${ENV_NAME}' from ${ENV_FILE}"
conda env remove -n "${ENV_NAME}" >/dev/null 2>&1 || true
conda env create -f "${ENV_FILE}"

# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${ENV_NAME}"

echo "[INFO] Installing Python packages from ${REQUIREMENTS_FILE}"
if [[ -d "${VENDOR_WHEELS}" ]]; then
  echo "[INFO] Using offline wheels in ${VENDOR_WHEELS}"
  pip install --no-index --find-links "${VENDOR_WHEELS}" -r "${REQUIREMENTS_FILE}"
else
  echo "[WARN] Offline wheel cache not found. Falling back to online installation."
  pip install -r "${REQUIREMENTS_FILE}"
fi

echo "[INFO] Capturing environment manifests under reports/"
mkdir -p "${ROOT_DIR}/reports"
pip freeze > "${ROOT_DIR}/reports/pip_freeze.txt"
conda env export --from-history > "${ROOT_DIR}/reports/conda_env_history.yaml"
nvidia-smi > "${ROOT_DIR}/reports/gpu_info.txt" 2>/dev/null || \
  echo "[WARN] nvidia-smi not available; GPU info report skipped."

echo "[INFO] Running environment smoke check (scripts/self_test.py)"
python "${ROOT_DIR}/scripts/self_test.py" --output "${ROOT_DIR}/reports/setup_verification_$(date +%Y%m%d).md"

echo "[INFO] Capturing offline asset inventory"
python "${ROOT_DIR}/scripts/inventory_assets.py" --json "${ROOT_DIR}/reports/offline_inventory_$(date +%Y%m%d).json" || \
  echo "[WARN] Asset inventory reported missing items. Review reports/offline_inventory_*.json."

echo "[SUCCESS] Local environment provisioned. Activate with 'conda activate ${ENV_NAME}'."
