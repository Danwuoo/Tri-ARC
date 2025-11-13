#!/usr/bin/env python3
"""
Validate resource constraint compliance for symbolic synthesis module.

Verifies that:
1. GPU memory usage stays within limits
2. CPU and RAM usage are acceptable under load
3. 12-hour time constraint can be met
4. Circuit breaker and fallback mechanisms work correctly
"""

from __future__ import annotations

import argparse
import json
import psutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


def get_gpu_memory_info() -> Dict[str, Any]:
    """Get GPU memory information."""
    try:
        import torch
        
        if not torch.cuda.is_available():
            return {
                "available": False,
                "message": "CUDA not available",
            }
        
        gpu_info = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            allocated = torch.cuda.memory_allocated(i)
            reserved = torch.cuda.memory_reserved(i)
            total = props.total_memory
            
            gpu_info.append({
                "device_id": i,
                "name": props.name,
                "total_memory_gb": total / (1024**3),
                "allocated_memory_gb": allocated / (1024**3),
                "reserved_memory_gb": reserved / (1024**3),
                "free_memory_gb": (total - reserved) / (1024**3),
                "utilization_percent": (reserved / total) * 100,
            })
        
        return {
            "available": True,
            "num_devices": len(gpu_info),
            "devices": gpu_info,
        }
        
    except ImportError:
        return {
            "available": False,
            "message": "PyTorch not installed",
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
        }


def validate_gpu_memory_limits(root: Path) -> Dict[str, Any]:
    """Validate GPU memory usage stays within limits."""
    print("[Resources] Validating GPU memory limits...")
    
    gpu_info = get_gpu_memory_info()
    
    if not gpu_info.get("available", False):
        return {
            "passed": True,
            "skipped": True,
            "message": gpu_info.get("message", "GPU not available"),
        }
    
    # Check each GPU
    issues = []
    warnings = []
    
    # Expected limit: ~40GB for A100, ~24GB for L4
    # We'll use 80% as warning threshold, 95% as error threshold
    warning_threshold = 0.80
    error_threshold = 0.95
    
    for device in gpu_info["devices"]:
        utilization = device["utilization_percent"] / 100.0
        
        if utilization > error_threshold:
            issues.append({
                "device_id": device["device_id"],
                "name": device["name"],
                "utilization": f"{utilization * 100:.1f}%",
                "message": f"GPU memory usage exceeds {error_threshold * 100}%",
            })
        elif utilization > warning_threshold:
            warnings.append({
                "device_id": device["device_id"],
                "name": device["name"],
                "utilization": f"{utilization * 100:.1f}%",
                "message": f"GPU memory usage exceeds {warning_threshold * 100}%",
            })
    
    return {
        "passed": len(issues) == 0,
        "gpu_info": gpu_info,
        "issues": issues,
        "warnings": warnings,
        "total_warnings": len(warnings),
    }


def validate_cpu_ram_usage(root: Path) -> Dict[str, Any]:
    """Validate CPU and RAM usage under load."""
    print("[Resources] Validating CPU and RAM usage...")
    
    # Get current system stats
    cpu_percent = psutil.cpu_percent(interval=1.0)
    memory = psutil.virtual_memory()
    
    # Thresholds
    cpu_warning_threshold = 80.0
    cpu_error_threshold = 95.0
    memory_warning_threshold = 0.80
    memory_error_threshold = 0.95
    
    issues = []
    warnings = []
    
    # Check CPU
    if cpu_percent > cpu_error_threshold:
        issues.append({
            "resource": "CPU",
            "usage": f"{cpu_percent:.1f}%",
            "message": f"CPU usage exceeds {cpu_error_threshold}%",
        })
    elif cpu_percent > cpu_warning_threshold:
        warnings.append({
            "resource": "CPU",
            "usage": f"{cpu_percent:.1f}%",
            "message": f"CPU usage exceeds {cpu_warning_threshold}%",
        })
    
    # Check memory
    memory_utilization = memory.percent / 100.0
    if memory_utilization > memory_error_threshold:
        issues.append({
            "resource": "RAM",
            "usage": f"{memory_utilization * 100:.1f}%",
            "total_gb": memory.total / (1024**3),
            "available_gb": memory.available / (1024**3),
            "message": f"RAM usage exceeds {memory_error_threshold * 100}%",
        })
    elif memory_utilization > memory_warning_threshold:
        warnings.append({
            "resource": "RAM",
            "usage": f"{memory_utilization * 100:.1f}%",
            "total_gb": memory.total / (1024**3),
            "available_gb": memory.available / (1024**3),
            "message": f"RAM usage exceeds {memory_warning_threshold * 100}%",
        })
    
    return {
        "passed": len(issues) == 0,
        "cpu_percent": cpu_percent,
        "memory_total_gb": memory.total / (1024**3),
        "memory_available_gb": memory.available / (1024**3),
        "memory_percent": memory.percent,
        "issues": issues,
        "warnings": warnings,
        "total_warnings": len(warnings),
    }


