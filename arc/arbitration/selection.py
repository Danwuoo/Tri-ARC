from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .models import ArbitrationCandidate
from .scoring import rank_candidates


@dataclass
class ArbitrationDecision:
    primary: Optional[ArbitrationCandidate]
    secondary: Optional[ArbitrationCandidate]
    rejected: List[ArbitrationCandidate] = field(default_factory=list)
    rationale: List[str] = field(default_factory=list)
    low_confidence: bool = False
    fallback_triggered: bool = False

    def answers(self) -> List[ArbitrationCandidate]:
        result: List[ArbitrationCandidate] = []
        if self.primary:
            result.append(self.primary)
        if self.secondary:
            result.append(self.secondary)
        return result


def select_candidates(
    candidates: Sequence[ArbitrationCandidate],
    *,
    confidence_threshold: float,
    diversity_gap: float,
) -> ArbitrationDecision:
    ordered = rank_candidates([cand for cand in candidates if cand.is_verified()])
    if not ordered:
        return ArbitrationDecision(primary=None, secondary=None, rejected=list(candidates), fallback_triggered=True)

    primary = ordered[0]
    secondary: Optional[ArbitrationCandidate] = None
    rationale: List[str] = []
    primary_score = primary.normalised_score()
    rationale.append(
        f"Primary candidate {primary.candidate_id} selected with score {primary_score:.3f}."
    )
    low_confidence = primary_score < confidence_threshold
    if low_confidence:
        rationale.append(
            f"Primary candidate {primary.candidate_id} below confidence threshold "
            f"({primary_score:.3f} < {confidence_threshold:.2f})."
        )

    for candidate in ordered[1:]:
        if candidate.compute_signature() == primary.compute_signature():
            continue
        candidate_score = candidate.normalised_score()
        score_ratio = 0.0 if primary_score == 0 else candidate_score / primary_score
        if candidate_score >= primary_score * (1.0 - diversity_gap):
            secondary = candidate
            rationale.append(
                f"Secondary candidate {candidate.candidate_id} selected within diversity gap "
                f"({candidate_score:.3f} vs {primary_score:.3f})."
            )
            break

        if secondary is None:
            secondary = candidate
            rationale.append(
                f"Secondary candidate {candidate.candidate_id} selected via diversification heuristic "
                f"(score ratio {score_ratio:.2f} below diversity gap)."
            )
            break

    if secondary is None and len(ordered) > 1:
        rationale.append("Secondary candidate not selected due to insufficient diversity or score gap.")

    rejected = [cand for cand in candidates if cand not in {primary, secondary}]
    return ArbitrationDecision(
        primary=primary,
        secondary=secondary,
        rejected=rejected,
        rationale=rationale,
        low_confidence=low_confidence,
    )


__all__ = ["select_candidates", "ArbitrationDecision"]
