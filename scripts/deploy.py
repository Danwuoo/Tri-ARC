#!/usr/bin/env python3
"""
Main deployment orchestration script for Tri-ARC symbolic synthesis.

This script coordinates the full deployment process including:
- Creating deployment package
- Validating deterministic execution
- Checking resource constraints
- Running final validation
- Generating submission artifacts
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class DeploymentOrchestrator:
    """Orchestrates the deployment process."""
    
    def __init__(self, root: Path, output_dir: Path, skip_validation: bool = False):
        self.root = root.resolve()
        self.output_dir = output_dir.resolve()
        self.skip_validation = skip_validation
        self.results: Dict[str, Any] = {}
        
    def run_command(
        self,
        cmd: List[str],
        description: str,
        cwd: Path | None = None,
    ) -> bool:
        """Run a command and capture results."""
        print(f"\n[Deploy] {description}")
        print(f"[Deploy] Command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.root,
                capture_output=True,
                text=True,
                check=False,
            )
            
            if result.returncode == 0:
                print(f"[Deploy] ✓ {description} completed successfully")
                return True
            else:
                print(f"[Deploy] ✗ {description} failed")
                print(f"[Deploy] stdout: {result.stdout}")
                print(f"[Deploy] stderr: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[Deploy] ✗ {description} failed with exception: {e}")
            return False
    
    def create_deployment_package(self) -> bool:
        """Step 1: Create deployment package."""
        print("\n" + "=" * 70)
        print("STEP 1: Creating Deployment Package")
        print("=" * 70)
        
        cmd = [
            sys.executable,
            str(self.root / "scripts" / "create_deployment_package.py"),
            "--root", str(self.root),
            "--output-dir", str(self.output_dir),
            "--include-data",
        ]
        
        success = self.run_command(cmd, "Creating deployment package")
        self.results["package_created"] = success
        return success
    
    def validate_deterministic_execution(self) -> bool:
        """Step 2: Validate deterministic execution."""
        if self.skip_validation:
            print("\n[Deploy] Skipping deterministic execution validation")
            self.results["deterministic_validated"] = True
            return True
        
        print("\n" + "=" * 70)
        print("STEP 2: Validating Deterministic Execution")
        print("=" * 70)
        
        cmd = [
            sys.executable,
            str(self.root / "scripts" / "validate_deterministic_execution.py"),
            "--root", str(self.root),
            "--output", str(self.output_dir / "deterministic_validation.json"),
        ]
        
        success = self.run_command(cmd, "Validating deterministic execution")
        self.results["deterministic_validated"] = success
        return success
    
    def validate_resource_constraints(self) -> bool:
        """Step 3: Validate resource constraints."""
        if self.skip_validation:
            print("\n[Deploy] Skipping resource constraint validation")
            self.results["resources_validated"] = True
            return True
        
        print("\n" + "=" * 70)
        print("STEP 3: Validating Resource Constraints")
        print("=" * 70)
        
        cmd = [
            sys.executable,
            str(self.root / "scripts" / "validate_resource_constraints.py"),
            "--root", str(self.root),
            "--output", str(self.output_dir / "resource_validation.json"),
        ]
        
        success = self.run_command(cmd, "Validating resource constraints")
        self.results["resources_validated"] = success
        return success
    
    def run_final_validation(self) -> bool:
        """Step 4: Run final validation."""
        if self.skip_validation:
            print("\n[Deploy] Skipping final validation")
            self.results["final_validated"] = True
            return True
        
        print("\n" + "=" * 70)
        print("STEP 4: Running Final Validation")
        print("=" * 70)
        
        cmd = [
            sys.executable,
            str(self.root / "scripts" / "validate_success_metrics.py"),
            "--output", str(self.output_dir / "final_validation.json"),
        ]
        
        success = self.run_command(cmd, "Running final validation")
        self.results["final_validated"] = success
        return success
    
    def prepare_submission_artifacts(self) -> bool:
        """Step 5: Prepare submission artifacts."""
        print("\n" + "=" * 70)
        print("STEP 5: Preparing Submission Artifacts")
        print("=" * 70)
        
        cmd = [
            sys.executable,
            str(self.root / "scripts" / "prepare_submission_artifacts.py"),
            "--root", str(self.root),
            "--output-dir", str(self.output_dir),
        ]
        
        success = self.run_command(cmd, "Preparing submission artifacts")
        self.results["artifacts_prepared"] = success
        return success
    
    def generate_deployment_report(self) -> None:
        """Generate final deployment report."""
        print("\n" + "=" * 70)
        print("Generating Deployment Report")
        print("=" * 70)
        
        report = {
            "deployment_timestamp": datetime.now().isoformat(),
            "project_root": str(self.root),
            "output_directory": str(self.output_dir),
            "steps": self.results,
            "overall_success": all(self.results.values()),
        }
        
        report_path = self.output_dir / "deployment_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        
        print(f"\n[Deploy] Deployment report written to: {report_path}")
        
        # Print summary
        print("\n" + "=" * 70)
        print("DEPLOYMENT SUMMARY")
        print("=" * 70)
        
        for step, success in self.results.items():
            status = "✓" if success else "✗"
            print(f"  {status} {step}: {'PASSED' if success else 'FAILED'}")
        
        if report["overall_success"]:
            print("\n[Deploy] ✓ Deployment completed successfully!")
        else:
            print("\n[Deploy] ✗ Deployment completed with errors")
    
    def run(self) -> bool:
        """Run the full deployment process."""
        print("=" * 70)
        print("TRI-ARC SYMBOLIC SYNTHESIS DEPLOYMENT")
        print("=" * 70)
        print(f"Root: {self.root}")
        print(f"Output: {self.output_dir}")
        print(f"Skip validation: {self.skip_validation}")
        
        # Step 1: Create deployment package
        if not self.create_deployment_package():
            print("\n[Deploy] ✗ Failed to create deployment package")
            self.generate_deployment_report()
            return False
        
        # Step 2: Validate deterministic execution
        if not self.validate_deterministic_execution():
            print("\n[Deploy] ✗ Failed deterministic execution validation")
            self.generate_deployment_report()
            return False
        
        # Step 3: Validate resource constraints
        if not self.validate_resource_constraints():
            print("\n[Deploy] ✗ Failed resource constraint validation")
            self.generate_deployment_report()
            return False
        
        # Step 4: Run final validation
        if not self.run_final_validation():
            print("\n[Deploy] ✗ Failed final validation")
            self.generate_deployment_report()
            return False
        
        # Step 5: Prepare submission artifacts
        if not self.prepare_submission_artifacts():
            print("\n[Deploy] ✗ Failed to prepare submission artifacts")
            self.generate_deployment_report()
            return False
        
        # Generate final report
        self.generate_deployment_report()
        
        return all(self.results.values())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy Tri-ARC symbolic synthesis enhancements"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist/deployment"),
        help="Output directory for deployment artifacts",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation steps (for testing)",
    )
    args = parser.parse_args()
    
    orchestrator = DeploymentOrchestrator(
        root=args.root,
        output_dir=args.output_dir,
        skip_validation=args.skip_validation,
    )
    
    success = orchestrator.run()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
