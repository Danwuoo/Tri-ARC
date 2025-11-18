from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from arc.common.grid import normalise_grid


@dataclass(frozen=True)
class PromptVariant:
    """Prompt specialisation used to diversify Qwen sampling."""

    name: str
    description: str
    focus: str
    system_prompt: str
    instructions: Tuple[str, ...]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_new_tokens: Optional[int] = None
    weight: float = 1.0
    style: str = "cot"


@dataclass
class LLMPromptContext:
    task_id: str
    train_examples: Sequence[Mapping[str, Any]]
    eval_examples: Sequence[Mapping[str, Any]] = ()


@dataclass
class PromptRequest:
    messages: List[Dict[str, str]]
    variant: str
    temperature: float
    top_p: float
    max_new_tokens: int
    stop_sequences: Tuple[str, ...]
    metadata: Dict[str, Any]


class PromptBuilder:
    """Formats ARC tasks into chat prompts for the LLM."""

    def __init__(
        self,
        *,
        prompt_version: str,
        variants: Sequence[PromptVariant],
        stop_sequences: Sequence[str] = ("</json>", "</response>", "<|im_end|>"),
        default_temperature: float = 0.7,
        default_top_p: float = 0.9,
        default_max_new_tokens: int = 512,
    ) -> None:
        if not variants:
            raise ValueError("PromptBuilder requires at least one variant.")
        self.prompt_version = prompt_version
        self.variants: Tuple[PromptVariant, ...] = tuple(variants)
        self.stop_sequences: Tuple[str, ...] = tuple(stop_sequences)
        self.default_temperature = float(default_temperature)
        self.default_top_p = float(default_top_p)
        self.default_max_new_tokens = int(default_max_new_tokens)

    def build_requests(self, context: LLMPromptContext, total_samples: int) -> List[PromptRequest]:
        total = max(1, total_samples if total_samples > 0 else len(self.variants))
        distribution = self._allocate_counts(total)
        requests: List[PromptRequest] = []
        sample_index = 0
        for variant, count in distribution:
            for _ in range(count):
                requests.append(self._make_request(context, variant, sample_index))
                sample_index += 1
        return requests

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _allocate_counts(self, total: int) -> List[Tuple[PromptVariant, int]]:
        weights = [max(1e-3, variant.weight) for variant in self.variants]
        weight_sum = math.fsum(weights)
        base_counts: List[int] = []
        fractions: List[Tuple[float, int]] = []
        remaining = total
        for idx, weight in enumerate(weights):
            raw = total * weight / weight_sum
            whole = int(math.floor(raw))
            base_counts.append(whole)
            fractions.append((raw - whole, idx))
            remaining -= whole
        while remaining > 0:
            pick = max(fractions, key=lambda item: (item[0], weights[item[1]]))
            base_counts[pick[1]] += 1
            fractions[fractions.index(pick)] = (0.0, pick[1])
            remaining -= 1
        return [
            (variant, count)
            for variant, count in zip(self.variants, base_counts)
            if count > 0
        ]

    def _make_request(self, context: LLMPromptContext, variant: PromptVariant, sample_index: int) -> PromptRequest:
        user_prompt = self._render_user_prompt(context, variant)
        system_prompt = variant.system_prompt.format(prompt_version=self.prompt_version)
        temperature = variant.temperature if variant.temperature is not None else self.default_temperature
        top_p = variant.top_p if variant.top_p is not None else self.default_top_p
        max_new_tokens = variant.max_new_tokens if variant.max_new_tokens is not None else self.default_max_new_tokens
        metadata = {
            "prompt_version": self.prompt_version,
            "variant": variant.name,
            "variant_style": variant.style,
            "sample_index": sample_index,
            "focus": variant.focus,
        }
        return PromptRequest(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            variant=variant.name,
            temperature=temperature,
            top_p=top_p,
            max_new_tokens=max_new_tokens,
            stop_sequences=self.stop_sequences,
            metadata=metadata,
        )

    def _render_user_prompt(self, context: LLMPromptContext, variant: PromptVariant) -> str:
        lines: List[str] = []
        lines.append(f"Task ID: {context.task_id}")
        lines.append(f"Focus: {variant.focus}")
        lines.append("Reason through the mapping using the numbered checklist before emitting DSL.")
        lines.append("")
        lines.append("Reasoning Checklist:")
        for idx, instruction in enumerate(variant.instructions, 1):
            lines.append(f"  {idx}. {instruction}")
        lines.append("")
        lines.append("Examples:")
        for idx, example in enumerate(context.train_examples, 1):
            lines.extend(_format_example(example, idx, role="train"))
        if context.eval_examples:
            lines.append("")
            lines.append("Evaluation inputs (predict outputs in JSON response under test_outputs):")
            for idx, example in enumerate(context.eval_examples, 1):
                lines.extend(_format_example(example, idx, role="eval"))
        lines.append("")
        lines.append(
            "Respond with a single JSON object using keys: rationale (string), dsl (string pipeline),"
            " confidence (0-1 float), test_outputs (list of grids for evaluation inputs)"
        )
        lines.append("All reasoning must stay inside the rationale string. Do not add commentary outside JSON.")
        lines.append("Keep DSL compliant with docs/reference/dsl_reference.md primitives. Use lowercase operator names.")
        return "\n".join(lines)


