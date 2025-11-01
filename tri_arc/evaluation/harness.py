from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from tri_arc.data import ARCAGI2Dataset, ARCTask
from tri_arc.data.loader import seed_everything

Grid = List[List[int]]


@dataclass(slots=True)
class EvaluationSettings:
    """Runtime settings for the evaluation harness."""

    split: str
    seed: int
    shuffle: bool = False
    limit: Optional[int] = None
    smoke_sample: int = 10
    metrics_path: Path = Path("metrics.jsonl")
    pass2_path: Path = Path("outputs/pass2.json")
    summary_path: Path = Path("reports/eval_summary.md")


@dataclass(slots=True)
class CandidateSet:
    """Collection of predicted outputs for every test example in a task."""

    rank: int
    outputs: Sequence[Grid]
    solver: str
    info: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TaskOutcome:
    """Per-task evaluation statistics."""

    task_id: str
    split: str
    candidates: Sequence[CandidateSet]
    pass_at_1: bool
    pass_at_2: bool
    latency_s: float


@dataclass(slots=True)
class EvaluationResult:
    """Aggregate metrics emitted after an evaluation run."""

    split: str
    total_tasks: int
    total_examples: int
    pass_at_1: int
    pass_at_2: int
    duration_s: float
    seed: int
    outcomes: Sequence[TaskOutcome]

    @property
    def pass_at_1_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.pass_at_1 / self.total_tasks

    @property
    def pass_at_2_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.pass_at_2 / self.total_tasks


class EvaluationHarness:
    """Lightweight evaluation harness used during Stage 3."""

    def __init__(self, dataset: ARCAGI2Dataset, settings: EvaluationSettings) -> None:
        self.dataset = dataset
        self.settings = settings

    def run(self) -> EvaluationResult:
        seed_everything(self.settings.seed)
        start_time = time.perf_counter()

        outcomes: List[TaskOutcome] = []
        pass1 = 0
        pass2 = 0
        total_examples = 0

        iterator = self.dataset.iter_split(
            self.settings.split,
            shuffle=self.settings.shuffle,
            seed=self.settings.seed,
            limit=self.settings.limit,
            smoke_sample=self.settings.smoke_sample,
        )

        for task in iterator:
            outcome = self._evaluate_task(task)
            outcomes.append(outcome)
            total_examples += task.metadata.test_examples
            if outcome.pass_at_1:
                pass1 += 1
            if outcome.pass_at_2:
                pass2 += 1

        duration = time.perf_counter() - start_time
        result = EvaluationResult(
            split=self.settings.split,
            total_tasks=len(outcomes),
            total_examples=total_examples,
            pass_at_1=pass1,
            pass_at_2=pass2,
            duration_s=duration,
            seed=self.settings.seed,
            outcomes=tuple(outcomes),
        )

        self._emit_pass2_file(result)
        self._emit_metrics_log(result)
        self._emit_summary_report(result)

        return result

    def _evaluate_task(self, task: ARCTask) -> TaskOutcome:
        solve_start = time.perf_counter()
        prediction_sets = _baseline_solver(task)
        latency = time.perf_counter() - solve_start

        candidates: List[CandidateSet] = []
        solved_first = False
        solved_any = False

        for idx, outputs in enumerate(prediction_sets[:2]):
            rank = idx + 1
            solved = _is_correct(outputs, task)
            if rank == 1 and solved:
                solved_first = True
            if solved:
                solved_any = True
            candidates.append(
                CandidateSet(
                    rank=rank,
                    outputs=tuple(_clone_grid(grid) for grid in outputs),
                    solver="baseline_echo",
                    info={"solved": str(solved)},
                )
            )

        return TaskOutcome(
            task_id=task.task_id,
            split=task.split,
            candidates=tuple(candidates),
            pass_at_1=solved_first,
            pass_at_2=solved_first or solved_any,
            latency_s=latency,
        )

    def _emit_pass2_file(self, result: EvaluationResult) -> None:
        payload: Dict[str, List[Dict[str, object]]] = {}
        for outcome in result.outcomes:
            task_entries: List[Dict[str, object]] = []
            for candidate in outcome.candidates:
                task_entries.append(
                    {
                        "rank": candidate.rank,
                        "solver": candidate.solver,
                        "outputs": candidate.outputs,
                        "info": candidate.info,
                    }
                )
            payload[outcome.task_id] = task_entries

        path = self.settings.pass2_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _emit_metrics_log(self, result: EvaluationResult) -> None:
        path = self.settings.metrics_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for outcome in result.outcomes:
                record = {
                    "task_id": outcome.task_id,
                    "split": outcome.split,
                    "pass_at_1": outcome.pass_at_1,
                    "pass_at_2": outcome.pass_at_2,
                    "latency_s": round(outcome.latency_s, 6),
                }
                handle.write(json.dumps(record) + "\n")

    def _emit_summary_report(self, result: EvaluationResult) -> None:
        rate1 = result.pass_at_1_rate * 100
        rate2 = result.pass_at_2_rate * 100
        lines = [
            f"# Tri-ARC Evaluation Summary ({result.split})",
            "",
            f"- Tasks evaluated: {result.total_tasks}",
            f"- Test examples: {result.total_examples}",
            f"- pass@1: {result.pass_at_1} ({rate1:.2f}%)",
            f"- pass@2: {result.pass_at_2} ({rate2:.2f}%)",
            f"- Total duration: {result.duration_s:.2f} s",
            f"- Seed: {result.seed}",
            "",
            "## Recent Tasks",
        ]

        tail = result.outcomes[-10:]
        for outcome in tail:
            lines.append(f"- {outcome.task_id}: pass@1={outcome.pass_at_1} pass@2={outcome.pass_at_2} latency={outcome.latency_s:.3f}s")

        path = self.settings.summary_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _baseline_solver(task: ARCTask) -> List[List[Grid]]:
    """
    Deterministic placeholder solver mirroring inputs.

    Returns up to two candidate sets to satisfy pass@2 emission requirements.
    """
    echo_candidate: List[Grid] = []
    zero_candidate: List[Grid] = []

    for example in task.test:
        echo_candidate.append(_clone_grid(example.input))
        zero_candidate.append(_filled_grid(example.input, fill_value=0))

    return [echo_candidate, zero_candidate]


def _is_correct(candidate_outputs: Sequence[Grid], task: ARCTask) -> bool:
    if len(candidate_outputs) != len(task.test):
        return False
    for predicted, target in zip(candidate_outputs, task.test):
        if not _grids_equal(predicted, target.output):
            return False
    return True


def _grids_equal(lhs: Grid, rhs: Grid) -> bool:
    if len(lhs) != len(rhs):
        return False
    for row_a, row_b in zip(lhs, rhs):
        if row_a != row_b:
            return False
    return True


def _clone_grid(grid: Grid) -> Grid:
    return [list(row) for row in grid]


def _filled_grid(reference: Grid, fill_value: int) -> Grid:
    return [[fill_value for _ in row] for row in reference]
