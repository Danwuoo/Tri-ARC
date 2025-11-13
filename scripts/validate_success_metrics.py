"""Validate symbolic synthesis enhancements against success metrics.

This script validates that the enhancements meet the following success criteria:
- Pass@2 accuracy improved by 5-10%
- Average solve time reduced by 20-30%
- Memory usage within GPU limits
- Timeout rate reduced by 15-20%
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class SuccessMetricsValidator:
    """Validator for success metrics."""
    
    def __init__(
        self,
        baseline_results: Dict[str, Any],
        enhanced_results: Dict[str, Any],
    ):
        """Initialize validator.
        
        Args:
            baseline_results: Results from baseline configuration
            enhanced_results: Results from enhanced configuration
        """
        self.baseline = baseline_results
        self.enhanced = enhanced_results
        self.validations = []
    
    def validate_pass_at_2_improvement(
        self,
        min_improvement: float = 0.05,
        max_improvement: float = 0.10,
    ) -> bool:
        """Validate pass@2 accuracy improvement.
        
        Args:
            min_improvement: Minimum expected improvement (default: 5%)
            max_improvement: Maximum expected improvement (default: 10%)
            
        Returns:
            True if validation passes
        """
        baseline_accuracy = self.baseline.get("success_rate", 0)
        enhanced_accuracy = self.enhanced.get("success_rate", 0)
        
        improvement = enhanced_accuracy - baseline_accuracy
        improvement_pct = improvement * 100
        
        passed = min_improvement <= improvement <= max_improvement
        
        validation = {
            "metric": "pass@2_accuracy",
            "baseline": baseline_accuracy,
            "enhanced": enhanced_accuracy,
            "improvement": improvement,
            "improvement_pct": improvement_pct,
            "target_min": min_improvement,
            "target_max": max_improvement,
            "passed": passed,
            "message": (
                f"Pass@2 accuracy improved by {improvement_pct:.1f}% "
                f"(target: {min_improvement*100:.0f}-{max_improvement*100:.0f}%)"
            ),
        }
        
        self.validations.append(validation)
        
        if passed:
            logger.info(f"✓ {validation['message']}")
        else:
            logger.warning(f"✗ {validation['message']}")
        
        return passed
    
    def validate_solve_time_reduction(
        self,
        min_reduction: float = 0.20,
        max_reduction: float = 0.30,
    ) -> bool:
        """Validate average solve time reduction.
        
        Args:
            min_reduction: Minimum expected reduction (default: 20%)
            max_reduction: Maximum expected reduction (default: 30%)
            
        Returns:
            True if validation passes
        """
        baseline_time = self.baseline.get("avg_solve_time_s", 0)
        enhanced_time = self.enhanced.get("avg_solve_time_s", 0)
        
        if baseline_time == 0:
            logger.warning("Baseline solve time is 0, cannot validate reduction")
            return False
        
        reduction = (baseline_time - enhanced_time) / baseline_time
        reduction_pct = reduction * 100
        
        passed = min_reduction <= reduction <= max_reduction
        
        validation = {
            "metric": "avg_solve_time",
            "baseline": baseline_time,
            "enhanced": enhanced_time,
            "reduction": reduction,
            "reduction_pct": reduction_pct,
            "target_min": min_reduction,
            "target_max": max_reduction,
            "passed": passed,
            "message": (
                f"Avg solve time reduced by {reduction_pct:.1f}% "
                f"(target: {min_reduction*100:.0f}-{max_reduction*100:.0f}%)"
            ),
        }
        
        self.validations.append(validation)
        
        if passed:
            logger.info(f"✓ {validation['message']}")
        else:
            logger.warning(f"✗ {validation['message']}")
        
        return passed
    
    def validate_memory_usage(
        self,
        max_memory_mb: float = 16000,  # 16 GB
        max_gpu_memory_mb: float = 40000,  # 40 GB (A100)
    ) -> bool:
        """Validate memory usage within limits.
        
        Args:
            max_memory_mb: Maximum CPU memory in MB
            max_gpu_memory_mb: Maximum GPU memory in MB
            
        Returns:
            True if validation passes
        """
        enhanced_perf = self.enhanced.get("performance", {})
        
        memory_mb = enhanced_perf.get("memory_mb_max", 0)
        gpu_memory_mb = enhanced_perf.get("gpu_memory_mb_max", 0)
        
        memory_passed = memory_mb <= max_memory_mb
        gpu_passed = gpu_memory_mb <= max_gpu_memory_mb if gpu_memory_mb > 0 else True
        
        passed = memory_passed and gpu_passed
        
        validation = {
            "metric": "memory_usage",
            "memory_mb": memory_mb,
            "max_memory_mb": max_memory_mb,
            "memory_passed": memory_passed,
            "gpu_memory_mb": gpu_memory_mb,
            "max_gpu_memory_mb": max_gpu_memory_mb,
            "gpu_passed": gpu_passed,
            "passed": passed,
            "message": (
                f"Memory usage: {memory_mb:.0f} MB (limit: {max_memory_mb:.0f} MB), "
                f"GPU: {gpu_memory_mb:.0f} MB (limit: {max_gpu_memory_mb:.0f} MB)"
            ),
        }
        
        self.validations.append(validation)
        
        if passed:
            logger.info(f"✓ {validation['message']}")
        else:
            logger.warning(f"✗ {validation['message']}")
        
        return passed
    
    def validate_timeout_rate_reduction(
        self,
        min_reduction: float = 0.15,
        max_reduction: float = 0.20,
    ) -> bool:
        """Validate timeout rate reduction.
        
        Args:
            min_reduction: Minimum expected reduction (default: 15%)
            max_reduction: Maximum expected reduction (default: 20%)
            
        Returns:
            True if validation passes
        """
        baseline_total = self.baseline.get("total_tasks", 1)
        baseline_timeouts = self.baseline.get("failed_tasks", 0)
        baseline_timeout_rate = baseline_timeouts / baseline_total if baseline_total > 0 else 0
        
        enhanced_total = self.enhanced.get("total_tasks", 1)
        enhanced_timeouts = self.enhanced.get("failed_tasks", 0)
        enhanced_timeout_rate = enhanced_timeouts / enhanced_total if enhanced_total > 0 else 0
        
        if baseline_timeout_rate == 0:
            logger.warning("Baseline timeout rate is 0, cannot validate reduction")
            return False
        
        reduction = (baseline_timeout_rate - enhanced_timeout_rate) / baseline_timeout_rate
        reduction_pct = reduction * 100
        
        passed = min_reduction <= reduction <= max_reduction
        
        validation = {
            "metric": "timeout_rate",
            "baseline": baseline_timeout_rate,
            "enhanced": enhanced_timeout_rate,
            "reduction": reduction,
            "reduction_pct": reduction_pct,
            "target_min": min_reduction,
            "target_max": max_reduction,
            "passed": passed,
            "message": (
                f"Timeout rate reduced by {reduction_pct:.1f}% "
                f"(target: {min_reduction*100:.0f}-{max_reduction*100:.0f}%)"
            ),
        }
        
        self.validations.append(validation)
        
        if passed:
            logger.info(f"✓ {validation['message']}")
        else:
            logger.warning(f"✗ {validation['message']}")
        
        return passed
    
    def validate_all(self) -> bool:
        """Run all validations.
        
        Returns:
            True if all validations pass
        """
        logger.info("Running success metrics validation...")
        logger.info("")
        
        results = [
            self.validate_pass_at_2_improvement(),
            self.validate_solve_time_reduction(),
            self.validate_memory_usage(),
            self.validate_timeout_rate_reduction(),
        ]
        
        all_passed = all(results)
        
        logger.info("")
        if all_passed:
            logger.info("✓ All success metrics validated successfully!")
        else:
            logger.warning("✗ Some success metrics did not meet targets")
        
        return all_passed
    
    def generate_report(self, output_path: Path) -> None:
        """Generate validation report.
        
        Args:
            output_path: Path to save report
        """
        report_lines = [
            "# Success Metrics Validation Report",
            "",
            "## Summary",
            "",
        ]
        
        passed_count = sum(1 for v in self.validations if v["passed"])
        total_count = len(self.validations)
        
        report_lines.append(f"**{passed_count}/{total_count} metrics passed**")
        report_lines.append("")
        
        report_lines.extend([
            "## Detailed Results",
            "",
            "| Metric | Baseline | Enhanced | Change | Target | Status |",
            "|--------|----------|----------|--------|--------|--------|",
        ])
        
        for validation in self.validations:
            metric = validation["metric"]
            
            if metric == "pass@2_accuracy":
                baseline_val = f"{validation['baseline']:.2%}"
                enhanced_val = f"{validation['enhanced']:.2%}"
                change = f"+{validation['improvement_pct']:.1f}%"
                target = f"{validation['target_min']*100:.0f}-{validation['target_max']*100:.0f}%"
            elif metric == "avg_solve_time":
                baseline_val = f"{validation['baseline']:.2f}s"
                enhanced_val = f"{validation['enhanced']:.2f}s"
                change = f"-{validation['reduction_pct']:.1f}%"
                target = f"{validation['target_min']*100:.0f}-{validation['target_max']*100:.0f}%"
            elif metric == "memory_usage":
                baseline_val = "N/A"
                enhanced_val = f"{validation['memory_mb']:.0f} MB"
                change = "N/A"
                target = f"<{validation['max_memory_mb']:.0f} MB"
            elif metric == "timeout_rate":
                baseline_val = f"{validation['baseline']:.2%}"
                enhanced_val = f"{validation['enhanced']:.2%}"
                change = f"-{validation['reduction_pct']:.1f}%"
                target = f"{validation['target_min']*100:.0f}-{validation['target_max']*100:.0f}%"
            else:
                baseline_val = str(validation.get("baseline", "N/A"))
                enhanced_val = str(validation.get("enhanced", "N/A"))
                change = "N/A"
                target = "N/A"
            
            status = "✓ Pass" if validation["passed"] else "✗ Fail"
            
            report_lines.append(
                f"| {metric} | {baseline_val} | {enhanced_val} | {change} | {target} | {status} |"
            )
        
        report_lines.extend([
            "",
            "## Validation Details",
            "",
        ])
        
        for validation in self.validations:
            report_lines.append(f"### {validation['metric']}")
            report_lines.append("")
            report_lines.append(validation["message"])
            report_lines.append("")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(report_lines))
        logger.info(f"Validation report saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Validate success metrics")
    parser.add_argument(
        "--baseline",
        type=str,
        required=True,
        help="Path to baseline results JSON"
    )
    parser.add_argument(
        "--enhanced",
        type=str,
        required=True,
        help="Path to enhanced results JSON"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/validation/success_metrics.md",
        help="Output path for validation report"
    )
    
    args = parser.parse_args()
    
    # Load results
    logger.info(f"Loading baseline results from {args.baseline}")
    with open(args.baseline) as f:
        baseline_data = json.load(f)
    baseline_results = baseline_data.get("summary", baseline_data)
    
    logger.info(f"Loading enhanced results from {args.enhanced}")
    with open(args.enhanced) as f:
        enhanced_data = json.load(f)
    enhanced_results = enhanced_data.get("summary", enhanced_data)
    
    # Validate
    validator = SuccessMetricsValidator(baseline_results, enhanced_results)
    all_passed = validator.validate_all()
    
    # Generate report
    output_path = Path(args.output)
    validator.generate_report(output_path)
    
    # Save validation results as JSON
    json_path = output_path.with_suffix(".json")
    with json_path.open("w") as f:
        json.dump({
            "all_passed": all_passed,
            "validations": validator.validations,
        }, f, indent=2)
    
    # Exit with appropriate code
    exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
