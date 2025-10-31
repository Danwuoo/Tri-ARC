#!/usr/bin/env bash
set -euo pipefail

# Bootstrap script for Kaggle offline notebooks.
# Assumes the repository is extracted under /kaggle/working/Tri-ARC
# and that the wheel cache lives at /kaggle/input/tri-arc-wheels.

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WHEEL_ROOT="/kaggle/input/tri-arc-wheels"
REQUIREMENTS_FILE="${ROOT_DIR}/requirements.txt"

if [[ ! -d "${WHEEL_ROOT}" ]]; then
  echo "[ERROR] Expected wheel cache at ${WHEEL_ROOT}. Upload vendor/wheels/ as a Kaggle dataset."
  exit 1
fi

echo "[INFO] Installing Python dependencies from offline wheel cache."
pip install --no-index --find-links "${WHEEL_ROOT}" -r "${REQUIREMENTS_FILE}"

echo "[INFO] Verifying GPU visibility."
python "${ROOT_DIR}/scripts/check_gpu.py"

echo "[INFO] Running environment smoke check."
python "${ROOT_DIR}/scripts/self_test.py" --output "${ROOT_DIR}/reports/setup_verification_kaggle_$(date +%Y%m%d).md"

echo "[INFO] Capturing offline asset inventory."
python "${ROOT_DIR}/scripts/inventory_assets.py" --json "${ROOT_DIR}/reports/offline_inventory_kaggle_$(date +%Y%m%d).json" || \
  echo "[WARN] Asset inventory reported missing items."

echo "[SUCCESS] Kaggle environment ready."
