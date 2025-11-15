"""End-to-end integration tests for the symbolic synthesis module.

This module tests the full synthesis pipeline with all enhancements enabled,
including TTT/LLM coordination, fallback mechanisms, and error handling.
"""

from __future__ import annotations

import json

import pytest
from typing import Any, Dict, List

from arc.symbolic.solver import SymbolicSolver, SolverResult
from arc.symbolic.dsl.types import Grid, Program, Stage


@pytest.fixture
def minimal_config() -> Dict[str, Any]:
    """Minimal configuration for testing."""
    return {
        "global": {
            "seed": 1337,
            "device_map": {"symbolic": "cpu"},
        },
        "symbolic": {
            "enabled": True,
            "seed": 1337,
            "search_strategy": "beam",
            "max_depth": 8,
            "max_expansions": 100,
            "max_nodes": 500,
            "beam_width": 10,
            "soft_timeout_s": 5.0,
            "hard_timeout_s": 10.0,
            "egraph": {"enabled": False},
            "ir": {"enabled": False},
            "smt": {"enabled": False},
            "symmetry": {"enabled": False},
            "cegis": {"enabled": False},
            "decomposition": {"enabled": False},
            "coordination": {"enabled": False},
            "advanced_search": {"enabled": False},
            "library": {"enabled": False},
            "engineering": {"enabled": False},
        },
    }


@pytest.fixture
def enhanced_config() -> Dict[str, Any]:
    """Configuration with all enhancements enabled."""
    return {
        "global": {
            "seed": 1337,
            "device_map": {"symbolic": "cpu"},
        },
        "symbolic": {
            "enabled": True,
            "seed": 1337,
            "search_strategy": "beam",
            "max_depth": 8,
            "max_expansions": 100,
            "max_nodes": 500,
            "beam_width": 10,
            "soft_timeout_s": 5.0,
            "hard_timeout_s": 10.0,
            "egraph": {
                "enabled": True,
                "rewrite_limit": 100,
                "saturation_limit": 500,
                "enable_tiered_rules": True,
                "enable_rule_scheduling": True,
                "enable_eclass_analysis": True,
                "enable_rule_mining": False,
            },
            "ir": {
                "enabled": True,
                "connectivity": 4,
                "min_object_size": 1,
            },
            "smt": {
                "enabled": False,  # Disabled for testing without z3
                "timeout_per_candidate": 1.0,
            },
            "symmetry": {
                "enabled": True,
                "color_normalization": True,
                "symmetry_detection": True,
                "step_normalization": True,
            },
            "cegis": {
                "enabled": False,  # Disabled for simpler testing
            },
            "decomposition": {
                "enabled": False,  # Disabled for simpler testing
            },
            "coordination": {
                "enabled": False,  # Disabled for simpler testing
            },
            "advanced_search": {
                "enabled": False,  # Disabled for simpler testing
            },
            "library": {
                "enabled": False,  # Disabled for simpler testing
            },
            "engineering": {
                "enabled": False,  # Disabled for simpler testing
            },
        },
    }


@pytest.fixture
def simple_task() -> Dict[str, Any]:
    """Simple identity task for testing."""
    grid = [[1, 2], [3, 4]]
    return {
        "task_id": "test_identity",
        "train_examples": [
            {"input": grid, "output": grid},
        ],
    }


@pytest.fixture
def rotation_task() -> Dict[str, Any]:
    """Simple rotation task."""
    return {
        "task_id": "test_rotation",
        "train_examples": [
            {
                "input": [[1, 2], [3, 4]],
                "output": [[3, 1], [4, 2]],
            },
        ],
    }


