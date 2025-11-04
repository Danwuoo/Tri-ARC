from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class TTTModule:
    config: Dict[str, Any]

    def initialise(self) -> None:
        if not self.config.get("enabled", True):
            return
        # Placeholder for time-to-think initialisation.

    def adapt(self, task: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("TTT adaptation pending.")
