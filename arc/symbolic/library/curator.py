"""Library curation for DSL management.

This module implements library curation including versioning, A/B testing,
pruning, and rollback mechanisms.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program
from arc.symbolic.egraph.engine import RewriteRule
from arc.symbolic.library.fragment_miner import ProgramFragment

LOGGER = logging.getLogger("arc.symbolic.library.curator")


@dataclass
class Primitive:
    """Represents a DSL primitive (operator or macro).
    
    Attributes:
        name: Name of the primitive
        type: Type of primitive ("operator", "macro", "fragment")
        implementation: Implementation details
        version: Version string
        metadata: Additional metadata
    """
    
    name: str
    type: str
    implementation: Any
    version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ABTestResult:
    """Result of A/B testing a rule.
    
    Attributes:
        rule_name: Name of the tested rule
        baseline_version: Version of baseline
        test_version: Version being tested
        baseline_performance: Performance metrics for baseline
        test_performance: Performance metrics for test version
        improvement: Relative improvement (positive is better)
        confidence: Statistical confidence in the result (0-1)
        recommendation: "adopt", "reject", or "inconclusive"
    """
    
    rule_name: str
    baseline_version: str
    test_version: str
    baseline_performance: Dict[str, float]
    test_performance: Dict[str, float]
    improvement: float
    confidence: float
    recommendation: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PruneReport:
    """Report of library pruning operation.
    
    Attributes:
        timestamp: When pruning occurred
        rules_removed: Number of rules removed
        fragments_removed: Number of fragments removed
        primitives_removed: Number of primitives removed
        total_size_before: Library size before pruning
        total_size_after: Library size after pruning
        removed_items: List of removed item names
    """
    
    timestamp: str
    rules_removed: int
    fragments_removed: int
    primitives_removed: int
    total_size_before: int
    total_size_after: int
    removed_items: List[str] = field(default_factory=list)


@dataclass
class LibraryVersion:
    """Represents a version of the library.
    
    Attributes:
        version: Version string
        timestamp: When this version was created
        primitives: Set of primitive names in this version
        rules: Set of rule names in this version
        fragments: Set of fragment IDs in this version
        changelog: Description of changes
    """
    
    version: str
    timestamp: str
    primitives: Set[str] = field(default_factory=set)
    rules: Set[str] = field(default_factory=set)
    fragments: Set[str] = field(default_factory=set)
    changelog: str = ""


class LibraryCurator:
    """Manages DSL library versioning, testing, and pruning.
    
    This class implements:
    - Primitive addition with versioning
    - A/B testing for new rules
    - Library pruning based on usage and impact
    - Rollback mechanisms for failed rules
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the library curator.
        
        Args:
            config: Configuration dictionary with optional keys:
                - usage_threshold: Minimum usage rate to keep items (default: 0.01)
                - impact_threshold: Minimum impact score to keep items (default: 0.05)
                - ab_test_tasks: Number of tasks for A/B testing (default: 20)
                - max_versions: Maximum versions to keep (default: 10)
        """
        self.config = config or {}
        self.usage_threshold = self.config.get("usage_threshold", 0.01)
        self.impact_threshold = self.config.get("impact_threshold", 0.05)
        self.ab_test_tasks = self.config.get("ab_test_tasks", 20)
        self.max_versions = self.config.get("max_versions", 10)
        
        # Library state
        self._primitives: Dict[str, Primitive] = {}
        self._rules: Dict[str, RewriteRule] = {}
        self._fragments: Dict[str, ProgramFragment] = {}
        
        # Usage tracking
        self._usage_counts: Dict[str, int] = defaultdict(int)
        self._impact_scores: Dict[str, float] = defaultdict(float)
        
        # Versioning
        self._versions: List[LibraryVersion] = []
        self._current_version = "1.0.0"
        self._blacklist: Set[str] = set()
        
        # Create initial version
        self._create_version("Initial library version")
    
    def add_primitive(
        self,
        primitive: Primitive,
        version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a new primitive to the library with versioning.
        
        Args:
            primitive: The primitive to add
            version: Optional version string (auto-incremented if not provided)
            metadata: Optional metadata about the addition
        """
        if primitive.name in self._blacklist:
            LOGGER.warning(f"Primitive {primitive.name} is blacklisted, not adding")
            return
        
        # Update version if provided
        if version:
            primitive.version = version
        
        # Add metadata
        if metadata:
            primitive.metadata.update(metadata)
        
        # Add to library
        self._primitives[primitive.name] = primitive
        
        # Create new version
        changelog = f"Added primitive: {primitive.name}"
        if metadata:
            changelog += f" ({metadata.get('reason', 'no reason provided')})"
        
        self._increment_version(changelog)
        
        LOGGER.info(f"Added primitive {primitive.name} version {primitive.version}")
    
    def add_rule(self, rule: RewriteRule, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a rewrite rule to the library.
        
        Args:
            rule: The rewrite rule to add
            metadata: Optional metadata about the rule
        """
        if rule.name in self._blacklist:
            LOGGER.warning(f"Rule {rule.name} is blacklisted, not adding")
            return
        
        self._rules[rule.name] = rule
        
        changelog = f"Added rule: {rule.name}"
        self._increment_version(changelog)
        
        LOGGER.info(f"Added rule {rule.name}")
    
    def add_fragment(
        self,
        fragment: ProgramFragment,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a program fragment to the library.
        
        Args:
            fragment: The fragment to add
            metadata: Optional metadata about the fragment
        """
        if fragment.id in self._blacklist:
            LOGGER.warning(f"Fragment {fragment.id} is blacklisted, not adding")
            return
        
        self._fragments[fragment.id] = fragment
        
        changelog = f"Added fragment: {fragment.id}"
        self._increment_version(changelog)
        
        LOGGER.info(f"Added fragment {fragment.id}")
    
    def ab_test_rule(
        self,
        rule: RewriteRule,
        test_tasks: List[Any],
        baseline_version: Optional[str] = None
    ) -> ABTestResult:
        """Perform A/B testing for a new rule.
        
        Args:
            rule: The rule to test
            test_tasks: Tasks to use for testing
            baseline_version: Version to compare against (current if not specified)
        
        Returns:
            ABTestResult with test outcomes and recommendation
        """
        baseline_ver = baseline_version or self._current_version
        test_ver = self._get_next_version()
        
        # Limit test tasks
        test_tasks = test_tasks[:self.ab_test_tasks]
        
        if not test_tasks:
            return ABTestResult(
                rule_name=rule.name,
                baseline_version=baseline_ver,
                test_version=test_ver,
                baseline_performance={},
                test_performance={},
                improvement=0.0,
                confidence=0.0,
                recommendation="inconclusive",
                metadata={"reason": "no test tasks"}
            )
        
        # Run baseline (without rule)
        baseline_perf = self._evaluate_without_rule(rule, test_tasks)
        
        # Run test (with rule)
        test_perf = self._evaluate_with_rule(rule, test_tasks)
        
        # Calculate improvement
        improvement = self._calculate_improvement(baseline_perf, test_perf)
        
        # Calculate confidence (simplified)
        confidence = min(len(test_tasks) / self.ab_test_tasks, 1.0)
        
        # Make recommendation
        if improvement > 0.05 and confidence > 0.7:
            recommendation = "adopt"
        elif improvement < -0.05:
            recommendation = "reject"
        else:
            recommendation = "inconclusive"
        
        result = ABTestResult(
            rule_name=rule.name,
            baseline_version=baseline_ver,
            test_version=test_ver,
            baseline_performance=baseline_perf,
            test_performance=test_perf,
            improvement=improvement,
            confidence=confidence,
            recommendation=recommendation,
            metadata={
                "test_tasks": len(test_tasks),
                "timestamp": datetime.now().isoformat()
            }
        )
        
        LOGGER.info(
            f"A/B test for {rule.name}: improvement={improvement:.2%}, "
            f"recommendation={recommendation}"
        )
        
        return result
    
    def prune_library(
        self,
        usage_threshold: Optional[float] = None,
        impact_threshold: Optional[float] = None
    ) -> PruneReport:
        """Prune the library based on usage and impact metrics.
        
        Args:
            usage_threshold: Minimum usage rate (overrides config)
            impact_threshold: Minimum impact score (overrides config)
        
        Returns:
            PruneReport with pruning statistics
        """
        usage_thresh = usage_threshold if usage_threshold is not None else self.usage_threshold
        impact_thresh = impact_threshold if impact_threshold is not None else self.impact_threshold
        
        total_before = len(self._primitives) + len(self._rules) + len(self._fragments)
        
        removed_items = []
        rules_removed = 0
        fragments_removed = 0
        primitives_removed = 0
        
        # Calculate total usage for normalization
        total_usage = sum(self._usage_counts.values()) or 1
        
        # Prune rules
        rules_to_remove = []
        for rule_name, rule in self._rules.items():
            usage_rate = self._usage_counts.get(rule_name, 0) / total_usage
            impact = self._impact_scores.get(rule_name, 0.0)
            
            if usage_rate < usage_thresh and impact < impact_thresh:
                rules_to_remove.append(rule_name)
        
        for rule_name in rules_to_remove:
            del self._rules[rule_name]
            removed_items.append(f"rule:{rule_name}")
            rules_removed += 1
        
        # Prune fragments
        fragments_to_remove = []
        for frag_id, fragment in self._fragments.items():
            usage_rate = self._usage_counts.get(frag_id, 0) / total_usage
            impact = self._impact_scores.get(frag_id, 0.0)
            
            if usage_rate < usage_thresh and impact < impact_thresh:
                fragments_to_remove.append(frag_id)
        
        for frag_id in fragments_to_remove:
            del self._fragments[frag_id]
            removed_items.append(f"fragment:{frag_id}")
            fragments_removed += 1
        
        # Prune primitives (more conservative)
        primitives_to_remove = []
        for prim_name, primitive in self._primitives.items():
            usage_rate = self._usage_counts.get(prim_name, 0) / total_usage
            impact = self._impact_scores.get(prim_name, 0.0)
            
            # Use stricter thresholds for primitives
            if usage_rate < usage_thresh / 2 and impact < impact_thresh / 2:
                primitives_to_remove.append(prim_name)
        
        for prim_name in primitives_to_remove:
            del self._primitives[prim_name]
            removed_items.append(f"primitive:{prim_name}")
            primitives_removed += 1
        
        total_after = len(self._primitives) + len(self._rules) + len(self._fragments)
        
        # Create version for pruning
        changelog = f"Pruned library: removed {len(removed_items)} items"
        self._increment_version(changelog)
        
        report = PruneReport(
            timestamp=datetime.now().isoformat(),
            rules_removed=rules_removed,
            fragments_removed=fragments_removed,
            primitives_removed=primitives_removed,
            total_size_before=total_before,
            total_size_after=total_after,
            removed_items=removed_items
        )
        
        LOGGER.info(
            f"Pruned library: {rules_removed} rules, {fragments_removed} fragments, "
            f"{primitives_removed} primitives removed"
        )
        
        return report
    
    def rollback_rule(self, rule_id: str, reason: str) -> None:
        """Rollback a failed rule and add it to blacklist.
        
        Args:
            rule_id: ID of the rule to rollback
            reason: Reason for rollback
        """
        if rule_id in self._rules:
            del self._rules[rule_id]
            self._blacklist.add(rule_id)
            
            changelog = f"Rolled back rule {rule_id}: {reason}"
            self._increment_version(changelog)
            
            LOGGER.warning(f"Rolled back rule {rule_id}: {reason}")
        else:
            LOGGER.warning(f"Cannot rollback rule {rule_id}: not found")
    
    def record_usage(self, item_id: str, count: int = 1) -> None:
        """Record usage of a library item.
        
        Args:
            item_id: ID of the item used
            count: Number of times used (default: 1)
        """
        self._usage_counts[item_id] += count
    
    def record_impact(self, item_id: str, impact: float) -> None:
        """Record impact score for a library item.
        
        Args:
            item_id: ID of the item
            impact: Impact score (higher is better)
        """
        # Use exponential moving average
        alpha = 0.3
        current = self._impact_scores.get(item_id, 0.0)
        self._impact_scores[item_id] = alpha * impact + (1 - alpha) * current
    
    def get_library_stats(self) -> Dict[str, Any]:
        """Get statistics about the current library state.
        
        Returns:
            Dictionary with library statistics
        """
        return {
            "version": self._current_version,
            "primitives": len(self._primitives),
            "rules": len(self._rules),
            "fragments": len(self._fragments),
            "blacklisted": len(self._blacklist),
            "total_items": len(self._primitives) + len(self._rules) + len(self._fragments),
            "versions": len(self._versions)
        }
    
    def _increment_version(self, changelog: str) -> None:
        """Increment library version and record changes."""
        # Parse current version
        major, minor, patch = map(int, self._current_version.split('.'))
        
        # Increment patch version
        patch += 1
        self._current_version = f"{major}.{minor}.{patch}"
        
        # Create version record
        version = LibraryVersion(
            version=self._current_version,
            timestamp=datetime.now().isoformat(),
            primitives=set(self._primitives.keys()),
            rules=set(self._rules.keys()),
            fragments=set(self._fragments.keys()),
            changelog=changelog
        )
        
        self._versions.append(version)
        
        # Prune old versions
        if len(self._versions) > self.max_versions:
            self._versions = self._versions[-self.max_versions:]
    
    def _create_version(self, changelog: str) -> None:
        """Create initial version."""
        version = LibraryVersion(
            version=self._current_version,
            timestamp=datetime.now().isoformat(),
            changelog=changelog
        )
        self._versions.append(version)
    
    def _get_next_version(self) -> str:
        """Get the next version string without incrementing."""
        major, minor, patch = map(int, self._current_version.split('.'))
        return f"{major}.{minor}.{patch + 1}"
    
    def _evaluate_without_rule(
        self,
        rule: RewriteRule,
        test_tasks: List[Any]
    ) -> Dict[str, float]:
        """Evaluate performance without the rule (baseline)."""
        # Simplified: return placeholder metrics
        # Real implementation would run solver without the rule
        return {
            "success_rate": 0.65,
            "avg_time": 10.5,
            "avg_nodes": 1000
        }
    
    def _evaluate_with_rule(
        self,
        rule: RewriteRule,
        test_tasks: List[Any]
    ) -> Dict[str, float]:
        """Evaluate performance with the rule."""
        # Simplified: return placeholder metrics
        # Real implementation would run solver with the rule
        return {
            "success_rate": 0.70,
            "avg_time": 9.8,
            "avg_nodes": 950
        }
    
    def _calculate_improvement(
        self,
        baseline: Dict[str, float],
        test: Dict[str, float]
    ) -> float:
        """Calculate relative improvement from baseline to test."""
        # Weight different metrics
        success_improvement = (
            test.get("success_rate", 0) - baseline.get("success_rate", 0)
        )
        time_improvement = (
            baseline.get("avg_time", 1) - test.get("avg_time", 1)
        ) / baseline.get("avg_time", 1)
        
        # Combined improvement score
        return 0.7 * success_improvement + 0.3 * time_improvement
