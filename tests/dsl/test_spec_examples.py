from __future__ import annotations

from pathlib import Path

from arc.symbolic.dsl.verify import verify_directory


def test_spec_examples_pass(tmp_path):
    fixtures_dir = Path("fixtures/dsl/spec_examples")
    summary = verify_directory(fixtures_dir, log_dir=tmp_path)
    assert summary.failed == 0, f"Expected all fixtures to pass, but saw {summary.failed} failures."
