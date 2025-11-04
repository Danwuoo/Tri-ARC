from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class LLMModule:
    config: Dict[str, Any]

    def initialise(self) -> None:
        if not self.config.get("enabled", True):
            return
        # Placeholder for loading quantised LLM checkpoints.

    def generate(self, prompt: str) -> Dict[str, Any]:
        raise NotImplementedError("LLM generation pending.")
