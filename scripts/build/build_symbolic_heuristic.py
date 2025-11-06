#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Tuple

import torch


FEATURE_DIM = 7  # coverage, consistency, progress, novelty, depth_ratio, cost, stagnation


class SimpleHeuristicModel(torch.nn.Module):
    """Lightweight feedforward network used for heuristic scoring."""

    def __init__(self) -> None:
        super().__init__()
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(FEATURE_DIM, 32),
            torch.nn.ReLU(),
            torch.nn.Linear(32, 16),
            torch.nn.ReLU(),
            torch.nn.Linear(16, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        return self.layers(features).view(-1)


def compute_checksum(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_model(seed: int) -> Tuple[torch.jit.ScriptModule, dict]:
    torch.manual_seed(seed)
    model = SimpleHeuristicModel()
    scripted = torch.jit.script(model)
    metadata = {
        "seed": seed,
        "layers": [module.__class__.__name__ for module in model.layers],
        "feature_dim": FEATURE_DIM,
    }
    return scripted, metadata


def save_model(scripted: torch.jit.ScriptModule, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.jit.save(scripted, str(output_path))


def write_manifest(checksum_path: Path, checksum: str, metadata: dict) -> None:
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"sha256": checksum, "metadata": metadata}
    checksum_path.write_text(json.dumps(payload, indent=2) + os.linesep, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TorchScript heuristic weights for the symbolic solver.")
    parser.add_argument("--output", type=Path, default=Path("models/symbolic/heuristic.pt"), help="Destination for the TorchScript module.")
    parser.add_argument("--checksum", type=Path, default=Path("models/symbolic/heuristic.sha256"), help="Path to write the checksum manifest.")
    parser.add_argument("--seed", type=int, default=1337, help="Random seed for deterministic weight initialisation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scripted, metadata = build_model(seed=args.seed)
    save_model(scripted, args.output)
    checksum = compute_checksum(args.output)
    metadata["checksum"] = checksum
    write_manifest(args.checksum, checksum, metadata)
    print(f"[build] Wrote heuristic weights to {args.output} (sha256={checksum})")
    print(f"[build] Checksum manifest written to {args.checksum}")


if __name__ == "__main__":
    main()
