from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass
class SchedulerModule:
    config: Dict[str, Any]

    def initialise(self) -> None:
        # Placeholder to load scheduler features and policies.
        pass

    def dispatch(self, tasks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return list(tasks)
