#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ENV_NAME="tri-arc"
ENV_YAML="${PROJECT_ROOT}/environments/conda/environment.yml"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
VENV_DIR="${PROJECT_ROOT}/.venv"

resolve_python_bin() {
  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    echo "${VENV_DIR}/bin/python"
  elif [[ -x "${VENV_DIR}/Scripts/python.exe" ]]; then
    echo "${VENV_DIR}/Scripts/python.exe"
  else
    echo ""
  fi
}

detect_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    echo "python3.11"
  elif command -v py >/dev/null 2>&1; then
    echo "py -3.11"
  else
    echo ""
  fi
}

echo "[Tri-ARC] Bootstrapping local environment at ${PROJECT_ROOT}"

if command -v conda >/dev/null 2>&1; then
  echo "[Tri-ARC] Detected conda; creating or updating environment ${CONDA_ENV_NAME}"
  conda env update -f "${ENV_YAML}" --prune
  echo "[Tri-ARC] Activating conda environment ${CONDA_ENV_NAME}"
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "${CONDA_ENV_NAME}"
  python -m pip install --extra-index-url https://download.pytorch.org/whl/cu121 -r "${REQUIREMENTS_FILE}"
else
  echo "[Tri-ARC] Conda not found; falling back to virtualenv at ${PROJECT_ROOT}/.venv"
  PY_CMD="$(detect_python)"
  if [[ -z "${PY_CMD}" ]]; then
    echo "[Tri-ARC] ERROR: Python 3.11 interpreter not found." >&2
    exit 1
  fi
  ${PY_CMD} -m venv "${VENV_DIR}"
  PYTHON_BIN="$(resolve_python_bin)"
  if [[ -z "${PYTHON_BIN}" ]]; then
    echo "[Tri-ARC] ERROR: Unable to resolve virtualenv python binary." >&2
    exit 1
  fi
  "${PYTHON_BIN}" -m pip install --upgrade pip
  "${PYTHON_BIN}" -m pip install --extra-index-url https://download.pytorch.org/whl/cu121 -r "${REQUIREMENTS_FILE}"
fi

echo "[Tri-ARC] Environment bootstrap complete."
