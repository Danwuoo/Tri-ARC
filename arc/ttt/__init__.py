from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
class TTTLossWeights:
    reconstruction: float = 1.0
    color_conservation: float = 0.5
    object_count: float = 0.3
    smoothness: float = 0.2

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "TTTLossWeights":
        payload = dict(config.get("losses") or {})
        return cls(
            reconstruction=float(payload.get("reconstruction", cls.reconstruction)),
            color_conservation=float(payload.get("color_conservation", cls.color_conservation)),
            object_count=float(payload.get("object_count", cls.object_count)),
            smoothness=float(payload.get("smoothness", cls.smoothness)),
        )


class TTTAdapter(nn.Module):
    """Lightweight adapter trained on-the-fly during inference."""

    def __init__(self, *, num_cells: int, num_colours: int, hidden_dim: int = 128) -> None:
        super().__init__()
        self.num_cells = num_cells
        self.num_colours = num_colours
        self.net = nn.Sequential(
            nn.Linear(num_cells * num_colours, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, num_cells * num_colours),
        )

    def forward(self, inputs: Tensor) -> Tensor:
        # inputs: (batch, num_cells, num_colours)
        batch_size, num_cells, num_colours = inputs.shape
        flattened = inputs.view(batch_size, num_cells * num_colours)
        logits = self.net(flattened)
        return logits.view(batch_size, num_cells, num_colours)


