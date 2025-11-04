This directory contains reproducible environment definitions for Tri-ARC.

- `conda/environment.yml` provisions a Python 3.11 / CUDA 12.1 stack that matches the Kaggle offline runtime.
- `docker/Dockerfile` builds a container image with the same dependency set for CI smoke tests and containerised workflows.

Use the automation in `scripts/setup_local_env.sh` and `scripts/setup_kaggle_env.sh` to materialise these environments.
