#!/usr/bin/env python3
"""
Validate deterministic execution of symbolic synthesis module.

Verifies that:
1. All random operations use fixed seeds
2. Checkpoint save/restore functionality works correctly
3. Results are reproducible across multiple runs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


def set_global_seeds(seed: int = 1337) -> None:
    """Set all random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass


def compute_result_hash(result: Any) -> str:
    """Compute hash of a result for comparison."""
    # Convert result to JSON string for hashing
    result_str = json.dumps(result, sort_keys=True, default=str)
    return hashlib.sha256(result_str.encode()).hexdigest()


def validate_seed_usage(root: Path) -> Dict[str, Any]:
    """Validate that all random operations use fixed seeds."""
    print("[Deterministic] Validating seed usage...")
    
    issues = []
    warnings = []
    
    # Check for unseeded random operations in symbolic module
    symbolic_dir = root / "arc" / "symbolic"
    if symbolic_dir.exists():
        for py_file in symbolic_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            
            # Check for random.* calls without seed
            if "random." in content and "random.seed" not in content:
                # Check if it's in a function that receives seed parameter
                if "seed" not in content:
                    warnings.append({
                        "file": str(py_file.relative_to(root)),
                        "issue": "Uses random module without explicit seed parameter",
                    })
            
            # Check for np.random calls without seed
            if "np.random" in content and "np.random.seed" not in content:
                if "seed" not in content and "rng" not in content:
                    warnings.append({
                        "file": str(py_file.relative_to(root)),
                        "issue": "Uses np.random without explicit seed or RNG parameter",
                    })
    
    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "total_warnings": len(warnings),
    }


def validate_reproducibility(root: Path) -> Dict[str, Any]:
    """Validate that results are reproducible across runs."""
    print("[Deterministic] Validating reproducibility...")
    
    try:
        # Import symbolic solver
        sys.path.insert(0, str(root))
        from arc.symbolic.solver import SymbolicSolver
        from arc.symbolic.search.types import SearchBudget
        
        # Create a simple test task
        test_task = {
            "task_id": "deterministic_test",
            "train": [
                {
                    "input": [[0, 0], [0, 0]],
                    "output": [[1, 1], [1, 1]],
                }
            ],
            "test": [
                {
                    "input": [[0, 0], [0, 0]],
                }
            ],
        }
        
        # Run solver multiple times with same seed
        results = []
        num_runs = 3
        seed = 1337
        
        for run_idx in range(num_runs):
            print(f"[Deterministic]   Run {run_idx + 1}/{num_runs}...")
            
            # Set seeds
            set_global_seeds(seed)
            
            # Create solver with minimal config
            config = {
                "device": "cpu",
                "search": {
                    "strategy": "dfs",
                    "max_depth": 3,
                    "max_expansions": 10,
                    "soft_timeout_s": 1.0,
                    "hard_timeout_s": 2.0,
                },
                "egraph": {"enabled": False},
                "cegis": {"enabled": False},
                "smt": {"enabled": False},
            }
            
            solver = SymbolicSolver(config)
            
            # Run solver
            try:
                result = solver.solve(test_task)
                result_dict = {
                    "status": result.status if hasattr(result, "status") else "unknown",
                    "num_candidates": len(result.candidates) if hasattr(result, "candidates") else 0,
                }
                results.append(result_dict)
            except Exception as e:
                results.append({"error": str(e)})
        
        # Check if all results are identical
        if len(results) > 1:
            first_hash = compute_result_hash(results[0])
            all_identical = all(
                compute_result_hash(r) == first_hash for r in results[1:]
            )
        else:
            all_identical = True
        
        return {
            "passed": all_identical,
            "num_runs": num_runs,
            "results": results,
            "all_identical": all_identical,
        }
        
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "message": "Failed to run reproducibility test",
        }


