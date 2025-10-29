# Test-Time Training Module

The TTT lane adapts a differentiable grid interpreter on-the-fly using the few I/O examples bundled with each ARC task. Its role is to capture statistical cues and subtle invariants that deterministic search may miss.

## Objectives
- Rapidly personalise model weights during inference while respecting per-task time budgets.
- Inject priors about ARC physics (color conservation, object persistence) through auxiliary losses.
- Produce grid predictions that can be fed to the arbitrator alongside symbolic and LLM outputs.

## Model Backbone
- **Base architecture**: A convolutional transformer hybrid that ingests stacked grids and object descriptors.
- **Parameter exposure**: Only a small adapter subset and layer-normalisation parameters remain trainable during TTT to keep updates stable.
- **State caching**: Intermediate activations for support examples are cached so multiple adaptation steps avoid recomputation.

## Adaptation Regimen
1. **Support set assembly**: Concatenate the provided I/O pairs plus synthetic augmentations (symmetry flips, color re-mappings) constrained by task metadata.
2. **Loss portfolio**:
   - **Reconstruction loss** on output grids.
   - **Color conservation loss** penalising ungrounded palette drift.
   - **Object count loss** discouraging spurious object creation or deletion.
   - **Smoothness loss** favouring consistent local patterns when evidence is scarce.
3. **Optimiser**: AdamW with cosine decay and gradient clipping tailored for short bursts (8-24 steps).
4. **Early stopping**: Monitor validation agreement on withheld examples and halt when improvement stagnates.
5. **Ensembling**: Optionally maintain a small ensemble of adapted checkpoints to increase diversity for the arbitrator.

## Interaction With The Coordinator
- The scheduler selects learning rates, step counts, and augmentation recipes based on task difficulty heuristics.
- Upon convergence, the module emits predicted outputs plus confidence scores derived from ensemble variance and loss trajectories.
- If adaptation diverges, the module resets to the frozen base weights, switches to a conservative configuration, and retrains within the remaining budget.

## Resource Footprint
- Runs primarily on a dedicated GPU with mixed-precision training to cap VRAM usage.
- Uses gradient checkpointing and activation offloading to the CPU when grids are large.
- Profiling monitors per-step latency, achieved occupancy, and the ratio of successful vs. reset runs.

## Failure Modes And Mitigations
- **Overfitting to support examples**: Controlled by early stopping, dropout, and colour/object priors.
- **Gradient explosion**: Guarded by clipping and by restricting the set of trainable parameters.
- **Ambiguous tasks**: When losses plateau at multiple candidate solutions, the module delivers the top two outputs to the arbitrator for pass@2 coverage.

## Future Enhancements
- Train a meta-learner that predicts adaptation hyperparameters from task descriptors.
- Incorporate contrastive objectives that align latent representations of similar objects across examples.
- Add explainability hooks that track which features shifted most during adaptation for downstream reporting.
