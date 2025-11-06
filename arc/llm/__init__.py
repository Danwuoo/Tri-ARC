from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from arc.core import (
    ModuleCapabilities,
    ModuleContext,
    ModuleResult,
    ModuleSolveStatus,
    ModuleTaskContext,
    SolverModule,
)

Tensor = torch.Tensor


@dataclass(frozen=True)
class LLMConfiguration:
    initial_candidates: int = 4
    refinement_candidates: int = 2
    temperature_initial: float = 0.7
    top_p_initial: float = 0.9

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> "LLMConfiguration":
        return cls(
            initial_candidates=int(cfg.get("initial_candidates", cls.initial_candidates)),
            refinement_candidates=int(cfg.get("refinement_candidates", cls.refinement_candidates)),
            temperature_initial=float(cfg.get("temperature_initial", cls.temperature_initial)),
            top_p_initial=float(cfg.get("top_p_initial", cls.top_p_initial)),
        )


class ArcLLMModel(nn.Module):
    """Compact decoder predicting transformation probabilities."""

    def __init__(self, *, input_dim: int, hidden_dim: int, num_operations: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, num_operations),
        )

    def forward(self, features: Tensor) -> Tensor:
        return self.net(features)


class LLMModule(SolverModule):
    module_name = "llm"
    capabilities = ModuleCapabilities(
        supports_partial_results=True,
        supports_resume=False,
        requires_gpu=False,
        extras={"lane": "llm"},
    )

    def __init__(self, config: Dict[str, Any], *, prompt_version: Optional[str] = None) -> None:
        super().__init__(config)
        cfg = config.get("llm", {})
        self._prompt_version = prompt_version or cfg.get("prompt_version", "v1")
        self._enabled = bool(cfg.get("enabled", True))
        self._config = LLMConfiguration.from_config(cfg)
        self._model_path = Path(cfg.get("model_path", "models/llm/tri-arc-30b-qlora/model.pt"))
        self._device_label = str(cfg.get("device") or config.get("global", {}).get("device_map", {}).get("llm", "cpu"))
        self._device = self._resolve_device(self._device_label)
        self._model: Optional[ArcLLMModel] = None
        self._operations: List[str] = []
        self._feature_mean: Optional[Tensor] = None
        self._feature_std: Optional[Tensor] = None
        self._feature_dim: int = 32

    # ------------------------------------------------------------------ #
    # Lifecycle hooks
    # ------------------------------------------------------------------ #
    def _on_initialize(self, context: ModuleContext) -> None:
        if not self._enabled:
            context.logger.info("LLM lane disabled via configuration toggle.")
            return
        self._ensure_assets_exist()
        payload = torch.load(self._model_path, map_location="cpu")
        operations = payload.get("operations")
        if not operations or not isinstance(operations, list):
            raise RuntimeError(f"LLM checkpoint {self._model_path} missing operation vocabulary.")
        self._operations = [str(item) for item in operations]
        self._feature_dim = int(payload.get("feature_dim", 32))
        self._model = ArcLLMModel(input_dim=self._feature_dim, hidden_dim=int(payload.get("hidden_dim", 64)), num_operations=len(self._operations))
        state = payload.get("model_state")
        if state is None:
            raise RuntimeError(f"LLM checkpoint {self._model_path} missing 'model_state'.")
        self._model.load_state_dict(state)
        self._model.to(self._device)
        mean = payload.get("feature_mean")
        std = payload.get("feature_std")
        if mean is not None and std is not None:
            self._feature_mean = torch.tensor(mean, dtype=torch.float32, device=self._device)
            self._feature_std = torch.tensor(std, dtype=torch.float32, device=self._device).clamp_min(1e-6)
        context.logger.info(
            "LLM module initialised with prompt_version=%s, device=%s, operations=%d",
            self._prompt_version,
            self._device,
            len(self._operations),
        )

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        shared_namespace = task_context.module_context.shared_cache.setdefault(self.module_name, {})
        module_cache = shared_namespace.setdefault(task_context.task_id, {})
        task_context.cache_namespace = module_cache
        task_context.metadata["module"] = self.module_name
        task_context.metadata["prompt_version"] = self._prompt_version
        task_context.metadata["device"] = str(self._device)
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        if not self._enabled:
            summary = {"lane": self.module_name, "reason": "module_disabled"}
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)
        if self._model is None:
            raise RuntimeError("LLM model not loaded; initialise module before solving.")

        train_examples = list(task_context.task_payload.get("train_examples") or [])
        eval_examples = list(task_context.task_payload.get("eval_examples") or task_context.task_payload.get("test_examples") or [])
        if not train_examples:
            summary = {
                "lane": self.module_name,
                "profile": self._prompt_version,
                "reason": "no_train_examples",
            }
            task_context.cache_namespace["candidates"] = []
            task_context.cache_namespace["llm_summary"] = summary
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        features = self._compute_task_features(train_examples).unsqueeze(0)  # (1, feature_dim)
        logits = self._model(features)
        logits = logits / max(self._config.temperature_initial, 1e-4)
        probabilities = F.softmax(logits, dim=-1).squeeze(0)
        ranked_indices = torch.argsort(probabilities, descending=True).tolist()

        operation_context = self._build_operation_context(train_examples)
        candidates: List[Dict[str, Any]] = []
        seen_operations: set[str] = set()
        for index in ranked_indices[: max(1, self._config.initial_candidates)]:
            operation = self._operations[index]
            if operation in seen_operations:
                continue
            seen_operations.add(operation)
            probability = float(probabilities[index].item())
            eval_payload = self._evaluate_operation(
                operation=operation,
                train_examples=train_examples,
                eval_examples=eval_examples,
                context=operation_context,
            )
            if not eval_payload["train_outputs"]:
                continue
            confidence = self._blend_confidence(probability, eval_payload["train_accuracy"])
            primary_grid = None
            for record in eval_payload["eval_outputs"]:
                if record.get("grid") is not None:
                    primary_grid = record["grid"]
                    break
            if primary_grid is None:
                for record in eval_payload["train_outputs"]:
                    if record.get("grid") is not None:
                        primary_grid = record["grid"]
                        break
            if primary_grid is None:
                continue
            candidate = {
                "candidate_id": f"llm-{task_context.task_id}-{operation}",
                "type": "grid",
                "grid": primary_grid,
                "metadata": {
                    "operation": operation,
                    "confidence": confidence,
                    "train_accuracy": eval_payload["train_accuracy"],
                    "probability": probability,
                    "prompt_version": self._prompt_version,
                    "train_outputs": eval_payload["train_outputs"],
                    "eval_outputs": eval_payload["eval_outputs"],
                    "rationale": eval_payload["rationale"],
                },
            }
            candidates.append(candidate)
            if len(candidates) >= self._config.refinement_candidates:
                break

        summary = {
            "lane": self.module_name,
            "prompt_version": self._prompt_version,
            "selected_operations": [candidate["metadata"]["operation"] for candidate in candidates],
            "top_probability": candidates[0]["metadata"]["probability"] if candidates else None,
        }
        task_context.cache_namespace["candidates"] = candidates
        task_context.cache_namespace["llm_summary"] = summary
        status = ModuleSolveStatus.SUCCESS if candidates else ModuleSolveStatus.PARTIAL
        return ModuleResult(
            task_id=task_context.task_id,
            status=status,
            candidates=candidates,
            summary=summary,
        )

    def _on_shutdown(self, context: ModuleContext) -> None:
        if self._model is not None:
            del self._model
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
        context.logger.debug("LLM module teardown complete.")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _resolve_device(self, label: str) -> torch.device:
        if label.startswith("cuda") and torch.cuda.is_available():
            try:
                index = int(label.split(":")[1])
            except (IndexError, ValueError):
                index = 0
            if index < torch.cuda.device_count():
                return torch.device(f"cuda:{index}")
            if torch.cuda.device_count() > 0:
                return torch.device("cuda:0")
        return torch.device("cpu")

    def _ensure_assets_exist(self) -> None:
        if self._model_path.exists():
            return
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        operations = [
            "identity",
            "rotate90",
            "rotate180",
            "rotate270",
            "mirror_horizontal",
            "mirror_vertical",
            "transpose",
            "invert_palette",
            "fill_majority_input",
            "fill_majority_output",
            "outline_preserve",
            "shift_right",
            "shift_down",
        ]
        feature_dim = self._feature_dim
        hidden_dim = 64
        model = ArcLLMModel(input_dim=feature_dim, hidden_dim=hidden_dim, num_operations=len(operations))
        torch.manual_seed(1337)
        for param in model.parameters():
            if param.dim() >= 2:
                nn.init.xavier_uniform_(param)
            else:
                nn.init.zeros_(param)
        payload = {
            "model_state": model.state_dict(),
            "operations": operations,
            "feature_dim": feature_dim,
            "hidden_dim": hidden_dim,
            "feature_mean": [0.0] * feature_dim,
            "feature_std": [1.0] * feature_dim,
        }
        torch.save(payload, self._model_path)

    def _compute_task_features(self, train_examples: Sequence[Mapping[str, Any]]) -> Tensor:
        feature_vectors: List[np.ndarray] = []
        for example in train_examples:
            input_grid = self._grid_to_array(example.get("input"))
            output_grid = self._grid_to_array(example.get("output"))
            if input_grid is None:
                continue
            feature_vectors.append(self._extract_features(input_grid, output_grid))
        if not feature_vectors:
            features = np.zeros(self._feature_dim, dtype=np.float32)
        else:
            features = np.mean(feature_vectors, axis=0)
        tensor = torch.tensor(features, dtype=torch.float32, device=self._device)
        if self._feature_mean is not None and self._feature_std is not None:
            tensor = (tensor - self._feature_mean) / self._feature_std
        return tensor

    def _extract_features(self, input_grid: np.ndarray, output_grid: Optional[np.ndarray]) -> np.ndarray:
        rows, cols = input_grid.shape
        feature = np.zeros(self._feature_dim, dtype=np.float32)
        feature[0] = rows / 30.0
        feature[1] = cols / 30.0
        feature[2] = (output_grid.shape[0] / 30.0) if output_grid is not None else feature[0]
        feature[3] = (output_grid.shape[1] / 30.0) if output_grid is not None else feature[1]
        feature[4] = self._palette_entropy(input_grid)
        feature[5] = self._palette_entropy(output_grid) if output_grid is not None else 0.0
        feature[6] = self._unique_ratio(input_grid)
        feature[7] = self._unique_ratio(output_grid) if output_grid is not None else 0.0
        feature[8] = self._symmetry_score(input_grid, axis=0)
        feature[9] = self._symmetry_score(input_grid, axis=1)
        feature[10] = self._symmetry_score(output_grid, axis=0) if output_grid is not None else 0.0
        feature[11] = self._symmetry_score(output_grid, axis=1) if output_grid is not None else 0.0
        feature[12] = self._colour_difference(input_grid, output_grid)
        feature[13] = float(np.mean(input_grid)) / 9.0
        feature[14] = float(np.mean(output_grid)) / 9.0 if output_grid is not None else feature[13]
        feature[15] = float(np.var(input_grid)) / 25.0
        feature[16] = float(np.var(output_grid)) / 25.0 if output_grid is not None else feature[15]
        feature[17] = float(self._foreground_density(input_grid))
        feature[18] = float(self._foreground_density(output_grid)) if output_grid is not None else feature[17]
        feature[19] = float(self._bounding_box_ratio(input_grid))
        feature[20] = float(self._bounding_box_ratio(output_grid)) if output_grid is not None else feature[19]
        feature[21] = (rows == cols)
        feature[22] = float(np.count_nonzero(input_grid)) / (rows * cols)
        feature[23] = float(np.count_nonzero(output_grid)) / (output_grid.size) if output_grid is not None else feature[22]
        feature[24] = float(self._colour_match_score(input_grid, output_grid))
        feature[25] = float(self._edge_similarity(input_grid, output_grid))
        feature[26] = float(self._background_colour(input_grid))
        feature[27] = float(self._background_colour(output_grid)) if output_grid is not None else feature[26]
        feature[28] = float(np.argmax(np.bincount(input_grid.flatten(), minlength=10)))
        feature[29] = float(np.argmax(np.bincount(output_grid.flatten(), minlength=10))) if output_grid is not None else feature[28]
        feature[30] = float(np.count_nonzero(input_grid == self._background_colour(input_grid))) / (rows * cols)
        feature[31] = float(np.count_nonzero(output_grid == self._background_colour(output_grid))) / (output_grid.size) if output_grid is not None else feature[30]
        return feature

    def _palette_entropy(self, grid: Optional[np.ndarray]) -> float:
        if grid is None:
            return 0.0
        values, counts = np.unique(grid, return_counts=True)
        probs = counts / counts.sum()
        entropy = -np.sum(probs * np.log2(probs + 1e-9))
        return float(entropy / math.log2(10))

    def _unique_ratio(self, grid: Optional[np.ndarray]) -> float:
        if grid is None or grid.size == 0:
            return 0.0
        return float(len(np.unique(grid)) / 10.0)

    def _symmetry_score(self, grid: Optional[np.ndarray], axis: int) -> float:
        if grid is None:
            return 0.0
        if axis == 0:
            flipped = np.flipud(grid)
        else:
            flipped = np.fliplr(grid)
        return float(np.mean(grid == flipped))

    def _colour_difference(self, input_grid: np.ndarray, output_grid: Optional[np.ndarray]) -> float:
        if output_grid is None or input_grid.shape != output_grid.shape:
            return 0.0
        return float(np.mean(input_grid == output_grid))

    def _foreground_density(self, grid: Optional[np.ndarray]) -> float:
        if grid is None or grid.size == 0:
            return 0.0
        background = self._background_colour(grid)
        return float(np.count_nonzero(grid != background)) / float(grid.size)

    def _bounding_box_ratio(self, grid: Optional[np.ndarray]) -> float:
        if grid is None or grid.size == 0:
            return 0.0
        rows = np.any(grid != self._background_colour(grid), axis=1)
        cols = np.any(grid != self._background_colour(grid), axis=0)
        if not rows.any() or not cols.any():
            return 0.0
        height = rows.sum()
        width = cols.sum()
        total = grid.shape[0] * grid.shape[1]
        return float(height * width) / float(total)

    def _colour_match_score(self, input_grid: np.ndarray, output_grid: Optional[np.ndarray]) -> float:
        if output_grid is None:
            return 0.0
        counts_input = np.bincount(input_grid.flatten(), minlength=10)
        counts_output = np.bincount(output_grid.flatten(), minlength=10)
        total = counts_input.sum() + counts_output.sum()
        if total == 0:
            return 0.0
        return float(np.minimum(counts_input, counts_output).sum()) / float(max(1, counts_output.sum()))

    def _edge_similarity(self, input_grid: np.ndarray, output_grid: Optional[np.ndarray]) -> float:
        if output_grid is None:
            return 0.0
        top_match = np.mean(input_grid[0, :] == output_grid[0, :]) if input_grid.shape[0] > 0 and output_grid.shape[0] > 0 else 0.0
        left_match = np.mean(input_grid[:, 0] == output_grid[:, 0]) if input_grid.shape[1] > 0 and output_grid.shape[1] > 0 else 0.0
        return float((top_match + left_match) / 2.0)

    def _background_colour(self, grid: Optional[np.ndarray]) -> int:
        if grid is None or grid.size == 0:
            return 0
        counts = np.bincount(grid.flatten(), minlength=10)
        return int(np.argmax(counts))

    def _build_operation_context(self, train_examples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        palette_input: Counter[int] = Counter()
        palette_output: Counter[int] = Counter()
        for example in train_examples:
            input_grid = self._grid_to_array(example.get("input"))
            output_grid = self._grid_to_array(example.get("output"))
            if input_grid is not None:
                palette_input.update(input_grid.flatten().tolist())
            if output_grid is not None:
                palette_output.update(output_grid.flatten().tolist())
        context["majority_input_colour"] = palette_input.most_common(1)[0][0] if palette_input else 0
        context["majority_output_colour"] = palette_output.most_common(1)[0][0] if palette_output else context["majority_input_colour"]
        context["background_colour"] = context["majority_input_colour"]
        context["train_outputs"] = [self._grid_to_list(example.get("output")) for example in train_examples]
        return context

    def _evaluate_operation(
        self,
        *,
        operation: str,
        train_examples: Sequence[Mapping[str, Any]],
        eval_examples: Sequence[Mapping[str, Any]],
        context: Mapping[str, Any],
    ) -> Dict[str, Any]:
        train_outputs: List[Dict[str, Any]] = []
        eval_outputs: List[Dict[str, Any]] = []
        matches = 0
        total = 0
        for index, example in enumerate(train_examples):
            predicted = self._apply_operation(operation, example.get("input"), context)
            expected = example.get("output")
            train_outputs.append({"index": index, "grid": predicted, "confidence": 1.0 if predicted is not None else 0.0})
            if predicted is not None and expected is not None and self._grids_equal(predicted, expected):
                matches += 1
            total += 1
        for index, example in enumerate(eval_examples):
            predicted = self._apply_operation(operation, example.get("input"), context)
            eval_outputs.append({"index": index, "grid": predicted, "confidence": 1.0 if predicted is not None else 0.0})
        accuracy = float(matches) / float(max(1, total))
        rationale = f"operation={operation}, train_accuracy={accuracy:.2f}"
        return {
            "train_outputs": train_outputs,
            "eval_outputs": eval_outputs,
            "train_accuracy": accuracy,
            "rationale": rationale,
        }

    def _apply_operation(self, operation: str, grid: Any, context: Mapping[str, Any]) -> Optional[List[List[int]]]:
        array = self._grid_to_array(grid)
        if array is None:
            return None
        background = int(context.get("background_colour", self._background_colour(array)))
        if operation == "identity":
            result = array
        elif operation == "rotate90":
            result = np.rot90(array, -1)
        elif operation == "rotate180":
            result = np.rot90(array, 2)
        elif operation == "rotate270":
            result = np.rot90(array, 1)
        elif operation == "mirror_horizontal":
            result = np.fliplr(array)
        elif operation == "mirror_vertical":
            result = np.flipud(array)
        elif operation == "transpose":
            result = array.transpose()
        elif operation == "invert_palette":
            result = (9 - array) % 10
        elif operation == "fill_majority_input":
            colour = int(context.get("majority_input_colour", background))
            result = np.full_like(array, colour)
        elif operation == "fill_majority_output":
            colour = int(context.get("majority_output_colour", background))
            result = np.full_like(array, colour)
        elif operation == "outline_preserve":
            result = np.full_like(array, background)
            if array.shape[0] > 0:
                result[0, :] = array[0, :]
                result[-1, :] = array[-1, :]
            if array.shape[1] > 0:
                result[:, 0] = array[:, 0]
                result[:, -1] = array[:, -1]
        elif operation == "shift_right":
            result = np.full_like(array, background)
            result[:, 1:] = array[:, :-1]
        elif operation == "shift_down":
            result = np.full_like(array, background)
            result[1:, :] = array[:-1, :]
        else:
            return None
        return result.astype(int).tolist()

    def _blend_confidence(self, probability: float, accuracy: float) -> float:
        return float(0.6 * probability + 0.4 * accuracy)

    def _grid_to_array(self, grid: Any) -> Optional[np.ndarray]:
        if grid is None:
            return None
        if isinstance(grid, np.ndarray):
            return grid.astype(np.int16, copy=True)
        if isinstance(grid, torch.Tensor):
            return grid.detach().cpu().numpy().astype(np.int16)
        if isinstance(grid, Iterable):
            rows: List[List[int]] = []
            for row in grid:
                if not isinstance(row, Iterable):
                    return None
                rows.append([int(value) for value in row])
            if not rows:
                return None
            try:
                return np.array(rows, dtype=np.int16)
            except ValueError:
                return None
        return None

    def _grid_to_list(self, grid: Any) -> Optional[List[List[int]]]:
        array = self._grid_to_array(grid)
        if array is None:
            return None
        return array.astype(int).tolist()

    def _grids_equal(self, left: Any, right: Any) -> bool:
        left_array = self._grid_to_array(left)
        right_array = self._grid_to_array(right)
        if left_array is None or right_array is None:
            return False
        return left_array.shape == right_array.shape and np.array_equal(left_array, right_array)
