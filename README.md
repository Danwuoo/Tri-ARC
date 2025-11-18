# Tri-ARC

Tri-ARC is a modular ARC solver that mixes symbolic program synthesis, TTT
reasoning, and LLM coordination. This repository contains the training
datasets, orchestration glue, and per-module documentation used during the
current research sprint.

## Symbolic Lane Documentation
- Overview & onboarding: `docs/MODULES/SYMBOLIC.md`
- Configuration reference (mirrors `arc.symbolic.default_config()`):
  `docs/MODULES/symbolic/configuration.md`
- Subsystem deep dives: `docs/MODULES/symbolic/*.md`

## Doc Link Checks

Broken Markdown references tend to rot quickly when docs move between folders.
Use the lightweight verifier before pushing documentation changes:

```bash
python scripts/check_doc_links.py
```

Run it without arguments to scan the entire `docs/` tree or pass specific files
and directories if you want to focus on a subsection.
