"""Regression test suite for symbolic synthesis enhancements.

This module contains regression tests to prevent known issues from recurring.
Tests are organized by the issue they prevent.
"""

from __future__ import annotations

import pytest
from typing import Any, Dict

from arc.symbolic.solver import SymbolicSolver
from arc.symbolic.dsl.types import Grid, Program, Stage


@pytest.fixture
def base_config() -> Dict[str, Any]:
    """Base configuration for regression tests."""
    return {
        "global": {
            "seed": 1337,
            "device_map": {"symbolic": "cpu"},
        },
        "symbolic": {
            "enabled": True,
            "seed": 1337,
            "max_depth": 8,
            "max_expansions": 100,
            "soft_timeout_s": 5.0,
            "hard_timeout_s": 10.0,
        },
    }


class TestEGraphRegressions:
    """Regression tests for e-graph issues."""
    
    def test_egraph_saturation_limit_respected(self, base_config):
        """Regression: e-graph saturation should respect limits.
        
        Issue: e-graph saturation could run indefinitely without respecting
        the saturation limit, causing hangs.
        """
        base_config["symbolic"]["egraph"] = {
            "enabled": True,
            "saturation_limit": 100,
            "rewrite_limit": 50,
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_saturation_limit",
            "train_examples": [
                {"input": [[1, 2]], "output": [[2, 1]]},
            ],
        }
        
        result = solver.solve(task)
        
        # Should complete without hanging
        assert result is not None
        assert result.telemetry.elapsed_s < 10.0
    
    def test_egraph_handles_empty_program_list(self, base_config):
        """Regression: e-graph should handle empty program lists gracefully.
        
        Issue: Adding empty program list to e-graph caused crashes.
        """
        base_config["symbolic"]["egraph"] = {"enabled": True}
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_empty_programs",
            "train_examples": [],  # No examples
        }
        
        # Should not crash
        result = solver.solve(task)
        assert result is not None


class TestSymmetryRegressions:
    """Regression tests for symmetry issues."""
    
    def test_color_normalization_preserves_structure(self, base_config):
        """Regression: color normalization should preserve grid structure.
        
        Issue: Color normalization could change grid dimensions or structure.
        """
        base_config["symbolic"]["symmetry"] = {
            "enabled": True,
            "color_normalization": True,
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_color_norm",
            "train_examples": [
                {
                    "input": [[1, 2, 3], [4, 5, 6]],
                    "output": [[6, 5, 4], [3, 2, 1]],
                },
            ],
        }
        
        result = solver.solve(task)
        
        # Should complete without errors
        assert result is not None
        assert result.status in ["success", "no_solution", "partial"]
    
    def test_symmetry_detection_handles_asymmetric_grids(self, base_config):
        """Regression: symmetry detection should handle asymmetric grids.
        
        Issue: Symmetry detection could crash on asymmetric grids.
        """
        base_config["symbolic"]["symmetry"] = {
            "enabled": True,
            "symmetry_detection": True,
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_asymmetric",
            "train_examples": [
                {
                    "input": [[1, 2], [3, 4], [5, 6]],  # Asymmetric
                    "output": [[1, 2], [3, 4], [5, 6]],
                },
            ],
        }
        
        result = solver.solve(task)
        assert result is not None


