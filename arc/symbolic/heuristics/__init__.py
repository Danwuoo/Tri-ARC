from pathlib import Path
from typing import Any, Dict, Optional

from .base import HeuristicContext, HeuristicEnsemble, HeuristicResult, HeuristicScorer, logistic_normalise
from .neural import NeuralHeuristic, NeuralHeuristicConfig
from .rule_based import RuleBasedHeuristic, RuleBasedWeights


def build_heuristic_from_config(config: Dict[str, Any], *, device: str) -> HeuristicScorer:
    """Construct a heuristic ensemble using repository configuration defaults."""
    symbolic_cfg = config.get("symbolic", {})
    heuristics_cfg = symbolic_cfg.get("heuristics", {})

    members = []
    weights = []

    if heuristics_cfg.get("rule_based", {}).get("enabled", True):
        rule_cfg = heuristics_cfg.get("rule_based", {})
        rb_weights = RuleBasedWeights(**rule_cfg.get("weights", {}))
        members.append(RuleBasedHeuristic(weights=rb_weights))
        weights.append(rule_cfg.get("weight", 1.0))

    neural_cfg = heuristics_cfg.get("neural", {})
    if neural_cfg.get("enabled", True):
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

    if len(members) == 1:
        return members[0]

    return HeuristicEnsemble(members, weights=weights)


__all__ = [
    "HeuristicContext",
    "HeuristicEnsemble",
    "HeuristicResult",
    "HeuristicScorer",
    "RuleBasedHeuristic",
    "NeuralHeuristic",
    "build_heuristic_from_config",
    "logistic_normalise",
]
