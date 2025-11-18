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
from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.ir import GridToObjectGraphMapper, ObjectGraphToDSLMapper
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
from arc.symbolic.heuristics import HeuristicContext, HeuristicResult, HeuristicScorer, build_heuristic_from_config
from arc.symbolic.egraph.engine import EGraph
from arc.symbolic.egraph.rules import builtin_rules
from arc.symbolic.verification import (
    CEGISCoordinator,
    CounterexampleMinimizer,
    InvariantChecker,
    ConstraintBasedRepairer,
    MultiSolutionArbitrator,
)
from arc.symbolic.verification.cegis import Example as CEGISExample

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


class TaskValidationError(Exception):
    """Raised when task examples fail structural validation."""

    def __init__(self, message: str, *, diagnostics: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__(message)
        self.diagnostics: List[Dict[str, Any]] = list(diagnostics or [])


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

        # Provide a configurable floor for beam search when width is omitted.
        beam_width_floor = next(
            (
                candidate
                for candidate in (
                    self.symbolic_cfg.get("beam_width_minimum"),
                    self.symbolic_cfg.get("min_beam_width"),
                    self.symbolic_cfg.get("default_beam_width"),
                )
                if candidate is not None
            ),
            16,
        )
        try:
            self._beam_width_minimum = max(1, int(beam_width_floor))
        except (TypeError, ValueError):
            self._beam_width_minimum = 16
            LOGGER.warning(
                "Invalid symbolic.beam_width_minimum=%r; falling back to %d",
                beam_width_floor,
                self._beam_width_minimum,
            )

        device_map = self.global_cfg.get("device_map", {})
        self.device = self.symbolic_cfg.get("device", device_map.get("symbolic", "cpu"))

        self.enumerator = enumerator or NullEnumerator()

        smt_cfg = raw_config.get("smt", {}) or {}
        symbolic_smt_cfg = self.symbolic_cfg.get("smt", {}) or {}
        token_prefix = symbolic_smt_cfg.get("token_prefix") or smt_cfg.get("token_prefix") or "smt:virtual-symbolic:"
        virtual_secret = symbolic_smt_cfg.get("virtual_secret") or smt_cfg.get("virtual_secret") or str(self.global_cfg.get("seed", "tri-arc"))
        self._smt_issue_tokens = bool(symbolic_smt_cfg.get("issue_tokens", True))
        self._smt_token_prefix = str(token_prefix)
        self._smt_virtual_secret = str(virtual_secret)
        self._smt_token_counter = 0
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
        
        # Initialize IR layer mappers
        ir_cfg = self.symbolic_cfg.get("ir", {})
        self.ir_enabled = bool(ir_cfg.get("enabled", False))
        if self.ir_enabled:
            self.grid_mapper = GridToObjectGraphMapper()
            self.dsl_mapper = ObjectGraphToDSLMapper()
        else:
            self.grid_mapper = None
            self.dsl_mapper = None
        
        # Initialize SMT gateway
        smt_gateway_cfg = self.symbolic_cfg.get("smt", {})
        self.smt_enabled = bool(smt_gateway_cfg.get("enabled", False))
        if self.smt_enabled:
            try:
                from arc.symbolic.smt import BatchVerifier, WitnessFunctionGenerator
                self.smt_verifier = BatchVerifier(smt_gateway_cfg)
                self.witness_generator = WitnessFunctionGenerator(smt_gateway_cfg)
                LOGGER.info("SMT gateway initialized successfully")
            except ImportError as e:
                LOGGER.warning("SMT gateway requested but z3-solver not available: %s", e)
                self.smt_enabled = False
                self.smt_verifier = None
                self.witness_generator = None
        else:
            self.smt_verifier = None
            self.witness_generator = None
        
        # Initialize symmetry components
        symmetry_cfg = self.symbolic_cfg.get("symmetry", {})
        self.symmetry_enabled = bool(symmetry_cfg.get("enabled", False))
        if self.symmetry_enabled:
            from arc.symbolic.symmetry import ColorNormalizer, SymmetryDetector, StepNormalizer
            
            color_strategy = symmetry_cfg.get("color_normalization_strategy", "frequency")
            self.color_normalizer = ColorNormalizer(strategy=color_strategy)
            self.symmetry_detector = SymmetryDetector()
            self.step_normalizer = StepNormalizer()
            
            self.color_normalization_enabled = bool(symmetry_cfg.get("color_normalization", True))
            self.symmetry_detection_enabled = bool(symmetry_cfg.get("symmetry_detection", True))
            self.step_normalization_enabled = bool(symmetry_cfg.get("step_normalization", True))
            
            LOGGER.info("Symmetry components initialized (color_norm=%s, sym_detect=%s, step_norm=%s)",
                       self.color_normalization_enabled,
                       self.symmetry_detection_enabled,
                       self.step_normalization_enabled)
        else:
            self.color_normalizer = None
            self.symmetry_detector = None
            self.step_normalizer = None
            self.color_normalization_enabled = False
            self.symmetry_detection_enabled = False
            self.step_normalization_enabled = False
        
        # Initialize CEGIS and verification components
        cegis_cfg = self.symbolic_cfg.get("cegis", {})
        self.cegis_enabled = bool(cegis_cfg.get("enabled", False))
        if self.cegis_enabled:
            # Create a simple verifier wrapper for CEGIS
            class SimpleVerifier:
                def __init__(self, interpreter):
                    self.interpreter = interpreter
                
                def verify(self, program, input_grid, output_grid):
                    try:
                        from arc.symbolic.dsl.types import Grid
                        if not isinstance(input_grid, Grid):
                            input_grid = Grid.from_list(input_grid)
                        if not isinstance(output_grid, Grid):
                            output_grid = Grid.from_list(output_grid)
                        
                        trace = self.interpreter.run(program, input_grid.to_list())
                        actual = trace.final_grid
                        success = actual.equals(output_grid)
                        return {
                            "success": success,
                            "actual_output": actual,
                        }
                    except Exception as e:
                        return {
                            "success": False,
                            "error": str(e),
                            "actual_output": input_grid,
                        }
                
                def execute(self, program, input_grid):
                    try:
                        from arc.symbolic.dsl.types import Grid
                        if not isinstance(input_grid, Grid):
                            input_grid = Grid.from_list(input_grid)
                        trace = self.interpreter.run(program, input_grid.to_list())
                        return {"output": trace.final_grid}
                    except Exception as e:
                        return {"output": input_grid, "error": str(e)}
            
            verifier = SimpleVerifier(self.interpreter)
            self.cegis_coordinator = CEGISCoordinator(
                raw_config,
                synthesizer=None,  # Will be set during solve
                verifier=verifier,
                minimizer=CounterexampleMinimizer(raw_config, verifier=verifier),
            )
            self.invariant_checker = InvariantChecker(raw_config)
            self.program_repairer = ConstraintBasedRepairer(
                raw_config,
                verifier=verifier,
                synthesizer=None,  # Will be set during solve
            )
            self.solution_arbitrator = MultiSolutionArbitrator(raw_config, verifier=verifier)
        else:
            self.cegis_coordinator = None
            self.invariant_checker = None
            self.program_repairer = None
            self.solution_arbitrator = None
        
        # Initialize decomposition integration
        decomp_cfg = self.symbolic_cfg.get("decomposition", {})
        self.decomposition_enabled = bool(decomp_cfg.get("enabled", False))
        if self.decomposition_enabled:
            from arc.symbolic.decomposition import DecompositionIntegration
            self.decomposition = DecompositionIntegration(raw_config)
            LOGGER.info("Decomposition integration initialized")
        else:
            self.decomposition = None
        
        # Initialize coordination integration (TTT and LLM)
        coord_cfg = self.symbolic_cfg.get("coordination", {})
        self.coordination_enabled = bool(coord_cfg.get("enabled", False))
        if self.coordination_enabled:
            from arc.symbolic.coordination import CoordinationIntegration
            self.coordination = CoordinationIntegration(raw_config)
            LOGGER.info("Coordination integration initialized")
        else:
            self.coordination = None
        
        # Initialize advanced search strategies
        advanced_search_cfg = self.symbolic_cfg.get("advanced_search", {})
        self.advanced_search_enabled = bool(advanced_search_cfg.get("enabled", False))
        if self.advanced_search_enabled:
            from arc.symbolic.search.advanced_search_integration import AdvancedSearchCoordinator
            self.advanced_search = AdvancedSearchCoordinator(advanced_search_cfg)
            LOGGER.info("Advanced search strategies initialized")
        else:
            self.advanced_search = None
        
        # Initialize DSL library management
        library_cfg = self.symbolic_cfg.get("library", {})
        self.library_enabled = bool(library_cfg.get("enabled", False))
        if self.library_enabled:
            from arc.symbolic.library.integration import LibraryManager
            self.library_manager = LibraryManager(raw_config)
            LOGGER.info("DSL library management initialized")
        else:
            self.library_manager = None
        
        # Initialize engineering infrastructure
        engineering_cfg = self.symbolic_cfg.get("engineering", {})
        self.engineering_enabled = bool(engineering_cfg.get("enabled", False))
        if self.engineering_enabled:
            from arc.symbolic.engineering import (
                CacheManager,
                AdaptiveBudgetManager,
                TimeoutGuard,
                TelemetryCollector,
            )
            self.cache_manager = CacheManager(engineering_cfg.get("cache", {}))
            self.adaptive_budget = AdaptiveBudgetManager(engineering_cfg.get("budget", {}))
            self.telemetry_collector = TelemetryCollector(engineering_cfg.get("telemetry", {}))
            LOGGER.info("Engineering infrastructure initialized")
        else:
            self.cache_manager = None
            self.adaptive_budget = None
            self.telemetry_collector = None

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def solve(self, task: Dict[str, Any]) -> SolverResult:
        task_id = str(task.get("task_id", "unknown_task"))
        control = SolverControl.from_task(task.get("control"))
        if control.signal_path and not control.signal_path.is_absolute():
            control.signal_path = (self.control_dir / control.signal_path).resolve()
        solve_start = time.perf_counter()
        telemetry_started = False

        def ensure_telemetry_started() -> None:
            nonlocal telemetry_started
            if telemetry_started:
                return
            if self.telemetry_collector and hasattr(self.telemetry_collector, "start_task"):
                self.telemetry_collector.start_task(task_id)
                telemetry_started = True

        train_examples = task.get("train_examples") or task.get("examples") or []
        metadata = task.get("metadata", {})
        try:
            examples = self._build_examples(train_examples)
        except TaskValidationError as exc:
            ensure_telemetry_started()
            elapsed = time.perf_counter() - solve_start
            LOGGER.error("Task %s failed validation: %s", task_id, exc)
            failure_result = self._build_failed_result(
                task_id=task_id,
                message=str(exc),
                reason="invalid_task",
                diagnostics=exc.diagnostics,
                elapsed_s=elapsed,
            )
            failure_metadata = {
                "elapsed_s": elapsed,
                "reason": "invalid_task",
                "message": str(exc),
                "invalid_examples": [entry.get("index") for entry in exc.diagnostics],
            }
            self._dispatch_failure_feedback(task_id, "invalid_task", failure_metadata)
            return failure_result

        # Receive invariants and sketches from TTT/LLM modules
        invariants = []
        relations = []
        sketches = []
        macros = []
        if self.coordination_enabled and self.coordination:
            invariants = self.coordination.get_invariants(task_id)
            relations = self.coordination.get_relations(task_id)
            sketches = self.coordination.get_sketches(task_id)
            macros = self.coordination.get_macros(task_id)
            
            if invariants:
                LOGGER.info(f"Received {len(invariants)} invariants from TTT for task {task_id}")
                metadata["ttt_invariants"] = len(invariants)
            if relations:
                LOGGER.info(f"Received {len(relations)} relations from TTT for task {task_id}")
                metadata["ttt_relations"] = len(relations)
            if sketches:
                LOGGER.info(f"Received {len(sketches)} sketches from LLM for task {task_id}")
                metadata["llm_sketches"] = len(sketches)
            if macros:
                LOGGER.info(f"Received {len(macros)} macros from LLM for task {task_id}")
                metadata["llm_macros"] = len(macros)

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

        # Use adaptive budget if enabled
        base_budget = self._build_budget(task_id)
        if self.adaptive_budget:
            budget = self.adaptive_budget.allocate_budget(task, base_budget)
            LOGGER.info(
                "Adaptive budget allocated for task %s: depth=%s, expansions=%s",
                task_id,
                budget.max_depth,
                budget.max_expansions,
            )
        else:
            budget = base_budget
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
        
        # Check cache for previously solved programs
        cached_result = None
        if self.cache_manager:
            cached_result = self.cache_manager.get_cached_program(task_id)
            if cached_result:
                LOGGER.info(f"Found cached solution for task {task_id}")
                # Return cached result immediately
                return self._build_cached_result(task_id, cached_result)
        
        # Start telemetry collection
        ensure_telemetry_started()

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
            self._capture_heuristic_metadata(node, node_score)

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
                self._capture_heuristic_metadata(new_node, score_result)

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
        if self.ir_enabled:
            summary["ir_enabled"] = True
        if checkpoint_path:
            summary["checkpoint_path"] = str(checkpoint_path)
        if control_reason:
            summary["control_reason"] = control_reason
        if self.coordination_enabled and self.coordination:
            summary["coordination_stats"] = self.coordination.get_stats()

        # Apply symmetry-based deduplication if enabled
        if self.symmetry_enabled and self.symmetry_detection_enabled and self.symmetry_detector and candidates:
            try:
                # Detect symmetry in the examples
                if examples:
                    from arc.symbolic.dsl.types import Grid
                    # Use first example to detect symmetry
                    first_input = examples[0].input_grid
                    if not isinstance(first_input, Grid):
                        first_input = Grid.from_list(first_input)
                    symmetry_group = self.symmetry_detector.detect_grid_symmetry(first_input)
                    
                    if symmetry_group.order > 1:
                        # Extract programs from candidates
                        programs = [c.program for c in candidates]
                        # Compute quotient representatives
                        representative_programs = self.symmetry_detector.compute_quotient_representatives(
                            programs, symmetry_group
                        )
                        
                        # Filter candidates to keep only representatives
                        representative_set = set(id(p) for p in representative_programs)
                        original_count = len(candidates)
                        candidates = [c for c in candidates if id(c.program) in representative_set]
                        
                        if len(candidates) < original_count:
                            LOGGER.info("Symmetry deduplication: reduced %d candidates to %d representatives (symmetry group order %d)",
                                       original_count, len(candidates), symmetry_group.order)
                            summary["symmetry_deduplication"] = {
                                "original_count": original_count,
                                "deduplicated_count": len(candidates),
                                "symmetry_group_order": symmetry_group.order,
                                "symmetry_type": symmetry_group.type,
                            }
            except Exception as e:
                LOGGER.warning("Symmetry deduplication failed: %s. Using all candidates.", e)
        
        self._emit_metric(summary)
        
        # Update library with successful programs
        if self.library_manager and summary_status == "success":
            successful_programs = [c.program for c in candidates if c.verification_passed]
            if successful_programs:
                self.library_manager.on_solve_success(
                    task_id,
                    successful_programs,
                    candidates,
                    egraph
                )
                LOGGER.info(f"Updated library with {len(successful_programs)} successful programs from task {task_id}")
        
        # Train advanced search from successful programs
        if self.advanced_search and summary_status == "success":
            successful_programs = [c.program for c in candidates if c.verification_passed]
            if successful_programs:
                self.advanced_search.train_from_successful_programs(successful_programs)
                LOGGER.info(f"Trained advanced search from {len(successful_programs)} successful programs")
        
        # Cache successful programs
        if self.cache_manager and summary_status == "success":
            successful_programs = [c.program for c in candidates if c.verification_passed]
            if successful_programs and hasattr(self.cache_manager, "cache_program_semantics"):
                io_examples = [(example.input_grid, example.output_grid) for example in examples]
                try:
                    self.cache_manager.cache_program_semantics(
                        successful_programs[0],
                        io_examples,
                        interpreter=self.interpreter,
                    )
                except Exception as exc:  # pragma: no cover - cache is best effort
                    LOGGER.debug("Failed to cache program for %s: %s", task_id, exc)
        
        # Record telemetry
        ensure_telemetry_started()
        if self.telemetry_collector and hasattr(self.telemetry_collector, "record_task_completion"):
            self.telemetry_collector.record_task_completion(
                task_id,
                summary_status,
                elapsed_s,
                budget.expansions,
                budget.generated_nodes,
                len(candidates),
                len([c for c in candidates if c.verification_passed])
            )
        
        # Send failure feedback to TTT/LLM (and library manager) if we failed to solve the task
        if summary_status == "no_solution":
            failure_metadata = {
                "elapsed_s": elapsed_s,
                "expansions": budget.expansions,
                "nodes": budget.generated_nodes,
                "candidates_generated": len(candidates),
            }
            self._dispatch_failure_feedback(task_id, "search_exhausted", failure_metadata)
        elif summary_status == "partial":
            reason = "timeout" if control_reason == "cancel" else "interrupted"
            failure_metadata = {
                "elapsed_s": elapsed_s,
                "control_reason": control_reason,
            }
            self._dispatch_failure_feedback(task_id, reason, failure_metadata)
        elif summary_status == "failed":
            failure_metadata = {
                "elapsed_s": elapsed_s,
                "reason": summary.get("reason"),
                "validation": summary.get("validation_errors"),
            }
            self._dispatch_failure_feedback(task_id, summary.get("reason", "failed"), failure_metadata)

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
        if not raw_examples:
            diag = self._make_validation_diag(
                index=None,
                message="Task must include at least one training example.",
                diag_type="invalid_task",
            )
            raise TaskValidationError("No training examples were provided.", diagnostics=[diag])
        examples: List[TrainingExample] = []
        for index, example in enumerate(raw_examples):
            if not isinstance(example, dict):
                diag = self._make_validation_diag(
                    index=index,
                    message="Training example must be a mapping.",
                    diag_type="invalid_example",
                    extra={"observed_type": type(example).__name__},
                )
                raise TaskValidationError("Training example is not a mapping.", diagnostics=[diag])
            input_grid = example.get("input") or example.get("input_grid")
            output_grid = example.get("output") or example.get("output_grid")
            metadata = dict(example.get("metadata", {}))
            metadata.setdefault("index", index)
            normalised_input, _ = self._normalise_example_grid(
                input_grid,
                grid_role="input",
                example_index=index,
                metadata=metadata,
            )
            normalised_output, _ = self._normalise_example_grid(
                output_grid,
                grid_role="output",
                example_index=index,
                metadata=metadata,
            )
            examples.append(TrainingExample(input_grid=normalised_input, output_grid=normalised_output, metadata=metadata))
        
        # Apply color normalization if enabled
        if self.symmetry_enabled and self.color_normalization_enabled and self.color_normalizer:
            try:
                normalized_examples, color_mapping = self.color_normalizer.canonical_relabel(examples)
                LOGGER.debug("Applied color normalization: %s", color_mapping)
                return normalized_examples
            except Exception as e:
                LOGGER.warning("Color normalization failed: %s. Using original examples.", e)
        
        return examples

    def _normalise_example_grid(
        self,
        grid_value: Any,
        *,
        grid_role: str,
        example_index: int,
        metadata: Dict[str, Any],
    ) -> Tuple[Any, Tuple[int, int]]:
        if grid_value is None:
            diag = self._make_validation_diag(
                index=example_index,
                message=f"Missing {grid_role} grid.",
                grid_role=grid_role,
                metadata=metadata,
            )
            raise TaskValidationError(f"Missing {grid_role} grid.", diagnostics=[diag])
        if isinstance(grid_value, Grid):
            rows, cols = grid_value.shape
            if rows <= 0 or cols <= 0:
                diag = self._make_validation_diag(
                    index=example_index,
                    message=f"{grid_role.capitalize()} grid must be at least 1x1.",
                    grid_role=grid_role,
                    metadata=metadata,
                    extra={"rows": rows, "cols": cols},
                )
                raise TaskValidationError("Grid dimensions are invalid.", diagnostics=[diag])
            return grid_value, (rows, cols)
        if isinstance(grid_value, (str, bytes)):
            diag = self._make_validation_diag(
                index=example_index,
                message=f"{grid_role.capitalize()} grid must be a 2D list of integers.",
                grid_role=grid_role,
                metadata=metadata,
                extra={"observed_type": type(grid_value).__name__},
            )
            raise TaskValidationError("Grid must be a 2D sequence.", diagnostics=[diag])
        try:
            rows_iterable = list(grid_value)
        except TypeError:
            diag = self._make_validation_diag(
                index=example_index,
                message=f"{grid_role.capitalize()} grid is not iterable.",
                grid_role=grid_role,
                metadata=metadata,
                extra={"observed_type": type(grid_value).__name__},
            )
            raise TaskValidationError("Grid must be iterable.", diagnostics=[diag])
        if not rows_iterable:
            diag = self._make_validation_diag(
                index=example_index,
                message=f"{grid_role.capitalize()} grid must contain at least one row.",
                grid_role=grid_role,
                metadata=metadata,
            )
            raise TaskValidationError("Grid must contain rows.", diagnostics=[diag])

        normalised_rows: List[List[Any]] = []
        row_length: Optional[int] = None
        row_lengths: List[int] = []
        for row_idx, row in enumerate(rows_iterable):
            if isinstance(row, (str, bytes)):
                diag = self._make_validation_diag(
                    index=example_index,
                    message=f"{grid_role.capitalize()} grid rows must be sequences of integers.",
                    grid_role=grid_role,
                    metadata=metadata,
                    extra={"row_index": row_idx},
                )
                raise TaskValidationError("Grid rows must be sequences.", diagnostics=[diag])
            try:
                row_values = list(row)
            except TypeError:
                diag = self._make_validation_diag(
                    index=example_index,
                    message=f"{grid_role.capitalize()} grid rows must be sequences of integers.",
                    grid_role=grid_role,
                    metadata=metadata,
                    extra={"row_index": row_idx},
                )
                raise TaskValidationError("Grid rows must be sequences.", diagnostics=[diag])
            if not row_values:
                diag = self._make_validation_diag(
                    index=example_index,
                    message=f"{grid_role.capitalize()} grid rows must contain at least one column.",
                    grid_role=grid_role,
                    metadata=metadata,
                    extra={"row_index": row_idx},
                )
                raise TaskValidationError("Grid row is empty.", diagnostics=[diag])
            row_len = len(row_values)
            row_lengths.append(row_len)
            if row_length is None:
                row_length = row_len
            elif row_len != row_length:
                diag = self._make_validation_diag(
                    index=example_index,
                    message=f"{grid_role.capitalize()} grid rows must all have the same length.",
                    grid_role=grid_role,
                    metadata=metadata,
                    extra={"row_index": row_idx, "row_lengths": row_lengths},
                )
                raise TaskValidationError("Grid rows are not rectangular.", diagnostics=[diag])
            normalised_rows.append(list(row_values))

        if row_length is None or row_length <= 0:
            diag = self._make_validation_diag(
                index=example_index,
                message=f"{grid_role.capitalize()} grid must be at least 1 column wide.",
                grid_role=grid_role,
                metadata=metadata,
            )
            raise TaskValidationError("Grid columns missing.", diagnostics=[diag])

        return normalised_rows, (len(normalised_rows), row_length)

    def _make_validation_diag(
        self,
        *,
        index: Optional[int],
        message: str,
        diag_type: str = "invalid_grid",
        grid_role: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "index": index,
            "type": diag_type,
            "reason": message,
        }
        if grid_role:
            entry["grid_role"] = grid_role
        if metadata:
            entry["example_metadata"] = self._sanitize_metadata(metadata)
        if extra:
            entry.update(extra)
        return entry

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        def _convert(value: Any) -> Any:
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            if isinstance(value, dict):
                return {str(key): _convert(val) for key, val in value.items()}
            if isinstance(value, (list, tuple)):
                return [_convert(item) for item in value]
            return repr(value)

        try:
            return {str(key): _convert(val) for key, val in metadata.items()}
        except Exception:
            return {str(key): repr(val) for key, val in metadata.items()}

    def _summarize_validation_errors(self, diagnostics: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        for entry in diagnostics:
            summary.append(
                {
                    "index": entry.get("index"),
                    "type": entry.get("type"),
                    "grid_role": entry.get("grid_role"),
                    "reason": entry.get("reason"),
                }
            )
        return summary

    def _build_failed_result(
        self,
        *,
        task_id: str,
        message: str,
        reason: str,
        diagnostics: Sequence[Dict[str, Any]],
        elapsed_s: float,
    ) -> SolverResult:
        diag_paths: List[Path] = []
        diag_entries = list(diagnostics)
        if diag_entries:
            diag_program = Program(stages=tuple())
            diag_paths.append(self._write_diagnostics(task_id, diag_program, diag_entries))

        progress_path = self._write_progress(
            task_id=task_id,
            status="failed",
            elapsed_s=elapsed_s,
            expansions=0,
            nodes=0,
        )

        summary: Dict[str, Any] = {
            "task_id": task_id,
            "status": "failed",
            "reason": reason,
            "message": message,
            "elapsed_s": elapsed_s,
            "expansions": 0,
            "nodes": 0,
            "solutions": 0,
        }
        if diag_entries:
            summary["validation_errors"] = self._summarize_validation_errors(diag_entries)

        self._emit_metric(summary)

        telemetry = SolverTelemetry(
            frontier_report=None,
            frontier_log=self.frontier_log_path,
            diagnostics=diag_paths,
            events=[],
            progress_path=progress_path,
            checkpoint_path=None,
            elapsed_s=elapsed_s,
            expansions=0,
            generated_nodes=0,
        )

        if self.telemetry_collector and hasattr(self.telemetry_collector, "record_task_completion"):
            self.telemetry_collector.record_task_completion(
                task_id,
                "failed",
                elapsed_s,
                0,
                0,
                0,
                0,
            )

        return SolverResult(
            task_id=task_id,
            status="failed",
            candidates=[],
            telemetry=telemetry,
            summary=summary,
        )

    def _dispatch_failure_feedback(self, task_id: str, reason: str, metadata: Dict[str, Any]) -> None:
        if self.coordination_enabled and self.coordination:
            self.coordination.send_failure_feedback(task_id, reason, metadata)
            LOGGER.info("Sent failure feedback for task %s: %s", task_id, reason)
        if self.library_manager:
            self.library_manager.on_solve_failure(task_id, reason, metadata)

    def _build_budget(self, task_id: str) -> SearchBudget:
        symbolic = self.symbolic_cfg
        soft_timeout = float(symbolic.get("soft_timeout_s", 90.0))
        hard_timeout = float(symbolic.get("hard_timeout_s", 150.0))
        max_depth = int(symbolic.get("max_depth", 12))
        max_expansions = int(symbolic.get("max_expansions", 5000))
        max_nodes = symbolic.get("max_nodes")
        if max_nodes is not None:
            max_nodes = int(max_nodes)
        beam_width_cfg = symbolic.get("beam_width")
        beam_width: Optional[int] = None
        if beam_width_cfg is not None:
            try:
                beam_width = int(beam_width_cfg)
            except (TypeError, ValueError):
                LOGGER.warning("Invalid symbolic.beam_width=%r; ignoring override", beam_width_cfg)
                beam_width = None
        if (beam_width is None or beam_width <= 0) and self._is_beam_strategy():
            beam_width = self._beam_width_minimum
            LOGGER.info(
                "Beam search selected without a valid beam_width; defaulting to %d for task %s",
                beam_width,
                task_id,
            )
        return SearchBudget(
            max_depth=max_depth,
            max_expansions=max_expansions,
            soft_timeout_s=soft_timeout,
            hard_timeout_s=hard_timeout,
            max_nodes=max_nodes,
            beam_width=beam_width,
            seed=self._derive_seed(task_id),
        )

    def _is_beam_strategy(self) -> bool:
        strategy_name = self.symbolic_cfg.get("search_strategy", "beam").lower()
        return strategy_name not in {"dfs", "iddfs", "iterative_deepening"}

    def _build_strategy(self, budget: SearchBudget) -> SearchStrategy:
        strategy_name = self.symbolic_cfg.get("search_strategy", "beam").lower()
        if strategy_name == "dfs":
            from arc.symbolic.search.enumerators import DepthFirstSearchStrategy

            return DepthFirstSearchStrategy(budget)
        if strategy_name in {"iddfs", "iterative_deepening"}:
            from arc.symbolic.search.enumerators import IterativeDeepeningStrategy

            return IterativeDeepeningStrategy(budget)
        if budget.beam_width is None or budget.beam_width <= 0:
            budget.beam_width = self._beam_width_minimum
            LOGGER.info(
                "Beam search requested without a valid beam_width; defaulting to %d",
                budget.beam_width,
            )
        return BeamSearchStrategy(budget)

    def _build_egraph(self) -> Optional[EGraph]:
        if not self.egraph_enabled:
            return None
        egraph_cfg = self.symbolic_cfg.get("egraph", {})
        rewrite_limit = int(egraph_cfg.get("rewrite_limit", 5000))
        saturation_limit = int(egraph_cfg.get("saturation_limit", 10000))
        cost_metric = egraph_cfg.get("cost_metric", "min_nodes")
        history_dir = Path(egraph_cfg.get("history_dir", "logs/symbolic/egraph"))
        enable_tiered_rules = bool(egraph_cfg.get("enable_tiered_rules", True))
        enable_rule_scheduling = bool(egraph_cfg.get("enable_rule_scheduling", True))
        history_dir.mkdir(parents=True, exist_ok=True)

        def cost_fn(program: Program) -> float:
            base_cost = float(len(program.stages))
            
            # Apply symmetry-aware cost adjustment if enabled
            if self.symmetry_enabled and self.symmetry_detector:
                try:
                    # Programs with more symmetry get a slight cost reduction
                    # This encourages finding symmetric solutions
                    # Count symmetric operations (rotate, reflect)
                    symmetric_ops = sum(
                        1 for stage in program.stages
                        if stage.operator in {"rotate", "reflect", "flip"}
                    )
                    if symmetric_ops > 0:
                        # Reduce cost by 5% per symmetric operation (up to 20% reduction)
                        reduction_factor = min(0.20, symmetric_ops * 0.05)
                        base_cost *= (1.0 - reduction_factor)
                except Exception:
                    pass
            
            if cost_metric == "min_nodes":
                return base_cost
            if cost_metric == "depth":
                return base_cost
            return base_cost

        egraph = EGraph(
            cost_fn=cost_fn,
            rewrite_limit=rewrite_limit,
            saturation_limit=saturation_limit,
            history_dir=history_dir,
            enable_tiered_rules=enable_tiered_rules,
            enable_rule_scheduling=enable_rule_scheduling,
        )
        return egraph

    def _run_egraph(self, egraph: EGraph, candidates: Sequence[CandidateProgram], task_id: str) -> Dict[str, Any]:
        from arc.symbolic.egraph.analyzer import EClassAnalyzer
        from arc.symbolic.egraph.extractor import OptimalExtractor
        from arc.symbolic.egraph.rule_miner import RuleMiner
        
        iterations = int(self.symbolic_cfg.get("egraph", {}).get("max_iterations", 50))
        egraph_cfg = self.symbolic_cfg.get("egraph", {})
        
        # Add programs to e-graph
        for candidate in candidates:
            egraph.add_program(candidate.program)
        
        # Run saturation with enhanced features
        stats = egraph.saturate(max_iterations=iterations)
        
        # Perform e-class analysis if enabled
        analyzer = EClassAnalyzer()
        eclass_summaries = []
        if egraph_cfg.get("enable_eclass_analysis", True):
            # Analyze a sample of programs
            sample_programs = [rec.program for rec in list(egraph._records.values())[:10]]
            for idx, program in enumerate(sample_programs):
                summary = analyzer.analyze_eclass([program], eclass_id=idx)
                eclass_summaries.append({
                    "eclass_id": idx,
                    "color_set": list(summary.color_set),
                    "symmetry": {
                        "horizontal": summary.symmetry.horizontal,
                        "vertical": summary.symmetry.vertical,
                        "rotational_90": summary.symmetry.rotational_90,
                        "rotational_180": summary.symmetry.rotational_180,
                    }
                })
        
        # Extract best program using optimal extraction
        extraction_method = egraph_cfg.get("extraction_method", "astar")
        extractor = OptimalExtractor(cost_fn=egraph.cost_fn, method=extraction_method)
        best = extractor.extract_best(egraph._records)
        
        # Mine rules from successful programs if enabled
        rule_mining_enabled = egraph_cfg.get("enable_rule_mining", False)
        mined_rules_count = 0
        if rule_mining_enabled and stats.rewrites_applied > 0:
            rule_miner = RuleMiner(min_support=3)
            mined_rules = rule_miner.mine_rules_from_egraph(egraph)
            mined_rules_count = len(mined_rules)
            LOGGER.debug("Mined %d rules from e-graph", mined_rules_count)
        
        total_tiered = stats.hot_rule_applications + stats.cold_rule_applications
        tiered_rule_stats = {
            "hot_applications": stats.hot_rule_applications,
            "cold_applications": stats.cold_rule_applications,
            "hot_ratio": (stats.hot_rule_applications / total_tiered) if total_tiered else 0.0,
            "cold_ratio": (stats.cold_rule_applications / total_tiered) if total_tiered else 0.0,
        }
        rewrite_density = stats.rewrites_applied / max(1, stats.iterations)
        
        payload: Dict[str, Any] = {
            "task_id": task_id,
            "iterations": stats.iterations,
            "rewrites": stats.rewrites_applied,
            "unique_programs": stats.unique_programs,
            "best_cost": stats.best_cost,
            "history_path": str(stats.history_path) if stats.history_path else None,
            "best_program": [(stage.operator, stage.arguments) for stage in best.program.stages] if best else None,
            "hot_rule_applications": stats.hot_rule_applications,
            "cold_rule_applications": stats.cold_rule_applications,
            "saturation_limit_reached": stats.saturation_limit_reached,
            "extraction_method": extraction_method,
            "tiered_rule_stats": tiered_rule_stats,
            "rewrite_density": rewrite_density,
            "eclass_summaries": eclass_summaries[:5],  # Include first 5 summaries
            "mined_rules_count": mined_rules_count,
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
        # Apply step normalization if enabled
        program = node.program
        if self.symmetry_enabled and self.step_normalization_enabled and self.step_normalizer:
            try:
                normalized_stages = self.step_normalizer.normalize_sequence(list(program.stages))
                program = Program(stages=tuple(normalized_stages))
            except Exception as e:
                LOGGER.debug("Step normalization failed for node %s: %s", node.node_id, e)
        
        issues = validate_program(program)
        if issues:
            return None
        solved, total, failures, diag_path = self._verify_program(program, examples, task_id)
        if total == 0:
            return None

        if diag_path:
            diagnostics.append(diag_path)

        metadata_snapshot = dict(node.metadata)
        candidate_metadata: Dict[str, Any] = dict(metadata_snapshot)
        candidate_metadata.setdefault("task_id", task_id)
        candidate_metadata["node_id"] = node.node_id
        candidate_metadata["depth"] = node.depth
        candidate_metadata["cost"] = node.cost
        candidate_metadata["generated_at"] = time.time()
        candidate_metadata["solved_examples"] = solved
        candidate_metadata["total_examples"] = total
        
        # SMT verification if enabled
        if self.smt_enabled and self.smt_verifier and solved == total:
            smt_result = self._verify_with_smt(program, examples)
            candidate_metadata["smt_verification"] = {
                "status": smt_result.status,
                "time": smt_result.verification_time,
                "verified": smt_result.is_verified,
            }
            # Only issue SMT token if verification passed
            if smt_result.is_verified:
                smt_token = self._issue_virtual_smt_token(task_id, node.node_id)
                if smt_token:
                    candidate_metadata["smt_token"] = smt_token
        else:
            # Issue virtual token without actual verification
            smt_token = self._issue_virtual_smt_token(task_id, node.node_id)
            if smt_token:
                candidate_metadata["smt_token"] = smt_token

        # Check invariants if enabled
        if self.invariant_checker and solved < total:
            invariant_results = self._check_invariants(program, examples, failures)
            candidate_metadata["invariant_checks"] = invariant_results
        
        # Attempt program repair if enabled and partially failing
        repaired_programs = []
        if self.program_repairer and 0 < solved < total:
            repaired_programs = self._attempt_repair(program, examples, failures)
            if repaired_programs:
                candidate_metadata["repair_attempted"] = True
                candidate_metadata["repair_count"] = len(repaired_programs)

        candidate = CandidateProgram(
            node_id=node.node_id,
            program=program,
            score=node.score,
            cost=node.cost,
            solved_examples=solved,
            total_examples=total,
            verification_passed=solved == total and total > 0,
            metadata=candidate_metadata,
        )
        if failures:
            candidate.metadata["failures"] = failures
        
        # If we have repaired programs, create additional candidates
        if repaired_programs and self.solution_arbitrator:
            all_programs = [program] + repaired_programs
            # Convert examples to CEGIS format
            cegis_examples = self._convert_to_cegis_examples(examples)
            # Arbitrate among solutions
            ranked = self.solution_arbitrator.arbitrate_solutions(all_programs, cegis_examples)
            if ranked and ranked[0][0] != program:
                # Best solution is a repaired version
                best_program, best_score = ranked[0]
                candidate.program = best_program
                candidate.metadata["repaired"] = True
                candidate.metadata["arbitration_score"] = best_score
                # Re-verify the repaired program
                solved, total, failures, _ = self._verify_program(best_program, examples, task_id)
                candidate.solved_examples = solved
                candidate.total_examples = total
                candidate.verification_passed = solved == total and total > 0
        
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

    def _capture_heuristic_metadata(self, node: SearchNode, result: HeuristicResult) -> None:
        heuristics_bucket = node.metadata.setdefault("heuristics", {})
        heuristics_bucket["score"] = result.score
        if result.components:
            components = heuristics_bucket.setdefault("components", {})
            components.update(result.components)

    def _verify_with_smt(
        self,
        program: Program,
        examples: Sequence[TrainingExample]
    ) -> Any:
        """Verify a program using SMT solver.
        
        Args:
            program: Program to verify
            examples: Training examples
            
        Returns:
            VerificationResult from SMT verifier
        """
        from arc.symbolic.dsl.types import Grid
        
        # Use the first example for SMT verification
        # (Full verification would check all examples)
        if not examples:
            # Return a dummy result
            from arc.symbolic.smt.types import VerificationResult
            return VerificationResult(
                program_id="no_examples",
                status="unknown",
                verification_time=0.0,
                metadata={"reason": "no examples provided"}
            )
        
        example = examples[0]
        input_grid = Grid.from_list(example.input_grid)
        output_grid = Grid.from_list(example.output_grid)
        
        try:
            result = self.smt_verifier.verify_incremental(
                program, input_grid, output_grid
            )
            return result
        except Exception as e:
            from arc.symbolic.smt.types import VerificationResult
            return VerificationResult(
                program_id="error",
                status="error",
                verification_time=0.0,
                metadata={"error": str(e)}
            )
    
    def _issue_virtual_smt_token(self, task_id: str, node_id: int) -> Optional[str]:
        if not self._smt_issue_tokens:
            return None
        self._smt_token_counter += 1
        payload = f"{task_id}:{node_id}:{self._smt_token_counter}:{time.time_ns()}:{self._smt_virtual_secret}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{self._smt_token_prefix}{digest[:24]}"

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
            "smt_token": candidate.metadata.get("smt_token"),
        }
    
    def _check_invariants(
        self,
        program: Program,
        examples: Sequence[TrainingExample],
        failures: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check invariants on failed examples."""
        if not self.invariant_checker:
            return {}
        
        from arc.symbolic.dsl.types import Grid
        
        invariant_results = {}
        for failure in failures:
            if failure.get("type") == "grid_mismatch":
                example_idx = failure.get("index", 0)
                if example_idx < len(examples):
                    example = examples[example_idx]
                    input_grid = Grid.from_list(example.input_grid)
                    expected_grid = Grid.from_list(example.output_grid)
                    actual_grid = Grid.from_list(failure.get("actual", []))
                    
                    # Check all invariants
                    results = self.invariant_checker.check_all_invariants(
                        input_grid, actual_grid
                    )
                    invariant_results[f"example_{example_idx}"] = results
        
        return invariant_results
    
    def _attempt_repair(
        self,
        program: Program,
        examples: Sequence[TrainingExample],
        failures: List[Dict[str, Any]],
    ) -> List[Program]:
        """Attempt to repair a partially failing program."""
        if not self.program_repairer:
            return []
        
        from arc.symbolic.dsl.types import Grid
        
        # Separate failed and passed examples
        failed_examples = []
        passed_examples = []
        
        failed_indices = {f.get("index", -1) for f in failures if f.get("type") == "grid_mismatch"}
        
        for idx, example in enumerate(examples):
            cegis_example = CEGISExample(
                input_grid=Grid.from_list(example.input_grid),
                output_grid=Grid.from_list(example.output_grid),
                metadata=dict(example.metadata),
            )
            if idx in failed_indices:
                failed_examples.append(cegis_example)
            else:
                passed_examples.append(cegis_example)
        
        # Attempt repair
        try:
            repaired = self.program_repairer.repair_program(
                program, failed_examples, passed_examples
            )
            return repaired
        except Exception as e:
            LOGGER.debug("Program repair failed: %s", e)
            return []
    
    def _convert_to_cegis_examples(
        self,
        examples: Sequence[TrainingExample],
    ) -> List[CEGISExample]:
        """Convert TrainingExample to CEGIS Example format."""
        from arc.symbolic.dsl.types import Grid
        
        cegis_examples = []
        for example in examples:
            cegis_example = CEGISExample(
                input_grid=Grid.from_list(example.input_grid),
                output_grid=Grid.from_list(example.output_grid),
                metadata=dict(example.metadata),
            )
            cegis_examples.append(cegis_example)
        return cegis_examples
    
    def _build_cached_result(
        self,
        task_id: str,
        cached_program: Program,
    ) -> SolverResult:
        """Build a solver result from a cached program.
        
        Args:
            task_id: Task ID
            cached_program: Cached program
            
        Returns:
            SolverResult with the cached program
        """
        candidate = CandidateProgram(
            node_id=0,
            program=cached_program,
            score=1.0,
            cost=float(len(cached_program.stages)),
            solved_examples=0,  # Will be verified by caller
            total_examples=0,
            verification_passed=True,
            metadata={
                "task_id": task_id,
                "source": "cache",
                "cached": True,
            }
        )
        
        telemetry = SolverTelemetry(
            frontier_report=None,
            frontier_log=self.frontier_log_path,
            diagnostics=[],
            events=[],
            progress_path=None,
            checkpoint_path=None,
            elapsed_s=0.0,
            expansions=0,
            generated_nodes=0,
        )
        
        summary = {
            "task_id": task_id,
            "status": "success",
            "elapsed_s": 0.0,
            "expansions": 0,
            "nodes": 0,
            "solutions": 1,
            "cached": True,
        }
        
        return SolverResult(
            task_id=task_id,
            status="success",
            candidates=[candidate],
            telemetry=telemetry,
            summary=summary,
        )


__all__ = ["SymbolicSolver", "SolverResult", "SolverTelemetry"]
