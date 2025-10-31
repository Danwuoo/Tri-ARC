# Quickstart Runbook

Goal: get Tri-ARC running on a small smoke split within 30 minutes on a development workstation.

## Prerequisites
- Environment configured per `docs/ENV_SETUP.md`.
- Datasets placed under `data/arcagi2/`.
- At least one GPU available (>=16 GB VRAM).

## Steps
1. **Clone and install**
   ```
   git clone <repo> Tri-ARC
   cd Tri-ARC
   bash scripts/setup_local_env.sh
   ```
2. **Verify hardware**
   ```
   python scripts/check_gpu.py
   ```
   Confirm four devices or adjust `docs/CONFIG_DEFAULTS.yaml` if fewer.
3. **Stage caches**
   ```
   python scripts/precompute_metadata.py --split train --limit 50
   ```
4. **Run smoke evaluation**
   ```
   python run_eval.py --split smoke --max_tasks 5 --config docs/CONFIG_DEFAULTS.yaml
   ```
5. **Inspect outputs**
   - Results: `outputs/pass2.json`
   - Metrics: `metrics.jsonl`
   - Logs: `logs/runtime.log`
6. **Tag errors**
   - Use `python tools/tag_errors.py --log metrics.jsonl --taxonomy docs/ERROR_TAXONOMY.md`
7. **Next steps**
   - Review module docs under `docs/MODULES/`
   - Plan ablations via `docs/ABLATIONS.md`

## Troubleshooting
- If imports fail, re-run dependency install steps.
- For GPU OOM, lower LLM candidate counts in `docs/CONFIG_DEFAULTS.yaml`.
- Consult `docs/DEBUG_PLAYBOOK.md` for module-specific troubleshooting.
