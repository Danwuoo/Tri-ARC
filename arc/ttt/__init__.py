from __future__ import annotations

import copy
import math
from dataclasses import dataclass
import random
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


@dataclass(frozen=True)
class TTTAugmentationConfig:
    enabled: bool = True
    max_copies: int = 2
    color_jitter: float = 0.2
    noise_probability: float = 0.03
    symmetry_ops: Tuple[str, ...] = ("identity", "hflip", "vflip", "transpose", "rot90")

    @classmethod
    def from_config(cls, config: Optional[Mapping[str, Any]]) -> "TTTAugmentationConfig":
        payload = dict(config or {})
        sym = payload.get("symmetry_ops") or payload.get("symmetries")
        if sym is None:
            symmetry_ops = cls.symmetry_ops
        else:
            symmetry_ops = tuple(str(op) for op in sym if isinstance(op, (str, bytes)))
            if not symmetry_ops:
                symmetry_ops = cls.symmetry_ops
        return cls(
            enabled=bool(payload.get("enabled", cls.enabled)),
            max_copies=max(0, int(payload.get("max_copies", cls.max_copies))),
            color_jitter=float(payload.get("color_jitter", cls.color_jitter)),
            noise_probability=float(payload.get("noise_probability", cls.noise_probability)),
            symmetry_ops=symmetry_ops,
        )