class TestFullSynthesisPipeline:
    """Test the full synthesis pipeline with all enhancements."""
    
    def test_minimal_pipeline(self, minimal_config, simple_task):
        """Test synthesis with minimal configuration."""
        solver = SymbolicSolver(minimal_config)
        result = solver.solve(simple_task)
        
        assert isinstance(result, SolverResult)
        assert result.task_id == "test_identity"
        assert result.status in ["success", "no_solution", "partial"]
        assert isinstance(result.candidates, list)
        assert result.telemetry is not None
        assert result.telemetry.elapsed_s >= 0
    
    def test_enhanced_pipeline(self, enhanced_config, simple_task):
        """Test synthesis with enhanced configuration."""
        solver = SymbolicSolver(enhanced_config)
        result = solver.solve(simple_task)
        
        assert isinstance(result, SolverResult)
        assert result.task_id == "test_identity"
        assert result.status in ["success", "no_solution", "partial"]
        assert isinstance(result.candidates, list)
        
        # Check that enhancements were used
        if "egraph" in result.summary:
            assert "iterations" in result.summary["egraph"]
        
        if "ir_enabled" in result.summary:
            assert result.summary["ir_enabled"] is True
    
    def test_pipeline_with_rotation(self, enhanced_config, rotation_task):
        """Test synthesis with a rotation task."""
        solver = SymbolicSolver(enhanced_config)
        result = solver.solve(rotation_task)
        
        assert isinstance(result, SolverResult)
        assert result.task_id == "test_rotation"
        assert isinstance(result.candidates, list)
        
        # Check telemetry
        assert result.telemetry.expansions >= 0
        assert result.telemetry.generated_nodes >= 0
    
    def test_pipeline_with_timeout(self, minimal_config, simple_task):
        """Test that pipeline respects timeout."""
        # Set very short timeout
        minimal_config["symbolic"]["soft_timeout_s"] = 0.1
        minimal_config["symbolic"]["hard_timeout_s"] = 0.2
        
        solver = SymbolicSolver(minimal_config)
        result = solver.solve(simple_task)
        
        assert isinstance(result, SolverResult)
        # Should complete quickly due to timeout
        assert result.telemetry.elapsed_s < 1.0


class TestTTTCoordination:
    """Test TTT coordination end-to-end."""
    
    def test_ttt_coordination_disabled(self, minimal_config, simple_task):
        """Test that TTT coordination can be disabled."""
        solver = SymbolicSolver(minimal_config)
        assert solver.coordination is None
        
        result = solver.solve(simple_task)
        assert isinstance(result, SolverResult)
    
    def test_ttt_coordination_enabled(self, enhanced_config, simple_task):
        """Test TTT coordination when enabled."""
        # Enable coordination
        enhanced_config["symbolic"]["coordination"] = {
            "enabled": True,
            "enable_ttt_coordination": True,
            "enable_llm_coordination": False,
        }
        
        solver = SymbolicSolver(enhanced_config)
        assert solver.coordination is not None
        
        result = solver.solve(simple_task)
        assert isinstance(result, SolverResult)
        
        # Check coordination stats if available
        if "coordination_stats" in result.summary:
            assert isinstance(result.summary["coordination_stats"], dict)


class TestLLMCoordination:
    """Test LLM coordination end-to-end."""
    
    def test_llm_coordination_disabled(self, minimal_config, simple_task):
        """Test that LLM coordination can be disabled."""
        solver = SymbolicSolver(minimal_config)
        assert solver.coordination is None
        
        result = solver.solve(simple_task)
        assert isinstance(result, SolverResult)
    
    def test_llm_coordination_enabled(self, enhanced_config, simple_task):
        """Test LLM coordination when enabled."""
        # Enable coordination
        enhanced_config["symbolic"]["coordination"] = {
            "enabled": True,
            "enable_ttt_coordination": False,
            "enable_llm_coordination": True,
        }
        
        solver = SymbolicSolver(enhanced_config)
        assert solver.coordination is not None
        
        result = solver.solve(simple_task)
        assert isinstance(result, SolverResult)


