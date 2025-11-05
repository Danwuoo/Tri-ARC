from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence, Set

from .models import ArbitrationCandidate, ScoreBreakdown


class CandidateScorer:
    """Blend module priors, confidence, runtime penalties, and diversity bonuses."""

    def __init__(self, config: Dict[str, Any]) -> None:
        arbitrator_cfg = config.get("arbitrator", {})
        self.default_prior = float(arbitrator_cfg.get("default_prior", 0.5))
        self.module_priors: Dict[str, float] = {
            key: float(value)
            for key, value in arbitrator_cfg.get("module_priors", {}).items()
        }
        self.runtime_penalty_weight = float(arbitrator_cfg.get("runtime_penalty_weight", 0.05))
        self.diversity_bonus_value = float(arbitrator_cfg.get("diversity_bonus", 0.05))
        self.low_confidence_threshold = float(arbitrator_cfg.get("confidence_threshold", 0.65))
        self.diversity_gap = float(arbitrator_cfg.get("diversity_gap", 0.1))

    def score_candidate(
        self,
        candidate: ArbitrationCandidate,
        *,
        observed_signatures: Optional[Set[str]] = None,
        ledger: Optional[Dict[str, Any]] = None,
    ) -> ScoreBreakdown:
        prior = self._module_prior(candidate.module, ledger=ledger)
        confidence = self._confidence_signal(candidate)
        runtime_penalty = self._runtime_penalty(candidate)
        diversity_bonus = self._diversity_bonus(candidate, observed_signatures or set())
        extras: Dict[str, Any] = {}

        # Flag low-confidence items explicitly
        if confidence < self.low_confidence_threshold:
            extras["low_confidence"] = True

        breakdown = ScoreBreakdown(
            module_prior=prior,
            confidence=confidence,
            runtime_penalty=runtime_penalty,
            diversity_bonus=diversity_bonus,
            extras=extras,
        )
        candidate.score = breakdown
        return breakdown

    # ------------------------------------------------------------------ #
    # Individual components
    # ------------------------------------------------------------------ #
    def _module_prior(self, module: str, ledger: Optional[Dict[str, Any]]) -> float:
        if ledger and module in ledger:
            entry = ledger[module]
            solved = float(entry.get("solved", 0))
            attempts = float(entry.get("attempts", 1))
            if attempts <= 0:
                attempts = 1.0
            return max(0.0, min(1.0, solved / attempts))
        return self.module_priors.get(module, self.default_prior)

    def _confidence_signal(self, candidate: ArbitrationCandidate) -> float:
        metadata = candidate.metadata
        # Symbolic lane typically exposes solver score and coverage.
        if "score" in metadata:
            value = float(metadata.get("score", 0.0))
            return max(0.0, min(1.0, value))

        if "confidence" in metadata:
            return max(0.0, min(1.0, float(metadata["confidence"])))

        solved = float(metadata.get("solved_examples", 0))
        total = float(metadata.get("total_examples", 0))
        if total > 0:
            return max(0.0, min(1.0, solved / total))

        if candidate.verification and candidate.verification.status.value == "passed":
            return 0.75
        return 0.4

    def _runtime_penalty(self, candidate: ArbitrationCandidate) -> float:
        runtime_s = float(candidate.metadata.get("runtime_s", candidate.metadata.get("elapsed_s", 0.0)))
        if runtime_s <= 0.0:
            return 0.0
        return max(0.0, min(1.0, runtime_s * self.runtime_penalty_weight))

    def _diversity_bonus(self, candidate: ArbitrationCandidate, observed: Set[str]) -> float:
        signature = candidate.compute_signature()
        return 0.0 if signature in observed else self.diversity_bonus_value


def rank_candidates(candidates: Sequence[ArbitrationCandidate]) -> Sequence[ArbitrationCandidate]:
    """Return candidates sorted by descending score with stable ordering."""
    return tuple(
        sorted(
            candidates,
            key=lambda item: (item.normalised_score(), -_float_safe(item.metadata.get("runtime_s", 0.0))),
            reverse=True,
        )
    )


def _float_safe(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return math.inf


__all__ = ["CandidateScorer", "rank_candidates"]

