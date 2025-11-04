#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHEEL_ROOT="${PROJECT_ROOT}/vendor/wheels"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
EXTRA_INDEX_URL="https://download.pytorch.org/whl/cu121"
MANIFEST_FILE="${WHEEL_ROOT}/manifest.sha256"

mkdir -p "${WHEEL_ROOT}"

echo "[Tri-ARC] Downloading wheels into ${WHEEL_ROOT}"
python -m pip download --dest "${WHEEL_ROOT}" --extra-index-url "${EXTRA_INDEX_URL}" -r "${REQUIREMENTS_FILE}"

echo "[Tri-ARC] Generating checksum manifest at ${MANIFEST_FILE}"
export WHEEL_ROOT
export MANIFEST_FILE

python - <<'PY'
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
