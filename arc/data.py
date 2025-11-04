from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


def load_sample_task(data_root: Path) -> Optional[Dict]:
    """Return the contents of the first ARC task JSON file under training data."""
    training_path = data_root / "training"
    if not training_path.exists():
        return None

    for candidate in sorted(training_path.glob("*.json")):
        with candidate.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    # If training root contains subdirectories (e.g., ARC-AGI-2 layout), search recursively.
    for candidate in sorted(training_path.rglob("*.json")):
        with candidate.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    return None