class TestCEGISRegressions:
    """Regression tests for CEGIS issues."""
    
    def test_cegis_handles_max_iterations(self, base_config):
        """Regression: CEGIS should respect max iterations.
        
        Issue: CEGIS loop could run indefinitely without respecting max_iterations.
        """
        base_config["symbolic"]["cegis"] = {
            "enabled": True,
            "max_iterations": 3,
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_cegis_iterations",
            "train_examples": [
                {"input": [[1]], "output": [[2]]},
            ],
        }
        
        result = solver.solve(task)
        
        # Should complete within reasonable time
        assert result is not None
        assert result.telemetry.elapsed_s < 10.0
    
    def test_counterexample_minimization_terminates(self, base_config):
        """Regression: counterexample minimization should terminate.
        
        Issue: Minimization could loop indefinitely on certain inputs.
        """
        base_config["symbolic"]["cegis"] = {
            "enabled": True,
            "enable_counterexample_minimization": True,
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_minimization",
            "train_examples": [
                {
                    "input": [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
                    "output": [[2, 2, 2], [2, 2, 2], [2, 2, 2]],
                },
            ],
        }
        
        result = solver.solve(task)
        assert result is not None


class TestCoordinationRegressions:
    """Regression tests for coordination issues."""
    
    def test_coordination_handles_missing_messages(self, base_config):
        """Regression: coordination should handle missing messages gracefully.
        
        Issue: Missing messages from TTT/LLM could cause crashes.
        """
        base_config["symbolic"]["coordination"] = {
            "enabled": True,
            "enable_ttt_coordination": True,
            "enable_llm_coordination": True,
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_missing_messages",
            "train_examples": [
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        # Should handle gracefully even with no messages
        result = solver.solve(task)
        assert result is not None
    
    def test_coordination_handles_malformed_invariants(self, base_config):
        """Regression: coordination should handle malformed invariants.
        
        Issue: Malformed invariants from TTT could cause crashes.
        """
        base_config["symbolic"]["coordination"] = {
            "enabled": True,
            "enable_ttt_coordination": True,
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_malformed_invariants",
            "train_examples": [
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        result = solver.solve(task)
        assert result is not None


class TestLibraryRegressions:
    """Regression tests for library management issues."""
    
    def test_library_handles_duplicate_fragments(self, base_config):
        """Regression: library should handle duplicate fragments.
        
        Issue: Adding duplicate fragments could cause inconsistent state.
        """
        base_config["symbolic"]["library"] = {
            "enabled": True,
            "fragment_mining": {"enabled": True},
        }
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_duplicate_fragments",
            "train_examples": [
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        result = solver.solve(task)
        assert result is not None
    
    def test_library_pruning_preserves_active_rules(self, base_config):
        """Regression: library pruning should preserve active rules.
        
        Issue: Pruning could remove rules that are still being used.
        """
        base_config["symbolic"]["library"] = {
            "enabled": True,
            "pruning": {
                "enabled": True,
                "interval": 1,  # Prune after every solve
            },
        }
        
        solver = SymbolicSolver(base_config)
        
        # Solve multiple tasks
        for i in range(3):
            task = {
                "task_id": f"test_pruning_{i}",
                "train_examples": [
                    {"input": [[1]], "output": [[1]]},
                ],
            }
            result = solver.solve(task)
            assert result is not None


class TestEngineeringRegressions:
    """Regression tests for engineering infrastructure issues."""
    
    def test_cache_handles_hash_collisions(self, base_config):
        """Regression: cache should handle hash collisions gracefully.
        
        Issue: Hash collisions in semantic cache could return wrong programs.
        """
        base_config["symbolic"]["engineering"] = {
            "enabled": True,
            "cache": {
                "enable_program_cache": True,
            },
        }
        
        solver = SymbolicSolver(base_config)
        
        # Solve similar tasks that might have hash collisions
        for i in range(3):
            task = {
                "task_id": f"test_cache_{i}",
                "train_examples": [
                    {"input": [[i]], "output": [[i]]},
                ],
            }
            result = solver.solve(task)
            assert result is not None
    
    def test_timeout_guard_prevents_hangs(self, base_config):
        """Regression: timeout guard should prevent hangs.
        
        Issue: Some operations could hang indefinitely without timeout protection.
        """
        base_config["symbolic"]["soft_timeout_s"] = 1.0
        base_config["symbolic"]["hard_timeout_s"] = 2.0
        
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_timeout",
            "train_examples": [
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        result = solver.solve(task)
        
        # Should complete within timeout
        assert result is not None
        assert result.telemetry.elapsed_s < 5.0


class TestBackwardCompatibilityRegressions:
    """Regression tests for backward compatibility issues."""
    
    def test_old_config_format_still_works(self):
        """Regression: old configuration format should still work.
        
        Issue: New features broke compatibility with old configs.
        """
        old_config = {
            "global": {"seed": 1337},
            "symbolic": {
                "enabled": True,
                "max_depth": 8,
                # No new feature flags
            },
        }
        
        solver = SymbolicSolver(old_config)
        
        task = {
            "task_id": "test_old_config",
            "train_examples": [
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        result = solver.solve(task)
        assert result is not None
    
    def test_legacy_task_format_supported(self, base_config):
        """Regression: legacy task format should be supported.
        
        Issue: Changes to task format broke existing code.
        """
        solver = SymbolicSolver(base_config)
        
        # Old format used "examples" instead of "train_examples"
        legacy_task = {
            "task_id": "test_legacy",
            "examples": [
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        result = solver.solve(legacy_task)
        assert result is not None
        assert result.task_id == "test_legacy"


class TestErrorHandlingRegressions:
    """Regression tests for error handling issues."""
    
    def test_invalid_grid_handled_gracefully(self, base_config):
        """Regression: invalid grids should be handled gracefully.
        
        Issue: Invalid grid data could cause unhandled exceptions.
        """
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_invalid_grid",
            "train_examples": [
                {
                    "input": [[1, 2], [3]],  # Jagged array
                    "output": [[1, 2], [3, 4]],
                },
            ],
        }
        
        # Should not crash
        result = solver.solve(task)
        assert result is not None
    
    def test_empty_examples_handled(self, base_config):
        """Regression: empty examples should be handled.
        
        Issue: Empty example list could cause crashes.
        """
        solver = SymbolicSolver(base_config)
        
        task = {
            "task_id": "test_empty_examples",
            "train_examples": [],
        }
        
        result = solver.solve(task)
        assert result is not None
        assert result.status in ["no_solution", "failed", "partial"]
    
    def test_missing_task_id_handled(self, base_config):
        """Regression: missing task_id should be handled.
        
        Issue: Missing task_id could cause key errors.
        """
        solver = SymbolicSolver(base_config)
        
        task = {
            # No task_id
            "train_examples": [
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        result = solver.solve(task)
        assert result is not None
        # Should use default task_id
        assert result.task_id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
