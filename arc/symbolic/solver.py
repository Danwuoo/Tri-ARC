from __future__ import annotations

import hashlib
import json
import logging
import random
import time
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from arc.config import load_config
from arc.logging_utils import append_metric
from arc.symbolic.dsl.interpreter import DSLInterpreter, validate_program
from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.search import (
    BeamSearchStrategy,
    CandidateProgram,
    FrontierRecorder,
    SearchBudget,
    SearchNode,
    SearchStrategy,
    SearchTraceEvent,
    TrainingExample,
)
from arc.symbolic.search.generator import EnumeratorContext, NullEnumerator, ProgramEnumerator
from arc.symbolic.heuristics import HeuristicContext, HeuristicScorer, build_heuristic_from_config
from arc.symbolic.egraph.engine import EGraph
from arc.symbolic.egraph.rules import builtin_rules

LOGGER = logging.getLogger("arc.symbolic.solver")


@dataclass
class SolverTelemetry:
    frontier_report: Optional[Path]
    frontier_log: Optional[Path]
    diagnostics: List[Path]
    events: List[SearchTraceEvent]
    progress_path: Optional[Path]
    checkpoint_path: Optional[Path]
    elapsed_s: float
    expansions: int
    generated_nodes: int


@dataclass
class SolverResult:
    task_id: str
    status: str
    candidates: List[CandidateProgram]
    telemetry: SolverTelemetry
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SolverControl:
    """Best-effort cooperative control shared with the scheduler."""

    signal_path: Optional[Path]
    throttle_s: float = 0.5
    _direct_action: Optional[str] = field(default=None, init=False, repr=False)
    _last_poll: float = field(default=0.0, init=False, repr=False)
    _last_seen: Optional[str] = field(default=None, init=False, repr=False)

    @classmethod
    def from_task(cls, payload: Optional[Dict[str, Any]]) -> "SolverControl":
        if not payload:
            return cls(signal_path=None)
        signal_path = payload.get("signal_path")
        path = Path(signal_path) if signal_path else None
        throttle = float(payload.get("poll_interval_s", 0.5))
        control = cls(signal_path=path, throttle_s=max(0.1, throttle))
        action = payload.get("action")
        if isinstance(action, str) and action.lower() in {"pause", "cancel"}:
            control._direct_action = action.lower()
        return control

    def poll(self) -> Optional[str]:
        if self._direct_action:
            action = self._direct_action
            self._direct_action = None
            self._last_seen = action
            return action
        if not self.signal_path:
            return None
        now = time.perf_counter()
        if now - self._last_poll < self.throttle_s:
            return None
        self._last_poll = now
        if not self.signal_path.exists():
            return None
        try:
            payload = json.loads(self.signal_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Failed to read control signal %s: %s", self.signal_path, exc)
            return None
        action = str(payload.get("action", "")).lower()
        if action not in {"pause", "cancel"}:
            return None
        if action == self._last_seen:
            return None
        self._last_seen = action
        return action


class SymbolicSolver:
    """Coordinates symbolic search, heuristic guidance, and verification."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        interpreter: Optional[DSLInterpreter] = None,
        enumerator: Optional[ProgramEnumerator] = None,
        heuristic: Optional[HeuristicScorer] = None,
    ) -> None:
        raw_config = config or load_config()
        self.config = raw_config
        self.symbolic_cfg = raw_config.get("symbolic", {})
        self.global_cfg = raw_config.get("global", {})
        self.interpreter = interpreter or DSLInterpreter(config=raw_config)

        device_map = self.global_cfg.get("device_map", {})
        self.device = self.symbolic_cfg.get("device", device_map.get("symbolic", "cuda:0"))

        self.enumerator = enumerator or NullEnumerator()
        self.heuristic = heuristic or build_heuristic_from_config(raw_config, device=self.device)

        self.frontier_log_path = Path(self.symbolic_cfg.get("frontier", {}).get("log_path", "logs/symbolic/symbolic_frontier.log"))
        self.frontier_log_path.parent.mkdir(parents=True, exist_ok=True)

        self.progress_path = Path(self.symbolic_cfg.get("telemetry", {}).get("progress_file", "solve_progress.jsonl"))
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)

        diagnostics_dir = self.symbolic_cfg.get("telemetry", {}).get("diagnostics_dir", "logs/symbolic/diagnostics")
        self.diagnostics_dir = Path(diagnostics_dir)
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_dir = self.symbolic_cfg.get("telemetry", {}).get("checkpoint_dir", "cache/symbolic/checkpoints")
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        control_dir = self.symbolic_cfg.get("telemetry", {}).get("control_dir")
        if control_dir:
            self.control_dir = Path(control_dir)
        else:
            self.control_dir = self.checkpoint_dir
        self.control_dir.mkdir(parents=True, exist_ok=True)

        self.reports_dir = Path(self.symbolic_cfg.get("frontier", {}).get("report_dir", "reports/symbolic"))
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.egraph_enabled = self.symbolic_cfg.get("egraph", {}).get("enabled", True)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def solve(self, task: Dict[str, Any]) -> SolverResult:
        task_id = str(task.get("task_id", "unknown_task"))
        control = SolverControl.from_task(task.get("control"))
        if control.signal_path and not control.signal_path.is_absolute():
            control.signal_path = (self.control_dir / control.signal_path).resolve()

        train_examples = task.get("train_examples") or task.get("examples") or []
        examples = self._build_examples(train_examples)
        metadata = task.get("metadata", {})

        resume_path = self._resolve_resume_checkpoint(task, task_id)
        resume_payload: Optional[Dict[str, Any]] = None
        if resume_path and resume_path.exists():
            try:
                candidate_payload = self._load_checkpoint(resume_path)
                if candidate_payload.get("task_id") != task_id:
                    LOGGER.warning(
                        "Checkpoint %s belongs to task %s; expected %s. Ignoring resume request.",
                        resume_path,
                        candidate_payload.get("task_id"),
                        task_id,
                    )
                else:
                    resume_payload = candidate_payload
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Failed to load checkpoint %s for task %s: %s", resume_path, task_id, exc)

        budget = self._build_budget(task_id)
        strategy = self._build_strategy(budget)
        if resume_payload:
            strategy_state = resume_payload.get("strategy", {})
            if strategy_state.get("name") != strategy.name:
                LOGGER.warning(
                    "Checkpoint %s strategy %s mismatches current strategy %s; starting fresh search for %s.",
                    resume_path,
                    strategy_state.get("name"),
                    strategy.name,
                    task_id,
                )
                resume_payload = None

        base_seed = self._derive_seed(task_id)
        rng = random.Random(base_seed)
        if resume_payload and "context_rng_state" in resume_payload:
            try:
                rng.setstate(resume_payload["context_rng_state"])
            except Exception as exc:  # pragma: no cover - best effort
                LOGGER.debug("Unable to restore RNG state for %s: %s", task_id, exc)

        root_node = SearchNode(
            node_id=0,
            stages=tuple(),
            depth=0,
            score=0.0,
            cost=0.0,
            metadata={"coverage": 0.0, "consistency": 0.0, "progress": 0.0, "novelty": 0.0},
        )

        events: List[SearchTraceEvent] = list(resume_payload.get("events", [])) if resume_payload else []
        candidates: List[CandidateProgram] = list(resume_payload.get("candidates", [])) if resume_payload else []
        diagnostics: List[Path] = list(resume_payload.get("diagnostics", [])) if resume_payload else []

        trace_log_handle = self.frontier_log_path.open("a", encoding="utf-8")
        if resume_payload:
            self._log_event(
                trace_log_handle,
                events,
                event_type="resume_start",
                payload={
                    "task_id": task_id,
                    "reason": resume_payload.get("reason", "resume"),
                    "checkpoint": str(resume_path) if resume_path else None,
                },
                task_id=task_id,
            )

        if resume_payload and resume_payload.get("frontier_report"):
            frontier_report_path = Path(resume_payload["frontier_report"])
        else:
            frontier_report_path = self.reports_dir / f"frontier_{task_id}_{time.strftime('%Y%m%d_%H%M%S')}.md"
        frontier_report_path.parent.mkdir(parents=True, exist_ok=True)
        frontier_recorder = FrontierRecorder(frontier_report_path)
        if resume_payload:
            frontier_recorder.extend(resume_payload.get("frontier_snapshots", []))

        context = EnumeratorContext(
            task_id=task_id,
            examples=examples,
            rng=rng,
            max_depth=budget.max_depth,
            metadata=dict(metadata),
        )
        self.enumerator.initialise(context)

        heuristic_context = HeuristicContext(
            task_id=task_id,
            examples=examples,
            metadata=dict(metadata),
            max_depth=budget.max_depth,
            device=self.device,
            seed=base_seed,
        )
        self.heuristic.initialise(heuristic_context)

        egraph = self._build_egraph()
        if egraph is not None:
            for rule in builtin_rules():
                egraph.add_rule(rule)

        node_counter = int(resume_payload.get("node_counter", 0)) if resume_payload else 0

        snapshot_interval_s = float(self.symbolic_cfg.get("frontier", {}).get("snapshot_interval_s", 5.0))
        if resume_payload:
            budget.restore_state(resume_payload.get("budget", {}))
            strategy.restore_state(resume_payload.get("strategy", {}))
            elapsed_offset = float(resume_payload.get("elapsed_s", 0.0))
            start_time = time.perf_counter() - elapsed_offset
            next_snapshot = float(resume_payload.get("next_snapshot", snapshot_interval_s))
        else:
            strategy.initialise(root_node)
            budget.register_node()
            start_time = time.perf_counter()
            next_snapshot = snapshot_interval_s

        pause_requested = False
        cancel_requested = False
        terminate = False

        while strategy and budget.allow_expansion():
            action = control.poll()
            if action == "pause":
                pause_requested = True
                LOGGER.info("Pause signal received for task %s.", task_id)
                break
            if action == "cancel":
                cancel_requested = True
                LOGGER.info("Cancel signal received for task %s.", task_id)
                break

            if not budget.within_time(soft=False):
                LOGGER.info("Task %s exceeded hard timeout.", task_id)
                break

            node = strategy.pop()
            if node is None:
                break
            budget.register_expansion()
            node_score = self.heuristic.score(node)
            node.score = node_score.score
            node.metadata.update(node_score.reasoning)

            self._log_event(
                trace_log_handle,
                events,
                event_type="expand_node",
                payload={
                    "node_id": node.node_id,
                    "depth": node.depth,
                    "score": node.score,
                    "cost": node.cost,
                    "metadata": node.metadata,
                },
                task_id=task_id,
            )

            if node.depth > 0:
                candidate = self._attempt_verification(node, examples, task_id, diagnostics)
                if candidate is not None:
                    candidates.append(candidate)
                    if egraph is not None:
                        egraph.add_program(candidate.program)
                    self._log_event(
                        trace_log_handle,
                        events,
                        event_type="candidate_evaluated",
                        payload=self._candidate_payload(candidate),
                        task_id=task_id,
                    )
                    if self._should_terminate(candidates):
                        terminate = True
            if terminate:
                strategy.mark_expanded(node)
                LOGGER.info("Task %s reached success threshold; stopping search.", task_id)
                break

            expansion_terminated = False
            for expansion in self.enumerator.expand(node, context):
                if node.depth + 1 > budget.max_depth:
                    self._log_event(
                        trace_log_handle,
                        events,
                        event_type="prune_expansion",
                        payload={
                            "node_id": node.node_id,
                            "reason": "max_depth",
                            "candidate_operator": expansion.stage.operator,
                        },
                        task_id=task_id,
                    )
                    continue

                next_id = node_counter + 1
                node_counter = next_id
                new_node = node.with_stage(
                    expansion.stage,
                    node_id=next_id,
                    score=node.score,
                    cost=node.cost + expansion.incremental_cost,
                )
                new_node.metadata.update(expansion.metadata)

                if not budget.register_node():
                    self._log_event(
                        trace_log_handle,
                        events,
                        event_type="prune_expansion",
                        payload={
                            "node_id": new_node.node_id,
                            "reason": "node_limit",
                            "candidate_operator": expansion.stage.operator,
                        },
                        task_id=task_id,
                    )
                    continue

                score_result = self.heuristic.score(new_node)
                new_node.score = score_result.score
                new_node.metadata.update(score_result.reasoning)

                if expansion.is_solution:
                    candidate = self._attempt_verification(new_node, examples, task_id, diagnostics)
                    if candidate is not None:
                        candidate.metadata.setdefault("solution_reason", expansion.reason)
                        candidates.append(candidate)
                        if egraph is not None:
                            egraph.add_program(candidate.program)
                        self._log_event(
                            trace_log_handle,
                            events,
                            event_type="candidate_evaluated",
                            payload=self._candidate_payload(candidate),
                            task_id=task_id,
                        )
                        if self._should_terminate(candidates):
                            expansion_terminated = True
                            LOGGER.info("Task %s reached success threshold from expansion; stopping.", task_id)
                            break
                else:
                    strategy.push(new_node)
            strategy.mark_expanded(node)
            if terminate or expansion_terminated:
                break

            elapsed = time.perf_counter() - start_time
            if elapsed >= next_snapshot:
                snapshot = strategy.frontier_snapshot(notes={"task": task_id})
                frontier_recorder.record(snapshot)
                self._log_event(
                    trace_log_handle,
                    events,
                    event_type="frontier_snapshot",
                    payload=snapshot.__dict__,
                    task_id=task_id,
                )
                next_snapshot += snapshot_interval_s

        elapsed_s = time.perf_counter() - start_time

        checkpoint_path: Optional[Path] = None
        control_reason: Optional[str] = None
        egraph_payload: Optional[Dict[str, Any]] = None

        if pause_requested or cancel_requested:
            control_reason = "pause" if pause_requested else "cancel"
            try:
                snapshot = strategy.frontier_snapshot(notes={"task": task_id, "phase": control_reason})
                frontier_recorder.record(snapshot)
                self._log_event(
                    trace_log_handle,
                    events,
                    event_type="frontier_snapshot",
                    payload=snapshot.__dict__,
                    task_id=task_id,
                )
            except Exception:  # pragma: no cover - best effort
                LOGGER.debug("Frontier snapshot unavailable during %s for task %s", control_reason, task_id)

            checkpoint_payload = {
                "version": 1,
                "task_id": task_id,
                "created_at": time.time(),
                "reason": control_reason,
                "node_counter": node_counter,
                "budget": budget.export_state(),
                "strategy": strategy.export_state(),
                "candidates": candidates,
                "diagnostics": diagnostics,
                "events": events,
                "frontier_snapshots": frontier_recorder.snapshots,
                "frontier_report": str(frontier_report_path),
                "context_rng_state": rng.getstate(),
                "elapsed_s": elapsed_s,
                "next_snapshot": next_snapshot,
            }
            checkpoint_path = self._save_checkpoint(task_id, checkpoint_payload)
            self._log_event(
                trace_log_handle,
                events,
                event_type="checkpoint_created",
                payload={"task_id": task_id, "checkpoint": str(checkpoint_path), "reason": control_reason},
                task_id=task_id,
            )
        else:
            if egraph is not None and candidates:
                egraph_payload = self._run_egraph(egraph, candidates, task_id)

            if not frontier_recorder.snapshots:
                try:
                    snapshot = strategy.frontier_snapshot(notes={"task": task_id, "phase": "final"})
                    frontier_recorder.record(snapshot)
                    self._log_event(
                        trace_log_handle,
                        events,
                        event_type="frontier_snapshot",
                        payload=snapshot.__dict__,
                        task_id=task_id,
                    )
                except Exception:  # pragma: no cover - strategies may not support snapshots after completion
                    LOGGER.debug("Frontier snapshot unavailable for task %s", task_id)

            final_payload: Dict[str, Any] = {
                "task_id": task_id,
                "elapsed_s": elapsed_s,
                "expansions": budget.expansions,
                "generated_nodes": budget.generated_nodes,
                "candidate_count": len(candidates),
            }
            if egraph_payload is not None:
                final_payload["egraph"] = egraph_payload
            self._log_event(
                trace_log_handle,
                events,
                event_type="search_complete",
                payload=final_payload,
                task_id=task_id,
            )

        trace_log_handle.close()

        frontier_report = frontier_recorder.flush(append=bool(resume_payload))

        self.enumerator.shutdown()
        self.heuristic.shutdown()

        if pause_requested or cancel_requested:
            progress_status = "paused" if pause_requested else "cancelled"
            summary_status = "partial"
        else:
            progress_status = "success" if candidates else "no_solution"
            summary_status = progress_status

        progress_path = self._write_progress(
            task_id=task_id,
            status=progress_status,
            elapsed_s=elapsed_s,
            expansions=budget.expansions,
            nodes=budget.generated_nodes,
        )

        telemetry = SolverTelemetry(
            frontier_report=frontier_report,
            frontier_log=self.frontier_log_path,
            diagnostics=diagnostics,
            events=events,
            progress_path=progress_path,
            checkpoint_path=checkpoint_path,
            elapsed_s=elapsed_s,
            expansions=budget.expansions,
            generated_nodes=budget.generated_nodes,
        )

        summary: Dict[str, Any] = {
            "task_id": task_id,
            "status": summary_status,
            "elapsed_s": elapsed_s,
            "expansions": budget.expansions,
            "nodes": budget.generated_nodes,
            "solutions": len([c for c in candidates if c.verification_passed]),
        }
        if egraph_payload is not None:
            summary["egraph"] = egraph_payload
        if checkpoint_path:
            summary["checkpoint_path"] = str(checkpoint_path)
        if control_reason:
            summary["control_reason"] = control_reason

        self._emit_metric(summary)

        return SolverResult(
            task_id=task_id,
            status=summary["status"],
            candidates=candidates,
            telemetry=telemetry,
            summary=summary,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _build_examples(self, raw_examples: Sequence[Dict[str, Any]]) -> List[TrainingExample]:
        examples: List[TrainingExample] = []
        for index, example in enumerate(raw_examples):
            input_grid = example.get("input") or example.get("input_grid")
            output_grid = example.get("output") or example.get("output_grid")
            metadata = dict(example.get("metadata", {}))
            metadata.setdefault("index", index)
            examples.append(TrainingExample(input_grid=input_grid, output_grid=output_grid, metadata=metadata))
        return examples

    def _build_budget(self, task_id: str) -> SearchBudget:
        symbolic = self.symbolic_cfg
        soft_timeout = float(symbolic.get("soft_timeout_s", 90.0))
        hard_timeout = float(symbolic.get("hard_timeout_s", 150.0))
        max_depth = int(symbolic.get("max_depth", 12))
        max_expansions = int(symbolic.get("max_expansions", 5000))
        max_nodes = symbolic.get("max_nodes")
        if max_nodes is not None:
            max_nodes = int(max_nodes)
        beam_width = symbolic.get("beam_width")
        if beam_width is not None:
            beam_width = int(beam_width)
        return SearchBudget(
            max_depth=max_depth,
            max_expansions=max_expansions,
            soft_timeout_s=soft_timeout,
            hard_timeout_s=hard_timeout,
            max_nodes=max_nodes,
            beam_width=beam_width,
            seed=self._derive_seed(task_id),
        )

    def _build_strategy(self, budget: SearchBudget) -> SearchStrategy:
        strategy_name = self.symbolic_cfg.get("search_strategy", "beam").lower()
        if strategy_name == "dfs":
            from arc.symbolic.search.enumerators import DepthFirstSearchStrategy

            return DepthFirstSearchStrategy(budget)
        if strategy_name in {"iddfs", "iterative_deepening"}:
            from arc.symbolic.search.enumerators import IterativeDeepeningStrategy

            return IterativeDeepeningStrategy(budget)
        return BeamSearchStrategy(budget)

    def _build_egraph(self) -> Optional[EGraph]:
        if not self.egraph_enabled:
            return None
        egraph_cfg = self.symbolic_cfg.get("egraph", {})
        rewrite_limit = int(egraph_cfg.get("rewrite_limit", 5000))
        cost_metric = egraph_cfg.get("cost_metric", "min_nodes")
        history_dir = Path(egraph_cfg.get("history_dir", "logs/symbolic/egraph"))
        history_dir.mkdir(parents=True, exist_ok=True)

        def cost_fn(program: Program) -> float:
            if cost_metric == "min_nodes":
                return float(len(program.stages))
            if cost_metric == "depth":
                return float(len(program.stages))
            return float(len(program.stages))

        egraph = EGraph(cost_fn=cost_fn, rewrite_limit=rewrite_limit, history_dir=history_dir)
        return egraph

    def _run_egraph(self, egraph: EGraph, candidates: Sequence[CandidateProgram], task_id: str) -> Dict[str, Any]:
        iterations = int(self.symbolic_cfg.get("egraph", {}).get("max_iterations", 50))
        for candidate in candidates:
            egraph.add_program(candidate.program)
        stats = egraph.saturate(max_iterations=iterations)
        best = egraph.extract_best()
        payload: Dict[str, Any] = {
            "task_id": task_id,
            "iterations": stats.iterations,
            "rewrites": stats.rewrites_applied,
            "unique_programs": stats.unique_programs,
            "best_cost": stats.best_cost,
            "history_path": str(stats.history_path) if stats.history_path else None,
            "best_program": [(stage.operator, stage.arguments) for stage in best.program.stages] if best else None,
        }
        append_metric(self.progress_path, {"event": "egraph_saturation", **payload})
        return payload

    def _attempt_verification(
        self,
        node: SearchNode,
        examples: Sequence[TrainingExample],
        task_id: str,
        diagnostics: List[Path],
    ) -> Optional[CandidateProgram]:
        issues = validate_program(node.program)
        if issues:
            return None
        solved, total, failures, diag_path = self._verify_program(node.program, examples, task_id)
        if total == 0:
            return None

        if diag_path:
            diagnostics.append(diag_path)

        candidate = CandidateProgram(
            node_id=node.node_id,
            program=node.program,
            score=node.score,
            cost=node.cost,
            solved_examples=solved,
            total_examples=total,
            verification_passed=solved == total and total > 0,
            metadata={}
        )
        if failures:
            candidate.metadata["failures"] = failures
        return candidate

    def _verify_program(
        self,
        program: Program,
        examples: Sequence[TrainingExample],
        task_id: str,
    ) -> Tuple[int, int, List[Dict[str, Any]], Optional[Path]]:
        failures: List[Dict[str, Any]] = []
        solved = 0
        diag_entries: List[Dict[str, Any]] = []
        for example in examples:
            index = example.metadata.get("index", 0)
            try:
                trace = self.interpreter.run(program, example.input_grid, metadata={"task_id": task_id, "example_index": index})
                output = trace.final_grid.to_list()
                if output == example.output_grid:
                    solved += 1
                else:
                    diff = self._diff(example.output_grid, output)
                    entry = {
                        "index": index,
                        "type": "grid_mismatch",
                        "expected": example.output_grid,
                        "actual": output,
                        "diff": diff,
                    }
                    failures.append(entry)
                    diag_entries.append(entry)
            except Exception as exc:  # pragma: no cover - defensive guard
                entry = {
                    "index": index,
                    "type": "exception",
                    "message": repr(exc),
                }
                failures.append(entry)
                diag_entries.append(entry)
        diag_path: Optional[Path] = None
        if diag_entries:
            diag_path = self._write_diagnostics(task_id, program, diag_entries)
        return solved, len(examples), failures, diag_path

    def _write_diagnostics(self, task_id: str, program: Program, entries: Sequence[Dict[str, Any]]) -> Path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = self.diagnostics_dir / f"{task_id}_diag_{timestamp}.json"
        payload = {
            "task_id": task_id,
            "program": [(stage.operator, stage.arguments) for stage in program],
            "failures": entries,
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return path

    def _log_event(
        self,
        handle,
        events: List[SearchTraceEvent],
        *,
        event_type: str,
        payload: Dict[str, Any],
        task_id: Optional[str] = None,
    ) -> None:
        timestamp = time.time()
        payload_with_task = dict(payload)
        if task_id is not None:
            payload_with_task.setdefault("task_id", task_id)
        record = {
            "event": event_type,
            "timestamp": timestamp,
            "task_id": task_id,
            "payload": payload_with_task,
        }
        handle.write(json.dumps(record) + "\n")
        events.append(SearchTraceEvent(timestamp=timestamp, event_type=event_type, payload=payload_with_task))

    def _diff(self, expected: Sequence[Sequence[int]], actual: Sequence[Sequence[int]]) -> Dict[str, Any]:
        try:
            rows = len(expected)
            cols = len(expected[0]) if rows else 0
        except Exception:  # pragma: no cover - defensive guard
            return {"message": "Diff unavailable."}
        for r in range(rows):
            for c in range(cols):
                if expected[r][c] != actual[r][c]:
                    return {"first_mismatch": {"row": r, "col": c, "expected": expected[r][c], "actual": actual[r][c]}}
        return {"message": "Mismatch but diff unavailable."}

    def _should_terminate(self, candidates: Sequence[CandidateProgram]) -> bool:
        successes = [candidate for candidate in candidates if candidate.verification_passed]
        return len(successes) > 0

    def _write_progress(
        self,
        *,
        task_id: str,
        status: str,
        elapsed_s: float,
        expansions: int,
        nodes: int,
    ) -> Path:
        payload = {
            "task_id": task_id,
            "status": status,
            "elapsed_s": elapsed_s,
            "expansions": expansions,
            "nodes": nodes,
            "timestamp": time.time(),
        }
        append_metric(self.progress_path, payload)
        return self.progress_path

    def _emit_metric(self, payload: Dict[str, Any]) -> None:
        metrics_file = Path(self.global_cfg.get("log_root", "logs")) / "metrics.jsonl"
        append_metric(metrics_file, {"module": "symbolic_solver", **payload})

    def _checkpoint_path(self, task_id: str) -> Path:
        return self.checkpoint_dir / f"{task_id}.ckpt"

    def _save_checkpoint(self, task_id: str, payload: Dict[str, Any]) -> Path:
        path = self._checkpoint_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(payload, handle)
        return path

    def _load_checkpoint(self, path: Path) -> Dict[str, Any]:
        with path.open("rb") as handle:
            return pickle.load(handle)

    def _resolve_resume_checkpoint(self, task: Dict[str, Any], task_id: str) -> Optional[Path]:
        if "resume_checkpoint" in task:
            return Path(task["resume_checkpoint"])
        resume_flag = task.get("resume")
        if isinstance(resume_flag, str):
            if resume_flag.lower() == "auto":
                candidate = self._checkpoint_path(task_id)
                return candidate if candidate.exists() else None
            if resume_flag.lower() in {"true", "yes"}:
                resume_flag = True
        if resume_flag:
            return self._checkpoint_path(task_id)
        return None

    def _derive_seed(self, task_id: str) -> int:
        base_seed = int(self.symbolic_cfg.get("seed", self.global_cfg.get("seed", 1337)))
        digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
        task_seed = int(digest[:8], 16)
        return (base_seed ^ task_seed) & 0xFFFFFFFF

    def _candidate_payload(self, candidate: CandidateProgram) -> Dict[str, Any]:
        return {
            "node_id": candidate.node_id,
            "score": candidate.score,
            "cost": candidate.cost,
            "solved_examples": candidate.solved_examples,
            "total_examples": candidate.total_examples,
            "verification_passed": candidate.verification_passed,
            "metadata": candidate.metadata,
            "program": [(stage.operator, stage.arguments) for stage in candidate.program],
        }


__all__ = ["SymbolicSolver", "SolverResult", "SolverTelemetry"]
