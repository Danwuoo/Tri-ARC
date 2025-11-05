from __future__ import annotations

import hashlib
import math
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from arc.symbolic.search.types import SearchNode

from .base import HeuristicContext, HeuristicResult, HeuristicScorer

LOGGER = logging.getLogger("arc.symbolic.heuristics.neural")


def _normalise_features(features: Dict[str, float]) -> Dict[str, float]:
    normalised = dict(features)
    normalised["depth_ratio"] = min(max(normalised.get("depth_ratio", 0.0), 0.0), 1.0)
    normalised["coverage"] = min(max(normalised.get("coverage", 0.0), 0.0), 1.0)
    normalised["consistency"] = min(max(normalised.get("consistency", 0.0), 0.0), 1.0)
    for key in ("progress", "novelty"):
        normalised[key] = max(normalised.get(key, 0.0), 0.0)
    return normalised


@dataclass
class NeuralHeuristicConfig:
    model_path: Path
    checksum_path: Optional[Path] = None
    device: str = "cuda:0"
    requires_checksum: bool = False


class NeuralHeuristic(HeuristicScorer):
    """Neural scoring model that blends with rule-based priors."""

    def __init__(self, config: NeuralHeuristicConfig):
        super().__init__(name="neural")
        self.config = config
        self._available = False
        self._torch = None
        self._model = None
        self._device = config.device

        try:
            import torch  # type: ignore

            self._torch = torch
            self._available = True
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.warning("PyTorch unavailable for neural heuristic: %s", exc)
            self._available = False

    def initialise(self, context: HeuristicContext) -> None:
        super().initialise(context)
        if not self._available:
            return
        model_path = self.config.model_path
        if not model_path.exists():
            LOGGER.warning("Neural heuristic weights missing at %s. Falling back to rule-based scoring.", model_path)
            self._available = False
            return
        if self.config.checksum_path and self.config.checksum_path.exists():
            expected = self.config.checksum_path.read_text(encoding="utf-8").strip()
            actual = self._compute_checksum(model_path)
            if expected != actual:
                message = f"Heuristic weights checksum mismatch: expected {expected}, got {actual}"
                if self.config.requires_checksum:
                    raise RuntimeError(message)
                LOGGER.warning("%s", message)
        try:
            self._model = self._torch.jit.load(str(model_path), map_location="cpu")
            self._model.eval()
            if self._device != "cpu":
                try:
                    self._model.to(self._device)
                except Exception as exc:  # pragma: no cover - environment specific
                    LOGGER.warning("Failed to move neural heuristic to %s: %s", self._device, exc)
            LOGGER.info("Loaded neural heuristic model from %s", model_path)
        except Exception as exc:  # pragma: no cover - model might be absent
            LOGGER.warning("Failed to load neural heuristic model: %s", exc)
            self._available = False

    def shutdown(self) -> None:
        self._model = None
        super().shutdown()

    def score_node(self, node: SearchNode) -> HeuristicResult:
        assert self.context is not None
        features = self._build_features(node)
        if not self._available or self._model is None or self._torch is None:
            # Deterministic lightweight scoring fallback.
            baseline = (
                3.0 * features["coverage"]
                + 2.0 * features["consistency"]
                + 1.0 * features["progress"]
                + 0.5 * features["novelty"]
                - 1.5 * features["depth_ratio"]
                - 0.3 * features["cost"]
                - 0.4 * features["stagnation"]
            )
            score = 1.0 / (1.0 + math.exp(-baseline))
            return HeuristicResult(score=score, components={"neural_fallback": score}, reasoning=features)

        tensor = self._torch.tensor(
            [
                features["coverage"],
                features["consistency"],
                features["progress"],
                features["novelty"],
                features["depth_ratio"],
                features["cost"],
                features["stagnation"],
            ],
            dtype=self._torch.float32,
            device=self._device,
        )
        with self._torch.no_grad():
            logits = self._model(tensor.unsqueeze(0))
            score = float(self._torch.sigmoid(logits).item())
        return HeuristicResult(score=score, components={"neural": score}, reasoning=features)

    def _build_features(self, node: SearchNode) -> Dict[str, float]:
        data = node.metadata
        depth_ratio = node.depth / max(1, self.context.max_depth)
        features = {
            "coverage": float(data.get("coverage", 0.0)),
            "consistency": float(data.get("consistency", 0.0)),
            "progress": float(data.get("progress", 0.0)),
            "novelty": float(data.get("novelty", 0.0)),
            "stagnation": float(data.get("stagnation", 0.0)),
            "depth_ratio": depth_ratio,
            "cost": float(node.cost),
        }
        return _normalise_features(features)

    @staticmethod
    def _compute_checksum(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


__all__ = ["NeuralHeuristic", "NeuralHeuristicConfig"]