def build_default_variants() -> Tuple[PromptVariant, ...]:
    """Return the built-in prompt profiles for the LLM lane."""

    system_prompt = (
        "You are Tri-ARC's DSL synthesis assistant. Use docs/reference/dsl_reference.md primitives only."
        " Think aloud inside the rationale field and prefer concise programs with <=8 stages."
        " Obey resource limits: deterministic, no randomness, no loops beyond provided primitives."
    )

    planner = PromptVariant(
        name="planner",
        description="General planner with explicit chain-of-thought",
        focus="Derive a rule mapping inputs to outputs, citing colour/shape heuristics.",
        system_prompt=system_prompt,
        instructions=(
            "List concrete differences between input/output grids (sizes, palette, object counts).",
            "Break the solution into primitive-friendly steps (segment, transform, compose).",
            "Draft the DSL pipeline referencing exactly those primitives.",
            "Validate the program mentally against each training pair before finalising.",
        ),
    )

    symmetry = PromptVariant(
        name="symmetry",
        description="Symmetry and repetition focused CoT",
        focus="Detect reflections, rotations, tiling, and repeated motifs.",
        system_prompt=system_prompt,
        instructions=(
            "Identify axes or rotations that align input and output.",
            "Describe how colours map under those symmetries.",
            "Compose primitives such as reflect/rotate/crop/paste accordingly.",
            "State any palette invariants before providing DSL.",
        ),
        weight=0.8,
    )

    contrast = PromptVariant(
        name="contrast",
        description="Object counting and contrast-driven reasoning",
        focus="Track foreground objects, counts, and colour replacement rules.",
        system_prompt=system_prompt,
        instructions=(
            "Count distinct objects and note bounding boxes versus background.",
            "Explain how colours change (preserve, replace, majority fill, outlines).",
            "Map each reasoning step to DSL primitives (filter_objects, paint_region, etc.).",
            "Predict evaluation outputs conservatively if uncertain.",
        ),
        weight=0.65,
    )

    return (planner, symmetry, contrast)


# ---------------------------------------------------------------------- #
# Formatting helpers
# ---------------------------------------------------------------------- #

def _format_example(example: Mapping[str, Any], index: int, *, role: str) -> List[str]:
    lines: List[str] = []
    prefix = "Train" if role == "train" else "Eval"
    lines.append(f"  {prefix} Example {index}:")
    input_grid = normalise_grid(example.get("input"))
    lines.append(_describe_grid("Input", input_grid))
    expected = example.get("output")
    if role == "train" and expected is not None:
        output_grid = normalise_grid(expected)
        lines.append(_describe_grid("Output", output_grid))
        lines.append(f"    Δ summary: {_describe_delta(input_grid, output_grid)}")
    if example.get("description"):
        lines.append(f"    Notes: {example['description']}")
    return lines


def _describe_grid(label: str, grid) -> str:
    rows, cols = grid.shape
    palette = _palette_summary(grid)
    body = _grid_to_ascii(grid)
    return f"    {label} ({rows}x{cols}, palette {palette}):\n{body}"


def _palette_summary(grid) -> str:
    values = np.unique(grid.data)
    clipped = values[:10]
    tokens = ", ".join(str(int(v)) for v in clipped)
    suffix = ", ..." if len(values) > len(clipped) else ""
    return "{" + tokens + suffix + "}"


def _grid_to_ascii(grid) -> str:
    rows = ["    " + " ".join(str(int(cell)) for cell in row) for row in grid.data]
    return "\n".join(rows)


def _describe_delta(input_grid, output_grid) -> str:
    in_shape = f"{input_grid.shape[0]}x{input_grid.shape[1]}"
    out_shape = f"{output_grid.shape[0]}x{output_grid.shape[1]}"
    palette_in = set(np.unique(input_grid.data).tolist())
    palette_out = set(np.unique(output_grid.data).tolist())
    changed = int(np.sum(input_grid.data != output_grid.data))
    palette_delta = sorted(palette_out - palette_in)
    palette_removed = sorted(palette_in - palette_out)
    parts = [f"shape {in_shape}->{out_shape}", f"cells changed {changed}"]
    if palette_delta:
        parts.append(f"added colours {palette_delta}")
    if palette_removed:
        parts.append(f"removed colours {palette_removed}")
    return ", ".join(parts)