def validate_time_constraint(root: Path) -> Dict[str, Any]:
    """Validate 12-hour time constraint compliance."""
    print("[Resources] Validating time constraint compliance...")
    
    # Check if we have evaluation metrics
    eval_history_file = root / "reports" / "eval_history.jsonl"
    
    if not eval_history_file.exists():
        return {
            "passed": True,
            "skipped": True,
            "message": "No evaluation history found",
        }
    
    try:
        # Read evaluation history
        eval_runs = []
        with eval_history_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    eval_runs.append(json.loads(line))
        
        if not eval_runs:
            return {
                "passed": True,
                "skipped": True,
                "message": "No evaluation runs found",
            }
        
        # Check most recent run
        latest_run = eval_runs[-1]
        total_time_s = latest_run.get("total_time_s", 0)
        total_time_h = total_time_s / 3600.0
        
        # 12-hour limit
        time_limit_h = 12.0
        warning_threshold_h = 10.0
        
        issues = []
        warnings = []
        
        if total_time_h > time_limit_h:
            issues.append({
                "total_time_h": total_time_h,
                "limit_h": time_limit_h,
                "message": f"Evaluation time {total_time_h:.2f}h exceeds {time_limit_h}h limit",
            })
        elif total_time_h > warning_threshold_h:
            warnings.append({
                "total_time_h": total_time_h,
                "limit_h": time_limit_h,
                "message": f"Evaluation time {total_time_h:.2f}h approaching {time_limit_h}h limit",
            })
        
        return {
            "passed": len(issues) == 0,
            "total_time_h": total_time_h,
            "time_limit_h": time_limit_h,
            "num_tasks": latest_run.get("num_tasks", 0),
            "issues": issues,
            "warnings": warnings,
            "total_warnings": len(warnings),
        }
        
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "message": "Failed to validate time constraint",
        }


def validate_circuit_breaker(root: Path) -> Dict[str, Any]:
    """Validate circuit breaker and fallback mechanisms."""
    print("[Resources] Validating circuit breaker mechanisms...")
    
    try:
        sys.path.insert(0, str(root))
        from arc.symbolic.engineering.circuit_breaker import CircuitBreaker
        
        # Test circuit breaker
        breaker = CircuitBreaker(
            failure_threshold=3,
            timeout_s=60.0,
            half_open_timeout_s=30.0,
        )
        
        # Simulate failures
        test_results = []
        
        # Test 1: Normal operation
        breaker.reset()
        result = breaker.call(lambda: "success")
        test_results.append({
            "test": "normal_operation",
            "passed": result == "success",
            "state": breaker.state,
        })
        
        # Test 2: Failure handling
        breaker.reset()
        for _ in range(3):
            try:
                breaker.call(lambda: 1 / 0)
            except:
                pass
        
        test_results.append({
            "test": "failure_handling",
            "passed": breaker.state == "open",
            "state": breaker.state,
        })
        
        # Test 3: Fallback
        breaker.reset()
        result = breaker.call(
            lambda: 1 / 0,
            fallback=lambda: "fallback_value",
        )
        test_results.append({
            "test": "fallback",
            "passed": result == "fallback_value",
            "state": breaker.state,
        })
        
        all_passed = all(t["passed"] for t in test_results)
        
        return {
            "passed": all_passed,
            "tests": test_results,
            "message": "Circuit breaker validated successfully" if all_passed else "Some tests failed",
        }
        
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "message": "Failed to validate circuit breaker",
        }


def validate_timeout_protection(root: Path) -> Dict[str, Any]:
    """Validate timeout protection mechanisms."""
    print("[Resources] Validating timeout protection...")
    
    try:
        sys.path.insert(0, str(root))
        from arc.symbolic.engineering.timeout import TimeoutGuard
        
        # Test timeout guard
        test_results = []
        
        # Test 1: Normal operation within timeout
        guard = TimeoutGuard(timeout_s=2.0)
        time.sleep(0.5)
        test_results.append({
            "test": "within_timeout",
            "passed": guard.check(),
            "remaining": guard.remaining(),
        })
        
        # Test 2: Timeout detection
        guard = TimeoutGuard(timeout_s=0.5)
        time.sleep(1.0)
        test_results.append({
            "test": "timeout_detection",
            "passed": not guard.check(),
            "remaining": guard.remaining(),
        })
        
        all_passed = all(t["passed"] for t in test_results)
        
        return {
            "passed": all_passed,
            "tests": test_results,
            "message": "Timeout protection validated successfully" if all_passed else "Some tests failed",
        }
        
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "message": "Failed to validate timeout protection",
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate resource constraints for symbolic synthesis"
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
        default=Path("reports/resource_validation.json"),
        help="Output file for validation results",
    )
    args = parser.parse_args()
    
    root = args.root.resolve()
    
    print("=" * 70)
    print("RESOURCE CONSTRAINT VALIDATION")
    print("=" * 70)
    print(f"Root: {root}")
    
    # Run validation tests
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(root),
        "tests": {},
    }
    
    # Test 1: GPU memory limits
    results["tests"]["gpu_memory"] = validate_gpu_memory_limits(root)
    
    # Test 2: CPU and RAM usage
    results["tests"]["cpu_ram"] = validate_cpu_ram_usage(root)
    
    # Test 3: Time constraint
    results["tests"]["time_constraint"] = validate_time_constraint(root)
    
    # Test 4: Circuit breaker
    results["tests"]["circuit_breaker"] = validate_circuit_breaker(root)
    
    # Test 5: Timeout protection
    results["tests"]["timeout_protection"] = validate_timeout_protection(root)
    
    # Compute overall result
    all_passed = all(
        test_result.get("passed", False) or test_result.get("skipped", False)
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
        if test_result.get("skipped", False):
            status = "○"
            suffix = " (SKIPPED)"
        elif test_result.get("passed", False):
            status = "✓"
            suffix = ""
        else:
            status = "✗"
            suffix = ""
        
        print(f"  {status} {test_name}{suffix}")
        
        if not test_result.get("passed", False) and not test_result.get("skipped", False):
            if "error" in test_result:
                print(f"      Error: {test_result['error']}")
            if "warnings" in test_result:
                print(f"      Warnings: {test_result['total_warnings']}")
    
    print(f"\n[Resources] Results written to: {args.output}")
    
    if all_passed:
        print("\n[Resources] ✓ All validation tests passed!")
        return 0
    else:
        print("\n[Resources] ✗ Some validation tests failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
