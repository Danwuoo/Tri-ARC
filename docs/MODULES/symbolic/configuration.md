# Symbolic Configuration Reference

This guide documents the structure returned by `arc.symbolic.default_config()`,
which wraps the canonical `docs/CONFIG_DEFAULTS.yaml` file and exposes the
`symbolic` block as a ready-to-use dictionary. Every key referenced below ships
with a concrete default so the solver can boot without experiment-specific
fragments.

## Quick Start
- Load the entire configuration: `config = arc.config.load_config()`
- Access only the symbolic block: `symbolic_cfg = arc.symbolic.default_config()`
- Override settings without mutating the global defaults:
  ```python
  from arc.symbolic import default_config

  symbolic_cfg = default_config(overrides={"beam_width": 128, "smt": {"enabled": False}})
  ```
- Pass these dictionaries directly into `SymbolicModule` or `SymbolicSolver`.

## Top-Level Keys

| Key | Default | Purpose |
| --- | --- | --- |
| `enabled` | `true` | Master toggle for the module. |
| `seed` | `1337` | Deterministic seeding for reproducibility. |
| `search_strategy` | `"beam"` | One of `beam`, `dfs`, or `iddfs`. |
| `max_depth` | `16` | Depth cap for enumerated programs. |
| `max_expansions` | `5000` | Hard stop on enumerator expansions. |
| `max_nodes` | `40000` | Optional node budget; omitted by default. |
| `beam_width` | `96` | Preferred beam width when explicitly set. |
| `beam_width_minimum` | `16` | Floor used when `beam_width` is missing/invalid. |
| `soft_timeout_s` | `90` | Grace period before winding down. |
| `hard_timeout_s` | `150` | Absolute time budget per task. |
| `heuristics_model_path` | `models/symbolic/heuristic.pt` | Default neural model weights. |

## Subsystem Blocks

Each nested block mirrors the YAML layout. The highlights below are the values
consumed directly by `SymbolicSolver`.

### Heuristics (`symbolic.heuristics`)
- **Mode**: `"hybrid"` to blend rule-based and neural scoring.
- **Rule-based**: Enabled by default with weights for coverage, consistency,
  progress, novelty, depth, cost, stagnation, and a normalisation scale.
- **Neural**: Enabled with a shared model + checksum path. Set
  `requires_checksum` when you want CI to enforce artifact integrity.
- **Calibration**: Keeps neural output within `[0, 1]`, auto-selecting the
  midpoint unless overridden via `midpoint`.

### Intermediate Representation (`symbolic.ir`)
- Disabled by default; set `enabled: true` to activate object-centric lookups.
- Controls connectivity (4- or 8-neighbourhood) and minimum object size.

### SMT Gateway (`symbolic.smt`)
- Disabled by default for the module-level section but enabled within the
  `verification` block (see below). Top-level SMT keys specify token issuance,
  virtual credential prefix, BDD toggles, and per-candidate timeouts.

### Symmetry (`symbolic.symmetry`)
- Enables canonical colour relabelling, symmetry detection (reflection,
  rotation, dihedral), step normalisation, and quotient search.

### CEGIS & Verification (`symbolic.cegis`)
- CEGIS loop is enabled with 10 iterations, counterexample minimisation, and
  invariant checks (colour conservation, object counts, topology).

### Search Enhancements (`symbolic.search`)
- Flags for sketch-guided synthesis, abstract interpretation, PCFG,
  Monte-Carlo Tree Search, and diversity control. Each subsection (e.g.
  `pcfg`, `mcts`) provides its own knobs for smoothing constants or depth.

### Library Management (`symbolic.library`)
- `fragment_mining`, `rule_learning`, and `pruning` all default to enabled.
- Persistence options point at `models/symbolic/dsl_library.json` with regular
  backups.

### Decomposition (`symbolic.decomposition`)
- Enables object-centric decomposition plus optional parallel synthesis and
  composition thresholds.

### Coordination (`symbolic.coordination`)
- Independent toggles for TTT and LLM hooks, including timeouts and whether
  invariants, relations, sketches, or macros should be exchanged.
- `fallback_on_failure` coordinates fallback heuristics when partner modules
  raise errors.

### Engineering (`symbolic.engineering`)
- Enables caching, adaptive budgets, timeout guards, circuit breakers,
  telemetry, and artifact management. Each nested block mirrors the dedicated
  engineering documentation for precise knobs.

### Telemetry (`symbolic.telemetry`)
- Progress JSONL path, diagnostics directory, checkpoint cache, frontier log,
  and report directory. All directories are created on demand by the solver.

### Cost Model (`symbolic.cost_model`)
- Weighting for length, complexity, generality, and execution plus a per-
  operator complexity table used by the e-graph extractor.

## Beam Search Defaults & Fallbacks

`SymbolicSolver` enforces a deterministic minimum beam width through the
following rules:

1. Read the first defined option among `beam_width_minimum`,
   `min_beam_width`, or `default_beam_width`.
2. Clamp the result to an integer `>= 1`. If parsing fails, fall back to `16`
   and log a warning.
3. Whenever `search_strategy` resolves to beam search but `symbolic.beam_width`
   is missing, non-positive, or unparsable per task,
   `beam_width_minimum` becomes the active width and is recorded in the solve
   summary.

This means experiments can safely omit `beam_width` overrides—beam search will
still run using the configured floor instead of silently disabling itself.

## Input Validation & Status Codes

Before synthesis starts, the solver normalises every training example:

- Each example must be a mapping with `input`/`output` (or `_grid`) keys.
- Inputs are converted to rectangular 2D lists (or `Grid` objects) with at
  least one row and one column. Rows must be iterable sequences; bytes/strings
  are rejected with explicit diagnostics.
- Missing grids raise `TaskValidationError` entries tagged with the example
  index, grid role, and failure reason.
- Empty task payloads trigger `invalid_task` with the message “No training
  examples were provided.”

When validation fails, `SymbolicSolver.solve()` returns a module summary with:

- `status: "failed"` and `reason: "invalid_task"`.
- A `validation_errors` array that summarises each diagnostic.
- `self._dispatch_failure_feedback(...)` is invoked so coordination partners
  receive the invalid-task status as well.

Downstream consumers should surface these diagnostics verbatim rather than
retrying, because the solver has not yet consumed any budgets.

## Related Documentation

- Module overview: `docs/MODULES/SYMBOLIC.md`
- Subsystem details: `docs/MODULES/symbolic/*.md`
- Default YAML source: `docs/CONFIG_DEFAULTS.yaml`
