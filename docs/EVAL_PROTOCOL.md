# Evaluation Protocol

Tri-ARC evaluation mirrors ARC-AGI-2 competition constraints: offline execution, a 12-hour wall-clock limit, and pass@2 scoring. Follow this guide to run reproducible assessments.

## Scoring
- **Metric**: pass@2 accuracy. A task is correct if either of the two submitted outputs matches the ground truth exactly.
- **Submission format**: For each task, emit a JSON list containing up to two output grids in the order chosen by the arbitrator (see `docs/ARBITRATOR_RULES.md`).
- **Reporting**: Aggregate accuracy over the evaluation split, plus per-module solve rates and average verification latency.

## Offline Environment
- **Runtime**: Kaggle Notebook (or equivalent 4xGPU server) with no internet access.
- **Hardware assumption**: Up to four GPUs (A100 or L4 class), 48-64 CPU cores, and 96-128 GB system RAM.
- **Software stack**:
  - Python 3.11
  - PyTorch with CUDA support
  - Z3 binaries compatible with CUDA environment
  - Auxiliary tools (`torch.profiler`, Nsight CLI, `ripgrep`) bundled locally
- **Determinism**: Seed numpy, torch, and Python RNGs at startup. Record seeds in run metadata.

## 12-Hour Limit Management
- Scheduler monitors elapsed wall-clock time and adjusts per-task budgets (see `docs/SCHEDULER_POLICY.md`).
- Profiling hooks capture average runtime per module; if estimates exceed the remaining budget, the coordinator reduces candidate generators and prioritises high-confidence solves.
- Periodic checkpoints (every 30 minutes) persist intermediate outputs so interrupted runs can resume without restarting solved tasks.

## Reproduction Steps
1. **Prepare environment**:
   - Clone the repository or unpack the competition bundle.
   - Verify data directories as described in `docs/DATASETS.md`.
   - Install dependencies from `environment.yml` or `requirements.txt`.
2. **Launch evaluation**:
   - Execute `python scripts/run_eval.py --split evaluation --max_hours 12`.
   - The script initialises scheduler, modules, SMT gatekeeper, and arbitrator.
3. **Monitor progress**:
   - Tail `logs/runtime.log` for module allocation and arbitrator decisions.
   - Inspect `metrics.jsonl` for rolling accuracy and budget usage.
4. **Collect results**:
   - Final outputs stored under `outputs/pass2.json`.
   - Summary stats in `reports/eval_summary.md`.
5. **Validate reproducibility**:
   - Re-run with identical seeds and confirm metric parity (difference <=0.1%).

## Post-Evaluation Checks
- Run ablation scripts (`python tools/ablate.py`) to attribute performance to individual modules.
- Archive logs and metrics with timestamped hashes for future comparison.
- Feed unsolved tasks into the ARC-Forge generator pipeline (see `docs/DATASETS.md`) to expand adversarial training.