class TTTAdapter(nn.Module):
    """Convolutional + shallow self-attention adapter for TTT."""

    def __init__(
        self,
        *,
        grid_size: Tuple[int, int],
        num_colours: int,
        hidden_dim: int = 128,
        conv_channels: int = 64,
        num_heads: int = 4,
        attn_layers: int = 2,
    ) -> None:
        super().__init__()
        self.height, self.width = grid_size
        self.num_cells = self.height * self.width
        self.num_colours = num_colours
        self.hidden_dim = hidden_dim
        self.conv_channels = conv_channels
        self.num_heads = num_heads
        self.attn_layers = attn_layers
        self.stem = nn.Sequential(
            nn.Linear(num_colours, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
        )
        self.proj = nn.Conv2d(hidden_dim, conv_channels, kernel_size=1)
        self.residual_blocks = nn.ModuleList(
            [ResidualConvBlock(conv_channels) for _ in range(3)]
        )
        self.attention_layers = nn.ModuleList(
            [SelfAttentionLayer(conv_channels, num_heads=num_heads) for _ in range(max(1, attn_layers))]
        )
        self.head = nn.Sequential(
            nn.LayerNorm(conv_channels),
            nn.Linear(conv_channels, num_colours),
        )

    def forward(self, inputs: Tensor) -> Tensor:
        batch_size, num_cells, num_colours = inputs.shape
        if num_cells != self.num_cells or num_colours != self.num_colours:
            raise ValueError(f"Unexpected input shape: got {(batch_size, num_cells, num_colours)}, expected (_, {self.num_cells}, {self.num_colours}).")
        features = self.stem(inputs)  # (batch, cells, hidden_dim)
        grid = features.view(batch_size, self.height, self.width, self.hidden_dim).permute(0, 3, 1, 2)
        grid = self.proj(grid)
        for block in self.residual_blocks:
            grid = block(grid)
        seq = grid.flatten(2).transpose(1, 2)  # (batch, cells, channels)
        for attn in self.attention_layers:
            seq = attn(seq)
        logits = self.head(seq)
        return logits


class ResidualConvBlock(nn.Module):
    """Simple residual 3x3 convolution block."""

    def __init__(self, channels: int, dropout: float = 0.0) -> None:
        super().__init__()
        layers: List[nn.Module] = [
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
            nn.GroupNorm(1, channels),  # GroupNorm is stable for tiny adaptation batches
            nn.GELU(),
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
            nn.GroupNorm(1, channels),
        ]
        self.net = nn.Sequential(*layers)
        self.dropout = nn.Dropout2d(dropout) if dropout > 0 else None

    def forward(self, inputs: Tensor) -> Tensor:
        out = self.net(inputs)
        if self.dropout is not None:
            out = self.dropout(out)
        return inputs + out


class SelfAttentionLayer(nn.Module):
    """Lightweight self-attention encoder block."""

    def __init__(self, dim: int, *, num_heads: int = 4) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = nn.Sequential(
            nn.Linear(dim, dim * 4),
            nn.GELU(),
            nn.Linear(dim * 4, dim),
        )

    def forward(self, inputs: Tensor) -> Tensor:
        residual = inputs
        normed = self.norm1(inputs)
        attn_out, _ = self.attn(normed, normed, normed, need_weights=False)
        x = residual + attn_out
        x = x + self.mlp(self.norm2(x))
        return x


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
        self._grid_size = (self._max_rows, self._max_cols)
        self._base_model: Optional[TTTAdapter] = None
        self._base_state: Optional[Dict[str, Tensor]] = None
        self._colour_values = torch.arange(self._num_colours, dtype=torch.float32)
        adapter_cfg = dict(cfg.get("adapter") or {})
        self._adapter_kwargs = {
            "grid_size": self._grid_size,
            "num_colours": self._num_colours,
            "hidden_dim": int(adapter_cfg.get("hidden_dim", 128)),
            "conv_channels": int(adapter_cfg.get("conv_channels", 64)),
            "num_heads": int(adapter_cfg.get("num_heads", 4)),
            "attn_layers": int(adapter_cfg.get("attn_layers", 2)),
        }
        self._augmentation = TTTAugmentationConfig.from_config(cfg.get("augmentation"))
        seed = cfg.get("seed")
        self._rng = random.Random(int(seed) if seed is not None else 0xA77AA)
        self._loss_failure_threshold = float(cfg.get("loss_failure_threshold", 1.0))
        self._loss_dropout_threshold = float(cfg.get("loss_dropout_threshold", 2.0))
        self._min_confidence = float(cfg.get("min_confidence", 0.05))

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
            augmented_examples=int(adaptation_payload.get("augmented_examples", 0)),
        )

        train_predictions = self._generate_predictions(model, train_examples, allow_reference=True)
        eval_predictions = self._generate_predictions(model, eval_examples) if eval_examples else []
        all_predictions = eval_predictions or train_predictions
        primary_record = next((record for record in all_predictions if record.get("grid") is not None), None)
        base_confidence = adaptation_state.get("mean_confidence", 0.0)
        best_loss = adaptation_state.get("best_reconstruction_loss")
        adjusted_confidence = self._loss_adjusted_confidence(base_confidence, best_loss)
        if not adaptation_state.get("converged", False):
            adjusted_confidence = max(self._min_confidence, adjusted_confidence * 0.5)
        drop_due_to_loss = self._should_drop_candidate(best_loss)

        summary = {
            "lane": self.module_name,
            "profile": self._profile,
            "strategy": "ttt_model",
            "steps_executed": adaptation_state.get("steps_executed", 0),
            "best_reconstruction": best_loss,
            "mean_confidence": base_confidence,
            "loss_adjusted_confidence": adjusted_confidence,
            "augmented_examples": adaptation_state.get("augmented_examples", 0),
            "converged": adaptation_state.get("converged", False),
        }
        primary_grid = primary_record.get("grid") if primary_record else None
        if primary_record and not primary_record.get("confidence"):
            primary_record["confidence"] = adjusted_confidence
        train_outputs = []
        for idx, record in enumerate(train_predictions):
            payload = {
                "index": idx,
                "grid": record.get("grid"),
                "confidence": record.get("confidence", 0.0),
            }
            if idx < len(train_examples):
                example = train_examples[idx]
                if "id" in example:
                    payload["example_id"] = example["id"]
            train_outputs.append(payload)
        eval_outputs = []
        for idx, record in enumerate(eval_predictions):
            payload = {
                "index": idx,
                "grid": record.get("grid"),
                "confidence": record.get("confidence", 0.0),
            }
            if idx < len(eval_examples):
                example = eval_examples[idx]
                if "id" in example:
                    payload["example_id"] = example["id"]
            eval_outputs.append(payload)

        metadata_loss_summary = {
            "best_reconstruction": best_loss,
            "converged": adaptation_state.get("converged", False),
            "mean_confidence": base_confidence,
            "adjusted_confidence": adjusted_confidence,
            "augmented_examples": adaptation_state.get("augmented_examples", 0),
            "loss_thresholds": {
                "deprioritise": self._loss_failure_threshold,
                "drop": self._loss_dropout_threshold,
            },
        }
        candidate_payload: List[Dict[str, Any]] = []
        drop_reason: Optional[str] = None
        if drop_due_to_loss:
            drop_reason = "loss_not_converged"
        elif primary_grid is None:
            drop_reason = "missing_primary_grid"
        else:
            candidate_payload.append(
                {
                    "candidate_id": f"ttt-{task_context.task_id}-grid",
                    "type": "grid",
                    "grid": primary_grid,
                    "metadata": {
                        "confidence": adjusted_confidence,
                        "strategy": "ttt_model",
                        "losses": adaptation_state.get("loss_history", []),
                        "loss_summary": metadata_loss_summary,
                        "source": "ttt_adapter",
                        "profile": self._profile,
                        "train_steps": adaptation_state.get("steps_executed", 0),
                        "augmented_examples": adaptation_state.get("augmented_examples", 0),
                        "train_outputs": train_outputs,
                        "eval_outputs": eval_outputs,
                        "verification_ready": True,
                    },
                }
            )
        if drop_reason:
            summary["reason"] = drop_reason

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
        model = TTTAdapter(**self._adapter_kwargs)
        torch.save({"model_state": model.state_dict()}, self._model_path)

    def _load_base_model(self) -> None:
        payload = torch.load(self._model_path, map_location="cpu")
        model = TTTAdapter(**self._adapter_kwargs)
        state = payload.get("model_state")
        if state is None:
            raise RuntimeError(f"TTT checkpoint {self._model_path} missing 'model_state'.")
        try:
            model.load_state_dict(state)
        except RuntimeError:
            # Shape changed between versions; reset checkpoint.
            torch.save({"model_state": model.state_dict()}, self._model_path)
        self._base_model = model
        self._base_state = {key: value.clone().detach() for key, value in model.state_dict().items()}

    def _clone_base_model(self) -> TTTAdapter:
        if self._base_model is None or self._base_state is None:
            raise RuntimeError("TTT base model not loaded.")
        model = TTTAdapter(**self._adapter_kwargs)
        model.load_state_dict(copy.deepcopy(self._base_state))  # type: ignore[arg-type]
        return model

    def _prepare_adaptation_payload(
        self, examples: Sequence[Mapping[str, Any]]
    ) -> Optional[Dict[str, Tensor]]:
        records: List[Tuple[Tensor, Tensor, Tensor]] = []
        augmented_pairs = 0
        for example in examples:
            input_grid = example.get("input")
            output_grid = example.get("output")
            if input_grid is None or output_grid is None:
                continue
            encoded_input, mask = self._encode_grid(input_grid)
            encoded_target, _ = self._encode_grid(output_grid)
            if encoded_input is None or encoded_target is None:
                return None
            records.append((encoded_input, self._grid_to_indices(output_grid), mask))

            for aug_input, aug_output in self._augment_example(input_grid, output_grid):
                encoded_aug_input, aug_mask = self._encode_grid(aug_input)
                encoded_aug_target, _ = self._encode_grid(aug_output)
                if encoded_aug_input is None or encoded_aug_target is None or aug_mask is None:
                    continue
                records.append((encoded_aug_input, self._grid_to_indices(aug_output), aug_mask))
                augmented_pairs += 1
        if not records:
            return None
        inputs, targets, masks = zip(*records)
        batched_inputs = torch.stack(inputs)
        batched_targets = torch.stack(targets)
        batched_masks = torch.stack(masks)
        return {
            "inputs": batched_inputs.to(self._device),
            "targets": batched_targets.to(self._device),
            "masks": batched_masks.to(self._device),
            "augmented_examples": augmented_pairs,
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

    def _augment_example(
        self,
        input_grid: Any,
        output_grid: Any,
    ) -> List[Tuple[List[List[int]], List[List[int]]]]:
        if not self._augmentation.enabled or self._augmentation.max_copies <= 0:
            return []
        normalised_input = self._normalise_literal_grid(input_grid)
        normalised_output = self._normalise_literal_grid(output_grid)
        if normalised_input is None or normalised_output is None:
            return []
        augmented: List[Tuple[List[List[int]], List[List[int]]]] = []
        for op in self._augmentation.symmetry_ops:
            transformed_input = self._apply_symmetry(normalised_input, op)
            transformed_output = self._apply_symmetry(normalised_output, op)
            jitter_input, jitter_output = self._apply_color_jitter(transformed_input, transformed_output)
            noisy_input = self._apply_noise(jitter_input)
            augmented.append((noisy_input, jitter_output))
            if len(augmented) >= self._augmentation.max_copies:
                break
        return augmented

    def _apply_symmetry(self, grid: List[List[int]], op: str) -> List[List[int]]:
        if op == "identity":
            return self._clone_grid(grid)
        if op == "hflip":
            return [list(reversed(row)) for row in grid]
        if op == "vflip":
            return list(reversed([row[:] for row in grid]))
        if op == "transpose":
            return self._transpose_grid(grid)
        if op == "rot90":
            return self._rotate_grid(grid, k=1)
        if op == "rot180":
            return self._rotate_grid(grid, k=2)
        if op == "rot270":
            return self._rotate_grid(grid, k=3)
        return self._clone_grid(grid)

    def _transpose_grid(self, grid: List[List[int]]) -> List[List[int]]:
        if not grid:
            return []
        max_cols = max(len(row) for row in grid)
        padded = [row + [self._pad_token] * (max_cols - len(row)) for row in grid]
        transposed = list(zip(*padded))
        return [list(row) for row in transposed]

    def _rotate_grid(self, grid: List[List[int]], *, k: int) -> List[List[int]]:
        k = k % 4
        rotated = self._clone_grid(grid)
        for _ in range(k):
            rotated = self._transpose_grid(rotated)
            rotated = [list(reversed(row)) for row in rotated]
        return rotated

    def _apply_color_jitter(
        self,
        input_grid: List[List[int]],
        output_grid: List[List[int]],
    ) -> Tuple[List[List[int]], List[List[int]]]:
        strength = max(0.0, min(1.0, self._augmentation.color_jitter))
        if strength <= 0.0 or self._rng.random() > strength:
            return self._clone_grid(input_grid), self._clone_grid(output_grid)
        palette = list(range(self._num_colours - 1))
        if len(palette) < 2:
            return self._clone_grid(input_grid), self._clone_grid(output_grid)
        swaps = max(1, int(len(palette) * strength * 0.5))
        mapping = {value: value for value in palette}
        for _ in range(swaps):
            a, b = self._rng.sample(palette, 2)
            mapping[a], mapping[b] = mapping[b], mapping[a]
        mapping[self._pad_token] = self._pad_token
        return self._remap_grid(input_grid, mapping), self._remap_grid(output_grid, mapping)

    def _apply_noise(self, grid: List[List[int]]) -> List[List[int]]:
        prob = max(0.0, min(1.0, self._augmentation.noise_probability))
        if prob <= 0.0:
            return self._clone_grid(grid)
        noisy: List[List[int]] = []
        for row in grid:
            noisy_row: List[int] = []
            for value in row:
                if self._rng.random() < prob:
                    noisy_row.append(self._rng.randrange(0, self._num_colours - 1))
                else:
                    noisy_row.append(value)
            noisy.append(noisy_row)
        return noisy

    def _remap_grid(self, grid: List[List[int]], mapping: Mapping[int, int]) -> List[List[int]]:
        remapped: List[List[int]] = []
        for row in grid:
            remapped.append([mapping.get(value, value) for value in row])
        return remapped

    @staticmethod
    def _clone_grid(grid: List[List[int]]) -> List[List[int]]:
        return [list(row) for row in grid]

    def _run_adaptation(
        self,
        *,
        model: TTTAdapter,
        optimiser: torch.optim.Optimizer,
        inputs: Tensor,
        targets: Tensor,
        masks: Tensor,
        augmented_examples: int = 0,
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
        best_loss = best_reconstruction if best_reconstruction != math.inf else None
        adaptation_state = {
            "best_reconstruction_loss": best_loss,
            "loss_history": history,
            "steps_executed": steps_executed,
            "mean_confidence": float(mean_confidence),
            "augmented_examples": int(augmented_examples),
            "converged": bool(best_loss is not None and best_loss <= self._loss_failure_threshold),
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

        full_probs = logits.softmax(dim=-1)
        mask_grid = masks.view(batch_size, self._max_rows, self._max_cols).to(full_probs.dtype)
        confidence_map = full_probs.max(dim=-1).values.view(batch_size, self._max_rows, self._max_cols)
        confidence_map = confidence_map * mask_grid
        occupancy_pred = confidence_map.view(batch_size, -1).sum(dim=-1)
        occupancy_target = mask_grid.view(batch_size, -1).sum(dim=-1)
        object_count = F.l1_loss(occupancy_pred, occupancy_target)

        colour_values = self._colour_values.to(logits.device)
        expected = (full_probs * colour_values).sum(dim=-1)
        expected_grid = expected.view(batch_size, self._max_rows, self._max_cols)
        smoothness = self._total_variation(expected_grid, mask_grid)
        confidence = confidence_map.sum() / mask_grid.sum().clamp_min(1.0)

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

    def _loss_adjusted_confidence(self, base_confidence: float, best_loss: Optional[float]) -> float:
        base = base_confidence if base_confidence > 0 else 0.25
        if best_loss is None:
            return float(max(self._min_confidence, min(0.4, base * 0.25)))
        scaled = base * math.exp(-max(0.0, best_loss))
        return float(max(self._min_confidence, min(0.99, scaled)))

    def _should_drop_candidate(self, best_loss: Optional[float]) -> bool:
        if best_loss is None:
            return True
        return best_loss >= self._loss_dropout_threshold
