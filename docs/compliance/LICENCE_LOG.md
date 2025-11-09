# Tri-ARC Licence Log

This log records third-party artefacts bundled with the offline package and their licence obligations. Review before publishing new bundles.

| Component | Version / Snapshot | Licence | Notes |
|-----------|-------------------|---------|-------|
| ARC-AGI2 dataset (`data/arcagi2/`) | Kaggle ARC-AGI2 (2023-08 snapshot) | CC BY-SA 4.0 | Redistribution permitted with attribution; bundle retains original README metadata. |
| PyTorch (`torch`, `torchvision`, `torchaudio`) | 2.3.0 / 0.18.0 / 2.3.0 | BSD-3-Clause | Wheels cached under `vendor/wheels/`; binaries distributed per upstream licence. |
| NumPy | 1.26.4 | BSD-3-Clause | Required for interpreter and feature extraction. |
| SciPy | 1.11.4 | BSD-3-Clause | Pulled for numerical kernels. |
| pandas | 2.1.4 | BSD-3-Clause | Used in analysis utilities; included in offline cache. |
| z3-solver | 4.12.4.0 | MIT | SMT backend; wheel cached for offline installs. |
| Hydra-Core / OmegaConf | 1.3.2 / 2.3.0 | MIT | Configuration stack for runtime. |
| tqdm | 4.66.4 | MIT | Progress reporting in CLI tools. |
| rich | 13.7.1 | MIT | Console formatting for diagnostics. |
| jsonschema | 4.21.1 | MIT | Validation of DSL schemas and configs. |
| orjson | 3.10.7 | Apache-2.0 | Fast JSON serialization for reports. |
| msgpack | 1.0.8 | Apache-2.0 | Artefact caching, optional. |
| PyYAML | 6.0.1 | MIT | Configuration parsing. |

## Maintenance Checklist

- [x] Wheel cache refreshed (`vendor/wheels/manifest.sha256` generated on 2025-11-04).
- [x] Offline data bundle rebuilt (`dist/data_bundle.tar.gz`, 2025-11-04).
- [x] Asset inventory exported (`reports/offline_inventory_20251104.json`).
- [ ] Confirm downstream consumers acknowledge upstream attribution when repackaging.
- [ ] Re-run licence diff before next release to capture new dependencies.
