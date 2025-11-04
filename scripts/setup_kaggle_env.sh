#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHEEL_ROOT="${PROJECT_ROOT}/vendor/wheels"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

echo "[Tri-ARC] Kaggle environment bootstrap starting."

if [[ ! -d "${WHEEL_ROOT}" ]]; then
  echo "[Tri-ARC] ERROR: Wheel cache ${WHEEL_ROOT} not found." >&2
  exit 1
fi

python3 -m venv "${PROJECT_ROOT}/.venv"
source "${PROJECT_ROOT}/.venv/bin/activate"

pip install --upgrade pip
pip install --no-index --find-links "${WHEEL_ROOT}" -r "${REQUIREMENTS_FILE}"

echo "[Tri-ARC] Kaggle environment bootstrap complete."
