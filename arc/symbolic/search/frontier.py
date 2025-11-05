from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from .types import FrontierSnapshot


def _format_snapshot(snapshot: FrontierSnapshot) -> str:
    best = "-" if snapshot.best_score is None else f"{snapshot.best_score:.4f}"
    worst = "-" if snapshot.worst_score is None else f"{snapshot.worst_score:.4f}"
    notes = json.dumps(snapshot.notes, sort_keys=True) if snapshot.notes else ""
    return (
        f"| {snapshot.timestamp:.3f} | {snapshot.strategy} | {snapshot.total_nodes} | "
        f"{snapshot.pending_nodes} | {snapshot.expanded_nodes} | {snapshot.pruned_nodes} | "
        f"{best} | {worst} | {snapshot.average_depth:.2f} | {snapshot.max_depth} | {notes} |"
    )


@dataclass
class FrontierRecorder:
    """Accumulates frontier snapshots and writes Markdown reports."""

    report_path: Path
    snapshots: List[FrontierSnapshot] = field(default_factory=list)

    def record(self, snapshot: FrontierSnapshot) -> None:
        self.snapshots.append(snapshot)

    def extend(self, snapshots: Iterable[FrontierSnapshot]) -> None:
        self.snapshots.extend(snapshots)

    def clear(self) -> None:
        self.snapshots.clear()

    def flush(self, *, append: bool = False) -> Optional[Path]:
        if not self.snapshots:
            return None
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        write_header = True
        if append and self.report_path.exists():
            write_header = self.report_path.stat().st_size == 0
        elif not append:
            write_header = True
        with self.report_path.open(mode, encoding="utf-8") as handle:
            if write_header:
                handle.write("# Symbolic Frontier Snapshot\n")
                handle.write("| Timestamp | Strategy | Total | Pending | Expanded | Pruned | Best | Worst | AvgDepth | MaxDepth | Notes |\n")
                handle.write("|-----------|----------|-------|---------|----------|--------|------|-------|----------|----------|-------|\n")
            for snapshot in self.snapshots:
                handle.write(_format_snapshot(snapshot) + "\n")
        return self.report_path


__all__ = ["FrontierRecorder"]