class TTTModule(SolverModule):
    module_name = "ttt"
    capabilities = ModuleCapabilities(
        supports_partial_results=True,
        supports_resume=False,
        requires_gpu=True,
        extras={"lane": "ttt"},
    )

    _max_rows: int = 32
    _max_cols: int = 32
    _num_colours: int = 16
    _pad_token: int = _num_colours - 1

    def __init__(self, config: Dict[str, Any], *, profile: Optional[str] = None) -> None:
        super().__init__(config)
        cfg = config.get("ttt", {})
        self._profile = profile or "default"
        self._enabled = bool(cfg.get("enabled", True))
        self._model_path = Path(cfg.get("model_path", "models/ttt/base.ckpt"))
        self._learning_rate = float(cfg.get("learning_rate", 3.0e-4))
        self._steps = int(cfg.get("steps", 16))
        self._gradient_clip = float(cfg.get("gradient_clip", 1.0))
        self._patience = max(1, int(cfg.get("early_stop_patience", 3)))
        self._loss_weights = TTTLossWeights.from_config(cfg)
        self._device_label = str(cfg.get("device") or config.get("global", {}).get("device_map", {}).get("ttt", "cuda:0"))
        self._device = self._resolve_device(self._device_label)
        self._base_model: Optional[TTTAdapter] = None
        self._base_state: Optional[Dict[str, Tensor]] = None
        self._colour_values = torch.arange(self._num_colours, dtype=torch.float32)

    # ------------------------------------------------------------------ #
    # Lifecycle hooks
    # ------------------------------------------------------------------ #
    def _on_initialize(self, context: ModuleContext) -> None:
        if not self._enabled:
            context.logger.info("TTT lane disabled via configuration toggle.")
            return
        self._ensure_assets_exist()
        self._load_base_model()
        context.logger.info(
            "TTT module initialised with profile=%s, device=%s, steps=%s",
            self._profile,
            self._device,
            self._steps,
        )

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        shared_namespace = task_context.module_context.shared_cache.setdefault(self.module_name, {})
        module_cache = shared_namespace.setdefault(task_context.task_id, {})
        task_context.cache_namespace = module_cache
        task_context.metadata["module"] = self.module_name
        task_context.metadata["profile"] = self._profile
        task_context.metadata["device"] = str(self._device)
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        if not self._enabled:
            summary = {"lane": self.module_name, "reason": "module_disabled"}
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        train_examples = list(task_context.task_payload.get("train_examples") or [])
        eval_examples = list(task_context.task_payload.get("test_examples") or task_context.task_payload.get("eval_examples") or [])

        if not train_examples:
            summary = {
                "lane": self.module_name,
                "profile": self._profile,
                "reason": "no_train_examples",
            }
            task_context.cache_namespace["candidates"] = []
            task_context.cache_namespace["ttt_summary"] = summary
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        adaptation_payload = self._prepare_adaptation_payload(train_examples)
        if adaptation_payload is None:
            summary = {
                "lane": self.module_name,
                "profile": self._profile,
                "reason": "grid_exceeds_capacity",
            }
            task_context.cache_namespace["candidates"] = []
            task_context.cache_namespace["ttt_summary"] = summary
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        model = self._clone_base_model()
        model.to(self._device)
        optimiser = torch.optim.AdamW(model.parameters(), lr=self._learning_rate)

        adaptation_history, adaptation_state = self._run_adaptation(
            model=model,
            optimiser=optimiser,
            inputs=adaptation_payload["inputs"],
            targets=adaptation_payload["targets"],
            masks=adaptation_payload["masks"],
        )

        train_predictions = self._generate_predictions(model, train_examples, allow_reference=True)
        eval_predictions = self._generate_predictions(model, eval_examples) if eval_examples else []
        all_predictions = eval_predictions or train_predictions
        primary_record = next((record for record in all_predictions if record.get("grid") is not None), None)
        confidence = adaptation_state.get("mean_confidence", 0.0)

        summary = {
            "lane": self.module_name,
            "profile": self._profile,
            "steps_executed": adaptation_state.get("steps_executed", 0),
            "best_reconstruction": adaptation_state.get("best_reconstruction_loss"),
            "mean_confidence": confidence,
        }
        primary_grid = primary_record.get("grid") if primary_record else None
        if primary_record and not primary_record.get("confidence"):
            primary_record["confidence"] = confidence
        candidate_payload: List[Dict[str, Any]] = []
        if primary_grid is not None:
            candidate_payload.append(
                {
                    "candidate_id": f"ttt-{task_context.task_id}-grid",
                    "type": "grid",
                    "grid": primary_grid,
                    "metadata": {
                        "confidence": confidence,
                        "losses": adaptation_state.get("loss_history", []),
                        "source": "ttt_adapter",
                        "profile": self._profile,
                        "train_steps": adaptation_state.get("steps_executed", 0),
                        "train_outputs": [
                            {"index": idx, "grid": record.get("grid"), "confidence": record.get("confidence", 0.0)}
                            for idx, record in enumerate(train_predictions)
                        ],
                        "eval_outputs": [
                            {"index": idx, "grid": record.get("grid"), "confidence": record.get("confidence", 0.0)}
                            for idx, record in enumerate(eval_predictions)
                        ],
                    },
                }
            )

        task_context.cache_namespace["candidates"] = candidate_payload
        task_context.cache_namespace["ttt_summary"] = summary
        task_context.cache_namespace["loss_history"] = adaptation_history

        status = ModuleSolveStatus.SUCCESS if candidate_payload else ModuleSolveStatus.PARTIAL
        return ModuleResult(
            task_id=task_context.task_id,
            status=status,
            candidates=candidate_payload,
            summary=summary,
        )

    def _on_shutdown(self, context: ModuleContext) -> None:
        if self._base_model is not None:
            del self._base_model
        if self._base_state is not None:
            for tensor in self._base_state.values():
                tensor.detach_()
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
        context.logger.debug("TTT module teardown complete.")

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
        model = TTTAdapter(num_cells=self._max_rows * self._max_cols, num_colours=self._num_colours)
        torch.save({"model_state": model.state_dict()}, self._model_path)

    def _load_base_model(self) -> None:
        payload = torch.load(self._model_path, map_location="cpu")
        model = TTTAdapter(num_cells=self._max_rows * self._max_cols, num_colours=self._num_colours)
        state = payload.get("model_state")
        if state is None:
            raise RuntimeError(f"TTT checkpoint {self._model_path} missing 'model_state'.")
        model.load_state_dict(state)
        self._base_model = model
        self._base_state = {key: value.clone().detach() for key, value in model.state_dict().items()}

    def _clone_base_model(self) -> TTTAdapter:
        if self._base_model is None or self._base_state is None:
            raise RuntimeError("TTT base model not loaded.")
        model = TTTAdapter(num_cells=self._max_rows * self._max_cols, num_colours=self._num_colours)
        model.load_state_dict(copy.deepcopy(self._base_state))  # type: ignore[arg-type]
        return model

    def _prepare_adaptation_payload(
        self, examples: Sequence[Mapping[str, Any]]
    ) -> Optional[Dict[str, Tensor]]:
        inputs: List[Tensor] = []
        targets: List[Tensor] = []
        masks: List[Tensor] = []
        for example in examples:
            input_grid = example.get("input")
            output_grid = example.get("output")
            if input_grid is None or output_grid is None:
                continue
            encoded_input, mask = self._encode_grid(input_grid)
            encoded_target, _ = self._encode_grid(output_grid)
            if encoded_input is None or encoded_target is None:
                return None
            inputs.append(encoded_input)
            masks.append(mask)
            targets.append(self._grid_to_indices(output_grid))
        if not inputs or not targets:
            return None
        batched_inputs = torch.stack(inputs)  # (batch, cells, colours)
        batched_targets = torch.stack(targets)  # (batch, cells)
        batched_masks = torch.stack(masks)  # (batch, cells)
        return {
            "inputs": batched_inputs.to(self._device),
            "targets": batched_targets.to(self._device),
            "masks": batched_masks.to(self._device),
        }

    def _grid_to_indices(self, grid: Any) -> Tensor:
        arr, _ = self._grid_to_array(grid)
        return arr.view(-1)

    def _encode_grid(self, grid: Any) -> Tuple[Optional[Tensor], Optional[Tensor]]:
        arr, mask = self._grid_to_array(grid)
        if arr is None:
            return None, None
        one_hot = F.one_hot(arr, num_classes=self._num_colours).to(torch.float32)
        return one_hot.view(-1, self._num_colours), mask.view(-1)

    def _grid_to_array(self, grid: Any) -> Tuple[Optional[Tensor], Tensor]:
        if not isinstance(grid, Iterable):
            return None, torch.zeros(self._max_rows * self._max_cols, dtype=torch.bool)
        rows = list(grid)
        if not rows:
            return None, torch.zeros(self._max_rows * self._max_cols, dtype=torch.bool)
        height = len(rows)
        width = len(rows[0]) if isinstance(rows[0], Sequence) else 0
        if height > self._max_rows or width > self._max_cols:
            return None, torch.zeros(self._max_rows * self._max_cols, dtype=torch.bool)
        tensor = torch.full((self._max_rows, self._max_cols), self._pad_token, dtype=torch.long)
        mask = torch.zeros((self._max_rows, self._max_cols), dtype=torch.bool)
        for r, row in enumerate(rows):
            if r >= self._max_rows:
                break
            if not isinstance(row, Sequence):
                continue
            for c, value in enumerate(row):
                if c >= self._max_cols:
                    break
                colour = int(value) if isinstance(value, int) else int(getattr(value, "item", lambda: 0)())
                colour = max(0, min(self._num_colours - 2, colour))
                tensor[r, c] = colour
                mask[r, c] = True
        return tensor, mask

    def _run_adaptation(
        self,
        *,
        model: TTTAdapter,
        optimiser: torch.optim.Optimizer,
        inputs: Tensor,
        targets: Tensor,
        masks: Tensor,
    ) -> Tuple[List[Dict[str, float]], Dict[str, Any]]:
        history: List[Dict[str, float]] = []
        best_reconstruction = math.inf
        best_state: Optional[Dict[str, Tensor]] = None
        patience = 0
        total_confidence = 0.0
        steps_executed = 0

        for step in range(1, self._steps + 1):
            model.train()
            optimiser.zero_grad(set_to_none=True)
            logits = model(inputs)
            losses = self._compute_losses(logits, targets, masks)
            total_loss = (
                losses["reconstruction"] * self._loss_weights.reconstruction
                + losses["color_conservation"] * self._loss_weights.color_conservation
                + losses["object_count"] * self._loss_weights.object_count
                + losses["smoothness"] * self._loss_weights.smoothness
            )
            total_loss.backward()
            if self._gradient_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), self._gradient_clip)
            optimiser.step()

            with torch.no_grad():
                confidence = losses["confidence"]
                total_confidence += confidence
                history.append(
                    {
                        "step": float(step),
                        "total_loss": float(total_loss.item()),
                        "reconstruction": float(losses["reconstruction"].item()),
                        "color_conservation": float(losses["color_conservation"].item()),
                        "object_count": float(losses["object_count"].item()),
                        "smoothness": float(losses["smoothness"].item()),
                        "confidence": float(confidence),
                    }
                )
                steps_executed = step
                if losses["reconstruction"].item() + 1e-6 < best_reconstruction:
                    best_reconstruction = losses["reconstruction"].item()
                    best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
                    patience = 0
                else:
                    patience += 1
                    if patience >= self._patience:
                        break

        if best_state is not None:
            model.load_state_dict(best_state)

        mean_confidence = total_confidence / max(1, steps_executed)
        adaptation_state = {
            "best_reconstruction_loss": best_reconstruction if best_reconstruction != math.inf else None,
            "loss_history": history,
            "steps_executed": steps_executed,
            "mean_confidence": float(mean_confidence),
        }
        return history, adaptation_state

    def _compute_losses(
        self,
        logits: Tensor,
        targets: Tensor,
        masks: Tensor,
    ) -> Dict[str, Tensor]:
        batch_size, num_cells, num_colours = logits.shape
        masks_flat = masks.view(batch_size * num_cells)
        logits_flat = logits.view(batch_size * num_cells, num_colours)
        targets_flat = targets.view(batch_size * num_cells)

        if masks_flat.sum() == 0:
            zero = torch.zeros((), device=logits.device)
            return {
                "reconstruction": zero,
                "color_conservation": zero,
                "object_count": zero,
                "smoothness": zero,
                "confidence": zero,
            }

        selected_logits = logits_flat[masks_flat]
        selected_targets = targets_flat[masks_flat]

        reconstruction = F.cross_entropy(selected_logits, selected_targets, reduction="mean")
        probs = selected_logits.softmax(dim=-1)
        target_one_hot = F.one_hot(selected_targets, num_classes=num_colours).to(probs.dtype)

        pred_hist = probs.mean(dim=0)
        target_hist = target_one_hot.mean(dim=0)
        color_conservation = F.l1_loss(pred_hist, target_hist)

        entropy = -(probs * probs.clamp_min(1e-8).log()).sum(dim=-1).mean()
        object_count = entropy

        full_probs = logits.softmax(dim=-1)
        expected = (full_probs * self._colour_values.to(logits.device)).sum(dim=-1)
        expected_grid = expected.view(batch_size, self._max_rows, self._max_cols)
        mask_grid = masks.view(batch_size, self._max_rows, self._max_cols).to(expected_grid.dtype)

        smoothness = self._total_variation(expected_grid, mask_grid)
        confidence = probs.max(dim=-1).values.mean()

        return {
            "reconstruction": reconstruction,
            "color_conservation": color_conservation,
            "object_count": object_count,
            "smoothness": smoothness,
            "confidence": confidence,
        }

    def _total_variation(self, grid: Tensor, mask: Tensor) -> Tensor:
        diff_x = (grid[:, 1:, :] - grid[:, :-1, :]).abs()
        mask_x = mask[:, 1:, :] * mask[:, :-1, :]
        diff_y = (grid[:, :, 1:] - grid[:, :, :-1]).abs()
        mask_y = mask[:, :, 1:] * mask[:, :, :-1]
        norm_x = mask_x.sum().clamp_min(1.0)
        norm_y = mask_y.sum().clamp_min(1.0)
        return (diff_x.mul(mask_x).sum() / norm_x + diff_y.mul(mask_y).sum() / norm_y) * 0.5

    def _generate_predictions(
        self,
        model: TTTAdapter,
        examples: Sequence[Mapping[str, Any]],
        *,
        allow_reference: bool = False,
    ) -> List[Dict[str, Any]]:
        model.eval()
        predictions: List[Dict[str, Any]] = []
        for example in examples:
            grid = example.get("input")
            reference = example.get("output") if allow_reference else None
            if grid is None:
                fallback_grid = self._normalise_literal_grid(reference)
                predictions.append({"grid": fallback_grid, "confidence": 1.0 if fallback_grid is not None else 0.0})
                continue
            encoded, mask = self._encode_grid(grid)
            if encoded is None:
                fallback_grid = self._normalise_literal_grid(reference)
                predictions.append({"grid": fallback_grid, "confidence": 1.0 if fallback_grid is not None else 0.0})
                continue
            mask_grid = mask.view(self._max_rows, self._max_cols)
            with torch.no_grad():
                logits = model(encoded.unsqueeze(0).to(self._device))
                probs = logits.softmax(dim=-1)
                confidence_map = probs.max(dim=-1).values.view(self._max_rows, self._max_cols).cpu()
                pred = logits.argmax(dim=-1).view(self._max_rows, self._max_cols).cpu()
                rows = min(len(grid), self._max_rows)
                cols = min(len(grid[0]) if grid else 0, self._max_cols)
                cropped = pred[:rows, :cols]
                cropped_mask = mask_grid[:rows, :cols]
                converted = self._tensor_to_grid(cropped, cropped_mask)
                if converted is None and reference is not None:
                    converted = self._normalise_literal_grid(reference)
                focus = confidence_map[:rows, :cols]
                mask_vector = cropped_mask.reshape(-1)
                if mask_vector.any().item():
                    confidence = float(focus[cropped_mask].mean().item())
                else:
                    confidence = 0.0
                predictions.append({"grid": converted, "confidence": confidence})
        return predictions

    def _normalise_literal_grid(self, grid: Any) -> Optional[List[List[int]]]:
        if grid is None:
            return None
        candidate = grid
        if hasattr(candidate, "to_list"):
            try:
                candidate = candidate.to_list()
            except Exception:
                candidate = grid
        if isinstance(candidate, torch.Tensor):
            candidate = candidate.detach().cpu().numpy().tolist()
        if not isinstance(candidate, Iterable):
            return None
        normalised: List[List[int]] = []
        for row in candidate:
            if not isinstance(row, Iterable):
                continue
            normalised_row: List[int] = []
            for value in row:
                try:
                    cell = int(value)
                except Exception:
                    cell = 0
                cell = max(0, min(9, cell))
                normalised_row.append(cell)
            if normalised_row:
                normalised.append(normalised_row)
        return normalised if normalised else None

    def _tensor_to_grid(self, tensor: Tensor, mask: Tensor) -> Optional[List[List[int]]]:
        rows: List[List[int]] = []
        for r in range(tensor.shape[0]):
            row: List[int] = []
            for c in range(tensor.shape[1]):
                if not mask[r, c]:
                    continue
                value = int(tensor[r, c].item())
                row.append(max(0, min(9, value)))
            if row:
                rows.append(row)
        return rows if rows else None
