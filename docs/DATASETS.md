# Datasets

Tri-ARC consumes three primary data sources: the official ARC-AGI-2 training set, the ARC-AGI-2 public evaluation set, and the internally generated ARC-Forge adversarial suite. This document outlines directory layouts, loading APIs, and synthesis workflows.

## ARC-AGI-2 Dataset Structure
- **Root layout** (relative to the repository workspace):
  ```
  data/
    arcagi2/
      train/
        task_xxxxx.json
      evaluation/
        task_yyyyy.json
  ```
- **File format**: Each JSON file contains `train` and `test` arrays. Entries provide `input` and `output` grids represented as nested integer lists.
- **Naming**: File IDs map to Kaggle task identifiers; keep them stable for reproducibility and cross-referencing.
- **Metadata cache**: During preprocessing, the coordinator writes per-task metadata (grid size, palette stats, object metrics) to `cache/meta/<task_id>.json` to avoid repeated parsing.

## Data Loading Interface
- Use the dataset loader in `arc/data/loader.py` (planned) that exposes:
  - `load_task(task_id)` returning structured tensors and metadata.
  - `iter_split(split="train")` yielding batches compatible with the scheduler.
- Loader guarantees deterministic ordering and sets numpy/torch seeds.
- Supports lazy loading with caching to minimise disk IO during the 12-hour run.
- Augmentations for TTT (symmetry flips, colour remaps) are defined in `arc/data/augment.py` to keep training logic separate from dataset parsing.

## ARC-Forge Generation Pipeline
1. **Seeding**: Start from failure cases logged by the arbitrator. Extract rules or primitives that caused difficulty.
2. **Program synthesis**: Use DSL templates to create new puzzle programs that emphasise the failure pattern (e.g., multi-step symmetry).
3. **Validation**: Automatically check generated tasks for human solvability heuristics (bounded size, limited colours) and ensure they are not duplicates.
4. **Filtering**: Run baseline solvers to keep only tasks that current Tri-ARC configurations fail or solve near timeout.
5. **Packaging**: Store generated tasks under `data/arc_forge/<date>/` with metadata describing the originating failure mode.

ARC-Forge tasks feed curriculum learning and ablation experiments. They remain separate from the official evaluation split to avoid contamination.

## Offline Deployment Considerations
- All datasets must be packaged with the final Kaggle notebook; no downloads are allowed once execution starts.
- Use `scripts/package_data.py` to assemble tarballs and verify checksums before upload.
- Disk quotas require pruning obsolete ARC-Forge batches; keep only the most informative subsets referenced by experiments.

## Provenance Logging
- Each task processed logs its origin (`arcagi2_train`, `arcagi2_eval`, `arc_forge`), version hash, and preprocessing timestamp.
- Logs integrate with `docs/EVAL_PROTOCOL.md` so reproduction steps can rehydrate identical data snapshots.
