# Documentation Guide & Classification

This guide defines how the `docs/` tree is organized, how to extend it, and the
expected hygiene rules for every addition or edit. Treat it as the canonical
reference before touching documentation.

## 1. Directory Taxonomy

| Path | Purpose | Examples |
| --- | --- | --- |
| `docs/handbook/` | Strategy-level and benchmarking guides that describe *why* the system exists and how it is evaluated. | `architecture.md`, `evaluation_suite.md` |
| `docs/reference/` | Canonical specs and API-level references. Content here must remain source-of-truth material. | `dsl_reference.md`, `api/`, `MODULES/` |
| `docs/operations/` | Runbooks, deployment notes, and troubleshooting content for day-to-day operations. | `runtime_playbook.md`, `troubleshooting.md` |
| `docs/policies/` | Governance artifacts, orchestration rules, compliance rules, and process documents. | `orchestration.md`, `compliance/` |
| `docs/original_plan/` | Historical proposals. Keep read-only for provenance. | Tri-ARC framework plan |
| Root files (`changelog`, `CONFIG_DEFAULTS`, etc.) | Cross-cutting assets referenced by automation or tooling. | `CONFIG_DEFAULTS.yaml`, `CONTRIBUTING.md` |

**Rule:** every new document must live in exactly one bucket. If the scope
spans buckets, split the content and link between files instead of duplicating.

## 2. Naming & Structure Rules

1. File names are lowercase with underscores and always end in `.md` unless a
   spec explicitly requires another extension (e.g., YAML config samples).
2. Top-level heading (`# Title`) must match the filename’s human-readable form.
3. Provide a two-sentence synopsis underneath the heading explaining *why* the
   document exists.
4. Use second-level headings (`##`) for persistent sections to keep generated
   tables of contents stable.
5. Cross-link related docs using relative paths (e.g.,
   `[Runtime Playbook](../operations/runtime_playbook.md)`).
6. When embedding content from specs or code, prefer snippets fenced with a
   language hint to keep formatting consistent.

## 3. Editing Workflow

1. **Assess overlap:** before editing, search (`rg`) for similar topics. If the
   content already exists elsewhere, consolidate rather than append.
2. **Update the right bucket:** edits to runtime procedures go in
   `operations/`, reference material belongs in `reference/`, etc.
3. **Document moves/merges:** when merging or relocating files, note the change
   in `docs/changelog.md` or the relevant project changelog entry.
4. **Keep diffs atomic:** each PR/patch should change either content or
   structure for one topic. Avoid bundling unrelated documentation updates.
5. **Lint locally:** run `rg --files docs | sort` to confirm no orphaned files
   remain, and render markdown preview if headings were reordered.

## 4. Adding New Documents

Follow this checklist when introducing a new file:

1. **Choose the directory** from the taxonomy table above.
2. **Reserve the filename** that mirrors the final title (e.g.,
   `docs/policies/release_governance.md` for “Release Governance”).
3. **Create a seed outline** with at least three second-level headings to avoid
   dumping wall-of-text content.
4. **Link from existing hubs:** add a short entry in the nearest overview file
   (e.g., mention a new policy doc inside `orchestration.md`).
5. **Log the addition:** update `docs/changelog.md` with a bullet describing the
   new resource, including who needs to read it.

## 5. Review Checklist

Before submitting documentation updates, reviewers should verify:

- The file sits in the correct directory and follows naming rules.
- Redundant content (if any) was removed and references updated.
- Links resolve using relative paths.
- Tables, code blocks, and diagrams are still readable after formatting.
- Sections reference the current code paths (e.g., solver modules) when
  describing behavior.

Keeping these rules enforced ensures the documentation set remains searchable,
deduplicated, and aligned with the project’s growth.

