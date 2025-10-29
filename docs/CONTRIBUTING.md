# Contributing Guide

Thank you for helping build Tri-ARC. This guide describes the workflow, coding standards, testing expectations, and change log process for collaborators.

## Branching Strategy
- `main`: Stable branch that mirrors the latest release candidate. Always green on CI.
- `develop`: Integration branch for upcoming release work. Feature branches merge here via pull requests.
- Feature branches: Use `feature/<short-desc>` (e.g., `feature/ttt-loss-tuning`).
- Hotfix branches: Use `hotfix/<issue-id>`. Merge into both `main` and `develop`.
- Keep branches rebased on `develop` to minimise merge conflicts.

## Code Style
- **Python**: Follow PEP 8 with `black` (line length 100) and `isort`. Type hints required for public functions.
- **C++/CUDA**: Use LLVM style via `clang-format`.
- **YAML/JSON**: Two-space indentation, keys sorted alphabetically when reasonable.
- **DSL examples**: Inline small programs; use fenced code blocks for longer snippets.
- **Comments**: Add concise comments only when logic is non-obvious (see system instructions).

## Testing Requirements
- Unit tests: `pytest tests/` must pass for modified areas. Add tests covering new functionality.
- Smoke tests: `python run_eval.py --split smoke --max_tasks 5` should complete under 15 minutes.
- Linting: Run `scripts/lint.sh` (wraps `black`, `isort`, `flake8`).
- Optional: `scripts/profile.sh` for performance-sensitive changes.
- Provide test evidence in the pull request description (command outputs or summary).

## Review Process
- Open a pull request targeting `develop`.
- Fill out the PR template, including risk assessment and testing status.
- Request review from module owners (`docs/ARCHITECTURE.md` outlines responsibilities).
- Address comments promptly; mark updates with follow-up commits or amend.
- Squash commits on merge unless review history needs preservation.

## Change Log
- Update `CHANGELOG.md` under the "Unreleased" section with:
  - Added / Changed / Fixed / Removed bullet.
  - Reference issue or PR ID.
- For release branches, move entries into a dated version section.

## Documentation
- Update relevant docs when behaviour changes (architecture, modules, scheduler, prompts, etc.).
- Keep ASCII text unless existing file uses non-ASCII.
- Link new docs from `docs/README.md` (to be created) when available.

## Collaboration Etiquette
- Prefer asynchronous discussion via issues. Summaries should include reproduction steps and log snippets.
- Assign yourself to tasks to avoid duplicated work.
- Respect the offline constraint: do not add dependencies that require runtime downloads.

## Contact
- For urgent issues, ping maintainers on the project chat (offline mirror).
- Escalate environment problems to the Infra contact listed in `docs/ENV_SETUP.md`.
