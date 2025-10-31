#!/usr/bin/env bash
set -euo pipefail

# Build the offline wheel cache for Tri-ARC.
# Requires internet access and should be run from a machine with CUDA-compatible
# wheels available (e.g., Linux x86_64).

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/vendor/wheels"
REQUIREMENTS="${ROOT_DIR}/requirements.txt"

mkdir -p "${OUTPUT_DIR}"
echo "[INFO] Downloading wheels into ${OUTPUT_DIR}"

pip download \
  --only-binary=:all: \
  --requirement "${REQUIREMENTS}" \
  --dest "${OUTPUT_DIR}" \
  --extra-index-url https://download.pytorch.org/whl/cu121

echo "[INFO] Wheel cache populated."
