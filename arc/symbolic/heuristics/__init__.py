from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Set

from .base import (
    CalibratedHeuristicEnsemble,
    HeuristicContext,
    HeuristicEnsemble,
    HeuristicResult,
    HeuristicScorer,
    logistic_normalise,
)
from .neural import NeuralHeuristic, NeuralHeuristicConfig
from .rule_based import RuleBasedHeuristic, RuleBasedWeights


def _resolve_active_set(heuristics_cfg: Dict[str, Any]) -> Optional[Set[str]]:
    active = heuristics_cfg.get("active")
    if active is None:
        mode = heuristics_cfg.get("mode")
        if isinstance(mode, str):
            lowered = mode.strip().lower()
            if lowered == "rule_only":
                return {"rule_based"}
            if lowered == "neural_only":
                return {"neural"}
        return None
    if isinstance(active, str):
        tokens: Sequence[str] = [token for token in (part.strip() for part in active.replace(",", " ").split()) if token]
    elif isinstance(active, Sequence):
        tokens = [str(token).strip() for token in active if str(token).strip()]
    else:
        return None
    return {token.lower() for token in tokens}


def _should_enable(block: Dict[str, Any], name: str, active: Optional[Set[str]]) -> bool:
    if not block.get("enabled", True):
        return False
    if active is None:
        return True
    return name in active


def build_heuristic_from_config(config: Dict[str, Any], *, device: str) -> HeuristicScorer:
    """Construct a heuristic ensemble using repository configuration defaults."""
    symbolic_cfg = config.get("symbolic", {})
    heuristics_cfg = symbolic_cfg.get("heuristics", {})
    active = _resolve_active_set(heuristics_cfg)

    members = []
    weights = []

    rule_cfg = heuristics_cfg.get("rule_based", {})
    if _should_enable(rule_cfg, "rule_based", active):
        rb_weights = RuleBasedWeights(**rule_cfg.get("weights", {}))
        members.append(RuleBasedHeuristic(weights=rb_weights))
        weights.append(rule_cfg.get("weight", 1.0))

    neural_cfg = heuristics_cfg.get("neural", {})
    if _should_enable(neural_cfg, "neural", active):
        model_path = Path(neural_cfg.get("model_path", symbolic_cfg.get("heuristics_model_path", "models/symbolic/heuristic.pt")))
        checksum_path: Optional[Path] = None
        if "checksum_path" in neural_cfg:
            checksum_path = Path(neural_cfg["checksum_path"])
        nh_config = NeuralHeuristicConfig(
            model_path=model_path,
            checksum_path=checksum_path,
            device=device,
            requires_checksum=neural_cfg.get("requires_checksum", False),
        )
        members.append(NeuralHeuristic(nh_config))
        weights.append(neural_cfg.get("weight", 1.0))

    if not members:
        raise ValueError("No heuristics enabled; at least one heuristic must be configured.")

    calibration_cfg = heuristics_cfg.get("calibration", {})
    if calibration_cfg.get("enabled", False):
        return CalibratedHeuristicEnsemble(members, weights=weights, calibration=calibration_cfg)

    if len(members) == 1:
        return members[0]

    return HeuristicEnsemble(members, weights=weights)


__all__ = [
    "HeuristicContext",
    "HeuristicEnsemble",
    "CalibratedHeuristicEnsemble",
    "HeuristicResult",
    "HeuristicScorer",
    "RuleBasedHeuristic",
    "NeuralHeuristic",
    "build_heuristic_from_config",
    "logistic_normalise",
]