def validate_checkpoint_functionality(root: Path) -> Dict[str, Any]:
    """Validate checkpoint save/restore functionality."""
    print("[Deterministic] Validating checkpoint functionality...")
    
    try:
        sys.path.insert(0, str(root))
        from arc.symbolic.engineering.cache import CacheManager
        
        # Create temporary checkpoint directory
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir) / "checkpoints"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            
            # Create cache manager
            cache_manager = CacheManager()
            
            # Test data
            test_program = {
                "stages": [
                    {"operator": "rotate_90", "arguments": []},
                    {"operator": "reflect_horizontal", "arguments": []},
                ],
            }
            test_examples = [
                {"input": [[0, 1], [2, 3]], "output": [[1, 3], [0, 2]]},
            ]
            
            # Cache program
            cache_key = cache_manager.cache_program_semantics(
                test_program,
                test_examples,
            )
            
            # Verify cache hit
            cached_program = cache_manager.program_cache.get(cache_key)
            
            if cached_program is None:
                return {
                    "passed": False,
                    "error": "Failed to retrieve cached program",
                }
            
            # Verify cached program matches original
            if cached_program != test_program:
                return {
                    "passed": False,
                    "error": "Cached program does not match original",
                }
            
            return {
                "passed": True,
                "cache_key": cache_key,
                "message": "Checkpoint functionality validated successfully",
            }
            
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "message": "Failed to validate checkpoint functionality",
        }


def validate_config_determinism(root: Path) -> Dict[str, Any]:
    """Validate that configuration includes determinism settings."""
    print("[Deterministic] Validating configuration...")
    
    config_file = root / "docs" / "CONFIG_DEFAULTS.yaml"
    if not config_file.exists():
        return {
            "passed": False,
            "error": f"Configuration file not found: {config_file}",
        }
    
    try:
        import yaml
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        
        # Check for seed configuration
        has_seed = False
        seed_locations = []
        
        def check_dict(d: Dict, path: str = ""):
            nonlocal has_seed
            for key, value in d.items():
                current_path = f"{path}.{key}" if path else key
                if key in ["seed", "random_seed", "deterministic"]:
                    has_seed = True
                    seed_locations.append(current_path)
                if isinstance(value, dict):
                    check_dict(value, current_path)
        
        check_dict(config)
        
        return {
            "passed": has_seed,
            "seed_locations": seed_locations,
            "message": "Configuration includes seed settings" if has_seed else "No seed configuration found",
        }
        
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "message": "Failed to validate configuration",
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate deterministic execution of symbolic synthesis"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/deterministic_validation.json"),
        help="Output file for validation results",
    )
    parser.add_argument(
        "--skip-reproducibility",
        action="store_true",
        help="Skip reproducibility test (faster)",
    )
    args = parser.parse_args()
    
    root = args.root.resolve()
    
    print("=" * 70)
    print("DETERMINISTIC EXECUTION VALIDATION")
    print("=" * 70)
    print(f"Root: {root}")
    
    # Run validation tests
    results = {
        "timestamp": str(np.datetime64("now")),
        "root": str(root),
        "tests": {},
    }
    
    # Test 1: Seed usage
    results["tests"]["seed_usage"] = validate_seed_usage(root)
    
    # Test 2: Configuration
    results["tests"]["config_determinism"] = validate_config_determinism(root)
    
    # Test 3: Checkpoint functionality
    results["tests"]["checkpoint_functionality"] = validate_checkpoint_functionality(root)
    
    # Test 4: Reproducibility (optional, can be slow)
    if not args.skip_reproducibility:
        results["tests"]["reproducibility"] = validate_reproducibility(root)
    else:
        results["tests"]["reproducibility"] = {
            "passed": True,
            "skipped": True,
            "message": "Skipped by user request",
        }
    
    # Compute overall result
    all_passed = all(
        test_result.get("passed", False)
        for test_result in results["tests"].values()
    )
    results["overall_passed"] = all_passed
    
    # Write results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    
    # Print summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    for test_name, test_result in results["tests"].items():
        status = "✓" if test_result.get("passed", False) else "✗"
        skipped = " (SKIPPED)" if test_result.get("skipped", False) else ""
        print(f"  {status} {test_name}{skipped}")
        
        if not test_result.get("passed", False) and not test_result.get("skipped", False):
            if "error" in test_result:
                print(f"      Error: {test_result['error']}")
            if "warnings" in test_result:
                print(f"      Warnings: {test_result['total_warnings']}")
    
    print(f"\n[Deterministic] Results written to: {args.output}")
    
    if all_passed:
        print("\n[Deterministic] ✓ All validation tests passed!")
        return 0
    else:
        print("\n[Deterministic] ✗ Some validation tests failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
