This directory contains reproducible environment definitions for Tri-ARC.

- `conda/environment.yml` provisions a Python 3.11 / CUDA 12.1 stack that matches the Kaggle offline runtime.
- `docker/Dockerfile` builds a container image with the same dependency set for CI smoke tests and containerised workflows.

Use `scripts/setup_local_env.sh` for local/offline hosts; Kaggle notebooks should instead run the Python bootstrap cell described in `docs/ENV_SETUP.md` to install dependencies in-place.
