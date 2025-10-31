# Environment Manifests

- `conda/environment.yml` — canonical dependency lock for local development (Python 3.11, CUDA 12.1).
- `docker/Dockerfile` — container baseline mirroring the conda environment with support for offline wheel installation.

Provisioning helpers in `scripts/` consume these manifests:

- `setup_local_env.sh` — refresh local conda env, capture reports.
- `setup_kaggle_env.sh` — bootstrap Kaggle notebooks using the offline wheel cache.
- `build_wheel_cache.sh` — pre-download wheels into `vendor/wheels/`.

Update these manifests when dependencies change and regenerate wheel caches to keep Kaggle and Docker builds in sync.
