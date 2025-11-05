from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from arc.scheduler import TaskFeatures, compute_task_features

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "scheduler" / "features"


def _load_fixture(name: str) -> Mapping[str, Any]:
    payload = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return payload


def _assert_features_close(actual: TaskFeatures, expected: Mapping[str, Any]) -> None:
    actual_dict = actual.to_dict()
    for top_key, expected_block in expected.items():
        if not isinstance(expected_block, Mapping):
            assert actual_dict[top_key] == expected_block
            continue
        for key, expected_value in expected_block.items():
            actual_value = actual_dict[top_key][key]
            if isinstance(expected_value, Mapping):
                actual_map = {str(k): v for k, v in actual_value.items()}
                expected_map = {str(k): v for k, v in expected_value.items()}
                assert actual_map == expected_map
            elif isinstance(expected_value, float):
                assert actual_value == pytest.approx(expected_value, rel=1e-6)
            else:
                assert actual_value == expected_value


def test_symmetry_task_features_round_trip() -> None:
    fixture = _load_fixture("symmetry_task")
    task = fixture["task"]
    expected = fixture["expected_features"]
    features = compute_task_features(task["task_id"], task["train_examples"])
    _assert_features_close(features, expected)


def test_palette_task_features_respect_history_context() -> None:
    fixture = _load_fixture("palette_task")
    task = fixture["task"]
    expected = fixture["expected_features"]
    history = task["metadata"]["scheduler_history"]
    features = compute_task_features(task["task_id"], task["train_examples"], history=history)
    _assert_features_close(features, expected)
