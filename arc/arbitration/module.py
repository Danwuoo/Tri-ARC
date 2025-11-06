from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from arc.core import (
    ModuleCapabilities,
    ModuleContext,
    ModuleResult,
    ModuleSolveStatus,
    ModuleTaskContext,
    SolverModule,
)
from arc.core.results import ModuleTelemetry

from .fallbacks import generate_fallback_candidates
from .models import ArbitrationCandidate, CandidateType, VerificationStatus
from .scoring import CandidateScorer
from .selection import ArbitrationDecision, select_candidates
from .verification import VerificationRunner
from .models import normalise_candidates

LOGGER = logging.getLogger("arc.module.arbitrator")


class ArbitratorModule(SolverModule):
    module_name = "arbitrator"
    capabilities = ModuleCapabilities(
        supports_partial_results=False,
        supports_resume=False,
        requires_gpu=False,
        extras={"lane": "arbitrator"},
    )

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._outputs_dir = Path(config.get("arbitrator", {}).get("outputs_dir", "outputs"))
        self._reports_dir = Path(config.get("arbitrator", {}).get("reports_dir", "reports"))
        self._logs_dir = Path(config.get("arbitrator", {}).get("logs_dir", "logs/arbitrator"))
        self._verification = VerificationRunner(config, log_dir=self._logs_dir / "verification")
        self._scorer = CandidateScorer(config)
        self._rolling_ledger: Dict[str, Dict[str, Any]] = {}
        self._stats: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle hooks
    # ------------------------------------------------------------------ #
    def _on_initialize(self, context: ModuleContext) -> None:
        self._outputs_dir.mkdir(parents=True, exist_ok=True)
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        (self._logs_dir / "verification").mkdir(parents=True, exist_ok=True)
        (self._logs_dir / "decisions").mkdir(parents=True, exist_ok=True)
        shared_namespace = context.shared_cache.setdefault(self.module_name, {})
        ledger = shared_namespace.setdefault("ledger", {})
        self._rolling_ledger = ledger  # type: ignore[assignment]
        stats = shared_namespace.setdefault(
            "stats",
            {
                "processed": 0,
                "fallback": 0,
                "low_confidence": 0,
                "total_latency_ms": 0.0,
                "max_latency_ms": 0.0,
            },
        )
        self._stats = stats  # type: ignore[assignment]

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        shared_namespace = task_context.module_context.shared_cache.setdefault(self.module_name, {})
        module_cache = shared_namespace.setdefault(task_context.task_id, {})
        task_context.cache_namespace = module_cache
        task_context.metadata["module"] = self.module_name
        task_context.metadata["cache_key"] = f"{self.module_name}:{task_context.task_id}"
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        task_id = task_context.task_id
        payload = dict(task_context.task_payload)
        train_examples = payload.get("train_examples", [])
        test_examples = payload.get("test_examples") or payload.get("eval_examples") or []
        solve_started_at = time.time()

        module_candidates = self._collect_candidates(task_context)
        verified_candidates = self._verification.verify_candidates(task_id, module_candidates, train_examples)
        observed_signatures: set[str] = set()
        for candidate in verified_candidates:
            self._scorer.score_candidate(candidate, observed_signatures=observed_signatures, ledger=self._rolling_ledger)
            observed_signatures.add(candidate.compute_signature())

        decision = select_candidates(
            verified_candidates,
            confidence_threshold=float(self.config.get("arbitrator", {}).get("confidence_threshold", 0.65)),
            diversity_gap=float(self.config.get("arbitrator", {}).get("diversity_gap", 0.1)),
        )

        fallback_used = False
        if not decision.primary:
            fallback_candidates = generate_fallback_candidates(task_id, train_examples, test_examples)
            for fallback in fallback_candidates:
                fallback.verification.status = VerificationStatus.PASSED  # type: ignore[union-attr]
                fallback.score = self._scorer.score_candidate(fallback, observed_signatures=observed_signatures)
                observed_signatures.add(fallback.compute_signature())
            decision = select_candidates(
                list(verified_candidates) + fallback_candidates,
                confidence_threshold=float(self.config.get("arbitrator", {}).get("confidence_threshold", 0.65)),
                diversity_gap=float(self.config.get("arbitrator", {}).get("diversity_gap", 0.1)),
            )
            fallback_used = decision.primary.module == "fallback" if decision.primary else True

        answers = self._materialise_answers(task_id, decision.answers(), test_examples)
        latency_ms = (time.time() - solve_started_at) * 1000.0
        summary = self._build_summary(
            task_id,
            decision,
            answers,
            fallback_used=fallback_used,
            latency_ms=latency_ms,
        )

        result = ModuleResult(
            task_id=task_id,
            status=ModuleSolveStatus.SUCCESS if answers else ModuleSolveStatus.FAILED,
            candidates=[
                {
                    "candidate_id": candidate.candidate_id,
                    "module": candidate.module,
                    "score": candidate.normalised_score(),
                    "metadata": candidate.metadata,
                    "provenance": candidate.provenance,
                }
                for candidate in decision.answers()
            ],
            summary=summary,
            telemetry=self._build_telemetry(started_at=solve_started_at),
        )

        self._update_ledger(decision)
        self._persist_outputs(task_id, answers)
        self._persist_report(task_id, decision, answers, summary)
        self._emit_metrics(task_context, decision, summary)
        self._update_stats(summary, latency_ms=latency_ms)
        task_context.cache_namespace["decision"] = summary
        return result

    def _on_shutdown(self, context: ModuleContext) -> None:
        namespace = context.shared_cache.setdefault(self.module_name, {})
        if self._rolling_ledger:
            namespace["ledger"] = self._rolling_ledger
        if self._stats:
            namespace["stats"] = self._stats

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _collect_candidates(self, task_context: ModuleTaskContext) -> List[ArbitrationCandidate]:
        shared_cache = task_context.module_context.shared_cache
        task_id = task_context.task_id
        candidates: List[ArbitrationCandidate] = []

        for module_name, module_namespace in shared_cache.items():
            if module_name == self.module_name:
                continue
            task_entries = module_namespace.get(task_id)
            if not isinstance(task_entries, dict):
                continue
            raw_candidates = task_entries.get("candidates") or []
            if not raw_candidates:
                continue
            normalised = normalise_candidates(module_name, raw_candidates)
            candidates.extend(normalised)

        return candidates

    def _materialise_answers(
        self,
        task_id: str,
        selected: Sequence[ArbitrationCandidate],
        test_examples: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        answers: List[Dict[str, Any]] = []
        for candidate in selected:
            outputs = []
            if candidate.candidate_type == CandidateType.FALLBACK:
                outputs = candidate.payload.get("outputs", [])
            elif candidate.candidate_type == CandidateType.GRID:
                payload_outputs = candidate.payload.get("outputs")
                if payload_outputs:
                    outputs = payload_outputs
                elif candidate.metadata.get("eval_outputs"):
                    outputs = [
                        record.get("grid")
                        for record in candidate.metadata.get("eval_outputs")
                        if record.get("grid") is not None
                    ]
                else:
                    outputs = [candidate.payload.get("grid")]
            else:
                outputs = self._execute_on_examples(candidate, test_examples)
            outputs = [self._grid_to_list(item) for item in outputs if item is not None]
            answers.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "module": candidate.module,
                    "outputs": outputs,
                    "score": candidate.normalised_score(),
                    "signature": candidate.compute_signature(),
                    "rationale": candidate.transformation_summary(),
                }
            )
        return answers

    def _execute_on_examples(
        self,
        candidate: ArbitrationCandidate,
        examples: Sequence[Dict[str, Any]],
    ) -> List[Any]:
        outputs: List[Any] = []
        for index, example in enumerate(examples):
            grid = example.get("input")
            if grid is None:
                outputs.append(None)
                continue
            try:
                result = self._verification.execute_candidate(
                    candidate,
                    grid,
                    metadata={"task_id": example.get("task_id"), "example_index": index},
                )
                outputs.append(result.to_list())
            except Exception as exc:
                LOGGER.warning(
                    "Candidate %s failed execution on evaluation example %d: %s",
                    candidate.candidate_id,
                    index,
                    exc,
                )
                outputs.append(None)
        return outputs

    def _grid_to_list(self, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "to_list"):
            try:
                return value.to_list()
            except Exception:
                pass
        if isinstance(value, list):
            return value
        return value

    def _build_summary(
        self,
        task_id: str,
        decision: ArbitrationDecision,
        answers: Sequence[Dict[str, Any]],
        *,
        fallback_used: bool,
        latency_ms: float,
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "task_id": task_id,
            "answers": answers,
            "answers_outputs": [answer["outputs"] for answer in answers],
            "rationale": decision.rationale,
            "low_confidence": decision.low_confidence,
            "fallback_used": fallback_used,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "latency_ms": latency_ms,
        }
        rejected_payload = []
        for candidate in decision.rejected:
            rejected_payload.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "module": candidate.module,
                    "score": candidate.normalised_score(),
                    "verification_status": candidate.verification.status.value if candidate.verification else "unknown",
                    "failure_reason": candidate.verification.failure_reason if candidate.verification else None,
                }
            )
        summary["rejected_candidates"] = rejected_payload
        return summary

    def _persist_outputs(self, task_id: str, answers: Sequence[Dict[str, Any]]) -> None:
        path = self._outputs_dir / "pass2.json"
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        existing[task_id] = [answer["outputs"] for answer in answers]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def _persist_report(
        self,
        task_id: str,
        decision: ArbitrationDecision,
        answers: Sequence[Dict[str, Any]],
        summary: Dict[str, Any],
    ) -> None:
        timestamp = time.strftime("%Y%m%d")
        report_path = self._reports_dir / f"arbitration_summary_{timestamp}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        header = f"# Arbitration Summary ({timestamp})\n\n"
        if report_path.exists():
            content = report_path.read_text(encoding="utf-8")
        else:
            content = header
        lines = [content.rstrip(), "", f"## Task {task_id}", ""]
        lines.append(f"- Answers emitted: {len(answers)}")
        lines.append(f"- Low confidence: {decision.low_confidence}")
        lines.append(f"- Fallback used: {summary['fallback_used']}")
        lines.append(f"- Solve latency: {summary['latency_ms']:.1f} ms")
        for answer in answers:
            lines.append(
                f"  - Candidate {answer['candidate_id']} (module={answer['module']}) score={answer['score']:.3f}"
            )
        if decision.rationale:
            lines.append("- Rationale:")
            for item in decision.rationale:
                lines.append(f"  - {item}")
        if decision.rejected:
            lines.append("- Rejected candidates:")
            for candidate in decision.rejected:
                state = candidate.verification.status.value if candidate.verification else "unknown"
                reason = candidate.verification.failure_reason if candidate.verification else ""
                lines.append(f"  - {candidate.candidate_id} [{candidate.module}] status={state} reason={reason}")
        lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")

        decisions_log = self._logs_dir / "decisions" / f"{task_id}.json"
        with decisions_log.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)

    def _update_ledger(self, decision: ArbitrationDecision) -> None:
        for candidate in decision.rejected + decision.answers():
            module_entry = self._rolling_ledger.setdefault(candidate.module, {"attempts": 0, "solved": 0})
            module_entry["attempts"] += 1
        for candidate in decision.answers():
            if candidate.module == "fallback":
                continue
            module_entry = self._rolling_ledger.setdefault(candidate.module, {"attempts": 0, "solved": 0})
            module_entry["solved"] += 1

    def _update_stats(self, summary: Dict[str, Any], *, latency_ms: float) -> None:
        stats = self._stats
        stats["processed"] = int(stats.get("processed", 0)) + 1
        if summary.get("fallback_used"):
            stats["fallback"] = int(stats.get("fallback", 0)) + 1
        if summary.get("low_confidence"):
            stats["low_confidence"] = int(stats.get("low_confidence", 0)) + 1
        stats["total_latency_ms"] = float(stats.get("total_latency_ms", 0.0)) + float(latency_ms)
        stats["max_latency_ms"] = max(float(stats.get("max_latency_ms", 0.0)), float(latency_ms))
        stats["latest_latency_ms"] = float(latency_ms)
        self._write_health_dashboard(stats)

    def _emit_metrics(
        self,
        task_context: ModuleTaskContext,
        decision: ArbitrationDecision,
        summary: Dict[str, Any],
    ) -> None:
        sink = task_context.module_context.metrics_sink
        if not sink:
            return
        payload = {
            "event": "arbitrator_decision",
            "task_id": task_context.task_id,
            "module": self.module_name,
            "answers": [
                {
                    "candidate_id": answer["candidate_id"],
                    "module": answer["module"],
                    "score": answer["score"],
                }
                for answer in summary["answers"]
            ],
            "fallback_used": summary["fallback_used"],
            "low_confidence": summary["low_confidence"],
            "timestamp": summary["timestamp"],
            "latency_ms": summary.get("latency_ms"),
        }
        try:
            sink(payload)
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Metrics sink rejected arbitrator payload: %s", exc)

    def _build_telemetry(self, *, started_at: float) -> ModuleTelemetry:
        telemetry = ModuleTelemetry.started(self.module_name, "solve", timestamp=started_at)
        telemetry = telemetry.complete("completed", timestamp=time.time())
        return telemetry

    def _write_health_dashboard(self, stats: Dict[str, Any]) -> None:
        processed = max(1, int(stats.get("processed", 1)))
        average_latency = float(stats.get("total_latency_ms", 0.0)) / processed
        fallback_rate = float(stats.get("fallback", 0)) / processed
        low_confidence_rate = float(stats.get("low_confidence", 0)) / processed
        timestamp = time.strftime("%Y%m%d")
        path = self._reports_dir / f"arbitrator_health_{timestamp}.md"
        lines = [
            f"# Arbitrator Health ({timestamp})",
            "",
            f"- Tasks processed: {processed}",
            f"- Fallback activations: {stats.get('fallback', 0)} ({fallback_rate:.2%})",
            f"- Low confidence decisions: {stats.get('low_confidence', 0)} ({low_confidence_rate:.2%})",
            f"- Average latency: {average_latency:.1f} ms",
            f"- Max latency: {stats.get('max_latency_ms', 0.0):.1f} ms",
            f"- Latest latency: {stats.get('latest_latency_ms', 0.0):.1f} ms",
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
