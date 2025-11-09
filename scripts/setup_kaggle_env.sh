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

ALLOW_PYPI="${TRI_ARC_ALLOW_PYPI:-0}"
PIP_EXTRA_INDEX_URL="${TRI_ARC_PIP_EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"
VENV_DIR="${PROJECT_ROOT}/.venv"

has_network() {
  if command -v curl >/dev/null 2>&1; then
    if curl -fsSL --max-time 3 https://pypi.org/pypi/pip/json >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

ensure_virtualenv_available() {
  if python3 -m virtualenv --version >/dev/null 2>&1; then
    return 0
  fi
  if python3 -m pip install --user --no-index --find-links "${WHEEL_ROOT}" virtualenv >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${ALLOW_PYPI}" == "1" ]] || has_network; then
    python3 -m pip install --user virtualenv
    return 0
  fi
  return 1
}

create_venv() {
  if python3 -m venv "${VENV_DIR}"; then
    return 0
  fi
  echo "[Tri-ARC] python3 -m venv failed; attempting virtualenv fallback." >&2
  rm -rf "${VENV_DIR}"
  if ensure_virtualenv_available && python3 -m virtualenv "${VENV_DIR}"; then
    return 0
  fi
  echo "[Tri-ARC] ERROR: Unable to create virtual environment via python3 -m venv or virtualenv." >&2
  return 1
}

install_requirements() {
  echo "[Tri-ARC] Installing requirements from wheel cache."
  if pip install --no-index --find-links "${WHEEL_ROOT}" -r "${REQUIREMENTS_FILE}"; then
    return 0
  fi
  if [[ "${ALLOW_PYPI}" == "1" ]] || has_network; then
    echo "[Tri-ARC] Offline install failed; falling back to PyPI (extra index: ${PIP_EXTRA_INDEX_URL})."
    pip install --extra-index-url "${PIP_EXTRA_INDEX_URL}" -r "${REQUIREMENTS_FILE}"
    return $?
  fi
  echo "[Tri-ARC] ERROR: Offline install failed and PyPI fallback is disabled/unavailable." >&2
  return 1
}

create_venv
source "${VENV_DIR}/bin/activate"

install_requirements

echo "[Tri-ARC] Kaggle environment bootstrap complete."
