#!/usr/bin/env python3
"""Generate dependency graphs for the arc.symbolic package.

The script parses Python files under arc/symbolic, builds the import graph,
detects circular dependencies, and emits JSON + Mermaid artifacts that can be
referenced from docs.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYMBOLIC_ROOT = PROJECT_ROOT / "arc" / "symbolic"


def iter_python_modules(root: Path) -> Iterable[Tuple[str, Path, bool]]:
    """Yield (module_name, path, is_package) for every Python file under root."""
    for path in sorted(root.rglob("*.py")):
        if path.name == "__pycache__":
            continue
        try:
            rel = path.relative_to(PROJECT_ROOT)
        except ValueError:
            continue
        parts = rel.with_suffix("").parts
        is_package = False
        if parts[-1] == "__init__":
            is_package = True
            parts = parts[:-1]
        module = ".".join(parts)
        yield module, path, is_package


def resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    """Resolve a relative import into an absolute module string."""
    if not module:
        return target or ""

    parts = module.split(".")
    if is_package:
        base = parts.copy()
    else:
        base = parts[:-1] or parts

    if level:
        drop = max(level - 1, 0)
        if drop > len(base):
            base = []
        else:
            base = base[: len(base) - drop]

    if target:
        base.extend(target.split("."))
    return ".".join(base)


def collect_imports(module: str, source: Path, *, is_package: bool) -> Set[str]:
    """Return symbolic module dependencies referenced by the file."""
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source))
    deps: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith("arc.symbolic"):
                    deps.add(name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None and node.level == 0:
                continue
            if node.level:
                resolved = resolve_relative(module, is_package, node.level, node.module)
            else:
                resolved = node.module or ""
            if resolved.startswith("arc.symbolic"):
                deps.add(resolved)
    deps.discard(module)
    return deps


def strongly_connected_components(graph: Dict[str, Set[str]]) -> List[List[str]]:
    """Tarjan's algorithm."""
    index = 0
    stack: List[str] = []
    indices: Dict[str, int] = {}
    lowlinks: Dict[str, int] = {}
    on_stack: Set[str] = set()
    result: List[List[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] == indices[node]:
            component: List[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                component.append(w)
                if w == node:
                    break
            if len(component) > 1:
                result.append(sorted(component))

    for node in graph:
        if node not in indices:
            strongconnect(node)

    return sorted(result, key=lambda comp: (len(comp), comp))


def collapse_module(module: str, depth: int) -> str:
    parts = module.split(".")
    return ".".join(parts[:depth])


@dataclass
class DepGraphArtifacts:
    adjacency: Dict[str, Set[str]]
    cycles: List[List[str]]


def build_graph(root: Path) -> DepGraphArtifacts:
    adjacency: Dict[str, Set[str]] = defaultdict(set)
    for module, path, is_package in iter_python_modules(root):
        if not module.startswith("arc.symbolic"):
            continue
        deps = collect_imports(module, path, is_package=is_package)
        if deps:
            adjacency[module].update(deps)
        else:
            adjacency.setdefault(module, set())
    cycles = strongly_connected_components(adjacency)
    return DepGraphArtifacts(adjacency=adjacency, cycles=cycles)


def export_json(graph: DepGraphArtifacts, output: Path) -> None:
    payload = {
        "root": "arc.symbolic",
        "module_count": len(graph.adjacency),
        "edge_count": sum(len(v) for v in graph.adjacency.values()),
        "cycles": graph.cycles,
        "adjacency": {k: sorted(v) for k, v in sorted(graph.adjacency.items())},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def export_mermaid(graph: DepGraphArtifacts, output: Path, depth: int) -> None:
    collapsed: Dict[str, Set[str]] = defaultdict(set)
    for src, targets in graph.adjacency.items():
        c_src = collapse_module(src, depth)
        for target in targets:
            c_tgt = collapse_module(target, depth)
            if c_src == c_tgt:
                continue
            collapsed[c_src].add(c_tgt)

    lines = ["%% Autogenerated by tools/generate_symbolic_depmap.py", "graph LR"]
    for src in sorted(collapsed):
        for tgt in sorted(collapsed[src]):
            lines.append(f'    "{src}" --> "{tgt}"')

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SYMBOLIC_ROOT, help="Path to arc/symbolic root.")
    parser.add_argument("--json-out", type=Path, default=PROJECT_ROOT / "reports" / "symbolic" / "dependency_graph.json")
    parser.add_argument("--mermaid-out", type=Path, default=PROJECT_ROOT / "docs" / "symbolic" / "import_graph.mmd")
    parser.add_argument("--collapse-depth", type=int, default=3, help="Module depth used by the Mermaid summary.")
    args = parser.parse_args()

    graph = build_graph(args.root)
    export_json(graph, args.json_out)
    export_mermaid(graph, args.mermaid_out, depth=args.collapse_depth)
    print(f"Wrote {args.json_out} and {args.mermaid_out}")


if __name__ == "__main__":
    main()