class TestFallbackMechanisms:
    """Test fallback and error handling paths."""
    
    def test_fallback_on_search_exhaustion(self, minimal_config, simple_task):
        """Test fallback when search is exhausted."""
        # Set very low limits to force exhaustion
        minimal_config["symbolic"]["max_expansions"] = 10
        minimal_config["symbolic"]["max_nodes"] = 20
        
        solver = SymbolicSolver(minimal_config)
        result = solver.solve(simple_task)
        
        assert isinstance(result, SolverResult)
        # Should complete without crashing
        assert result.status in ["success", "no_solution", "partial"]
    
    def test_fallback_on_invalid_config(self):
        """Test fallback on invalid configuration."""
        invalid_config = {
            "global": {"seed": 1337},
            "symbolic": {
                "enabled": True,
                "max_depth": -1,  # Invalid
            },
        }
        
        # Should not crash, may use defaults
        solver = SymbolicSolver(invalid_config)
        assert solver is not None
    
    def test_error_handling_on_malformed_task(self, minimal_config):
        """Test error handling with malformed task."""
        malformed_task = {
            "task_id": "test_malformed",
            "train_examples": [],  # Empty examples
        }
        
        solver = SymbolicSolver(minimal_config)
        result = solver.solve(malformed_task)
        
        assert isinstance(result, SolverResult)
        # Should handle gracefully
        assert result.status in ["no_solution", "failed", "partial"]
    
    def test_error_handling_on_invalid_grid(self, minimal_config):
        """Test error handling with invalid grid data."""
        invalid_task = {
            "task_id": "test_invalid_grid",
            "train_examples": [
                {
                    "input": [[1, 2], [3]],  # Jagged array
                    "output": [[1, 2], [3, 4]],
                },
            ],
        }

        solver = SymbolicSolver(minimal_config)
        result = solver.solve(invalid_task)

        assert isinstance(result, SolverResult)
        assert result.status == "failed"
        assert result.summary["status"] == "failed"
        assert result.summary.get("reason") == "invalid_task"
        assert result.summary.get("validation_errors")

        diagnostics = result.telemetry.diagnostics
        assert diagnostics, "Expected diagnostics output for invalid grids"
        payload = json.loads(diagnostics[0].read_text(encoding="utf-8"))
        failure_entries = payload.get("failures", [])
        assert failure_entries, "Diagnostics should include failure entries"
        assert any(entry.get("grid_role") == "input" for entry in failure_entries)
        assert any(entry.get("type") == "invalid_grid" for entry in failure_entries)


class TestFeatureToggling:
    """Test configuration-based feature toggling."""
    
    def test_egraph_toggle(self, minimal_config, simple_task):
        """Test e-graph can be toggled on/off."""
        # Test with e-graph disabled
        minimal_config["symbolic"]["egraph"] = {"enabled": False}
        solver = SymbolicSolver(minimal_config)
        assert solver.egraph_enabled is False
        
        result = solver.solve(simple_task)
        assert "egraph" not in result.summary or result.summary.get("egraph") is None
        
        # Test with e-graph enabled
        minimal_config["symbolic"]["egraph"] = {"enabled": True}
        solver = SymbolicSolver(minimal_config)
        assert solver.egraph_enabled is True
    
    def test_symmetry_toggle(self, minimal_config, simple_task):
        """Test symmetry features can be toggled."""
        # Test with symmetry disabled
        minimal_config["symbolic"]["symmetry"] = {"enabled": False}
        solver = SymbolicSolver(minimal_config)
        assert solver.symmetry_enabled is False
        assert solver.color_normalizer is None
        
        # Test with symmetry enabled
        minimal_config["symbolic"]["symmetry"] = {
            "enabled": True,
            "color_normalization": True,
            "symmetry_detection": True,
        }
        solver = SymbolicSolver(minimal_config)
        assert solver.symmetry_enabled is True
        assert solver.color_normalizer is not None
    
    def test_ir_toggle(self, minimal_config, simple_task):
        """Test IR layer can be toggled."""
        # Test with IR disabled
        minimal_config["symbolic"]["ir"] = {"enabled": False}
        solver = SymbolicSolver(minimal_config)
        assert solver.ir_enabled is False
        assert solver.grid_mapper is None
        
        # Test with IR enabled
        minimal_config["symbolic"]["ir"] = {"enabled": True}
        solver = SymbolicSolver(minimal_config)
        assert solver.ir_enabled is True
        assert solver.grid_mapper is not None


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""
    
    def test_minimal_config_still_works(self):
        """Test that minimal config without new features still works."""
        config = {
            "global": {"seed": 1337},
            "symbolic": {
                "enabled": True,
                "max_depth": 8,
            },
        }
        
        solver = SymbolicSolver(config)
        assert solver is not None
        
        # All new features should be disabled by default
        assert solver.ir_enabled is False
        assert solver.symmetry_enabled is False
        assert solver.cegis_enabled is False
        assert solver.decomposition_enabled is False
        assert solver.coordination_enabled is False
    
    def test_legacy_task_format(self, minimal_config):
        """Test that legacy task format still works."""
        legacy_task = {
            "task_id": "legacy_test",
            "examples": [  # Old key name
                {"input": [[1]], "output": [[1]]},
            ],
        }
        
        solver = SymbolicSolver(minimal_config)
        result = solver.solve(legacy_task)
        
        assert isinstance(result, SolverResult)
        assert result.task_id == "legacy_test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
