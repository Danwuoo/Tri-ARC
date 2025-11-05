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
   - Execute `python scripts/run_eval.py --preset evaluation --split evaluation --run-id eval-<tag>`.
   - Use `--preset smoke` for quick sanity checks or `--resume-from <run_dir>` to continue an interrupted run.
   - The harness initialises scheduler, modules, the SMT gatekeeper, and the arbitrator, creating a dedicated run directory under `reports/eval_runs/<tag>`.
3. **Monitor progress**:
   - Tail `<run_dir>/logs/runtime.log` for scheduler allocations and arbitrator decisions.
   - Watch `<run_dir>/metrics.jsonl` (and the consolidated `reports/eval_summary.md`) for rolling accuracy, fallback usage, and latency.
   - Inspect `<run_dir>/run_state.json` for resumable checkpoints.
4. **Collect results**:
   - Kaggle-ready outputs are written to `<run_dir>/outputs/pass2.json`.
   - Reproducibility metadata lives in `<run_dir>/reports/eval_manifest_<tag>.md` alongside the copied `eval_summary.md` and `eval_history.md` snapshots.
   - Packaged artefacts (logs, metrics, outputs) are assembled automatically at `<run_dir>/archives/<run_id>_artefacts.zip`.
5. **Validate reproducibility**:
   - Re-run with identical seeds and confirm metric parity (difference <=0.1%).
   - Compare successive runs with `python tools/compare_runs.py <run_a> <run_b>`; deltas are also recorded in `reports/eval_delta_<run_id>.md`.

## Post-Evaluation Checks
- Run ablation suites with `python tools/ablate.py --preset smoke --split smoke` to isolate module contributions; consolidated results are written to `reports/ablations/`.
- Review `reports/eval_history.md` (rendered from the JSONL ledger) for trends across nightly smoke and weekly full runs.
- Generate side-by-side comparisons with `tools/compare_runs.py`, especially before shipping new configs.
- Feed unsolved tasks (listed in each run manifest) into the ARC-Forge generator pipeline (see `docs/DATASETS.md`) to expand adversarial training datasets.
