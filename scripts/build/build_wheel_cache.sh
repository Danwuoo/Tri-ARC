#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WHEEL_ROOT="${PROJECT_ROOT}/vendor/wheels"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
EXTRA_INDEX_URL="${EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"
MANIFEST_FILE="${WHEEL_ROOT}/manifest.sha256"

TARGET_PLATFORM="${PIP_PLATFORM:-manylinux2014_x86_64}"
TARGET_PYTHON="${PIP_PYTHON_VERSION:-3.11}"
TARGET_IMPLEMENTATION="${PIP_IMPLEMENTATION:-cp}"
TARGET_ABI="${PIP_ABI:-cp311}"
NO_BINARY_DEFAULT="${PIP_NO_BINARY-}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[Tri-ARC] Python interpreter not found." >&2
  exit 1
fi

mkdir -p "${WHEEL_ROOT}"

echo "[Tri-ARC] Downloading wheels into ${WHEEL_ROOT}"
PIP_ARGS=(
  "--dest" "${WHEEL_ROOT}"
  "--extra-index-url" "${EXTRA_INDEX_URL}"
  "--platform" "${TARGET_PLATFORM}"
  "--python-version" "${TARGET_PYTHON}"
  "--implementation" "${TARGET_IMPLEMENTATION}"
  "--abi" "${TARGET_ABI}"
  "--only-binary" ":all:"
  "-r" "${REQUIREMENTS_FILE}"
)

if [[ -n "${NO_BINARY_DEFAULT}" ]]; then
  PIP_ARGS+=("--no-binary" "${NO_BINARY_DEFAULT}")
fi

"${PYTHON_BIN}" -m pip download "${PIP_ARGS[@]}"

echo "[Tri-ARC] Generating checksum manifest at ${MANIFEST_FILE}"
export WHEEL_ROOT
export MANIFEST_FILE

"${PYTHON_BIN}" - <<'PY'
import hashlib
import os
from pathlib import Path

wheels_dir = Path(os.environ["WHEEL_ROOT"])
manifest_path = Path(os.environ["MANIFEST_FILE"])

entries = []
for wheel in sorted(wheels_dir.glob("*.whl")):
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    entries.append(f"{digest}  {wheel.name}")

manifest_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
print(f"[Tri-ARC] Wrote {len(entries)} entries to {manifest_path}")
PY

echo "[Tri-ARC] Wheel cache ready."
