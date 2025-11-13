"""Automatic rule discovery from e-graphs and successful programs."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage

from .engine import EGraph, RewriteRule

LOGGER = logging.getLogger("arc.symbolic.egraph.rule_miner")


class RuleMiner:
    """Mine rewrite rules from e-graphs and program collections"""
    
    def __init__(
        self,
        min_support: int = 3,
        min_utility: float = 0.1,
    ):
        """
        Initialize the rule miner.
        
        Args:
            min_support: Minimum number of occurrences for a rule to be considered
            min_utility: Minimum utility score for a rule to be kept
        """
        self.min_support = min_support
        self.min_utility = min_utility
    
    def mine_rules_from_egraph(
        self,
        egraph: EGraph,
        min_support: Optional[int] = None
    ) -> List[RewriteRule]:
        """
        Mine rewrite rules from an e-graph's rewrite history.
        
        Args:
            egraph: E-graph with rewrite history
            min_support: Override minimum support threshold
            
        Returns:
            List of discovered rewrite rules
        """
        support_threshold = min_support or self.min_support
        
        # Analyze rewrite history to find frequent patterns
        rule_applications: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        
        for rewrite in egraph._history:
            rule_applications[rewrite.rule].append(
                (rewrite.source_signature, rewrite.target_signature)
            )
        
        # Find rules with sufficient support
        discovered_rules: List[RewriteRule] = []
        
        for rule_name, applications in rule_applications.items():
            if len(applications) >= support_threshold:
                # Rule has sufficient support
                LOGGER.debug(
                    "Rule %s has %d applications (threshold=%d)",
                    rule_name,
                    len(applications),
                    support_threshold
                )
                # Note: We don't create new rules here as we'd need the actual
                # transformation function. This is a placeholder for future enhancement.
        
        return discovered_rules
    
    def mine_rules_from_programs(
        self,
        programs: List[Program],
        min_support: Optional[int] = None
    ) -> List[RewriteRule]:
        """
        Mine rewrite rules from a collection of successful programs.
        
        Looks for common transformation patterns that could be generalized.
        
        Args:
            programs: List of successful programs
            min_support: Override minimum support threshold
            
        Returns:
            List of discovered rewrite rules
        """
        support_threshold = min_support or self.min_support
        
        # Find common stage patterns
        pattern_counter: Counter[Tuple[str, ...]] = Counter()
        
        for program in programs:
            # Extract operator sequences
            operators = tuple(stage.operator for stage in program.stages)
            
            # Count subsequences of length 2-4
            for length in range(2, min(5, len(operators) + 1)):
                for i in range(len(operators) - length + 1):
                    pattern = operators[i:i + length]
                    pattern_counter[pattern] += 1
        
        # Find patterns with sufficient support
        discovered_rules: List[RewriteRule] = []
        
        for pattern, count in pattern_counter.items():
            if count >= support_threshold:
                LOGGER.debug(
                    "Pattern %s found %d times (threshold=%d)",
                    pattern,
                    count,
                    support_threshold
                )
                # Note: Creating actual rewrite rules would require
                # analyzing the transformation semantics
        
        return discovered_rules
    
    def validate_rule_soundness(
        self,
        rule: RewriteRule,
        validation_examples: List[Tuple[Any, Any]]
    ) -> bool:
        """
        Validate that a rule is sound (preserves semantics).
        
        Args:
            rule: Rule to validate
            validation_examples: List of (input, output) grid pairs
            
        Returns:
            True if rule is sound, False otherwise
        """
        # Placeholder: Full validation would require executing programs
        # on validation examples and checking equivalence
        
        if not rule.enabled:
            return False
        
        # Basic validation: check if rule has been applied successfully
        if hasattr(rule, 'applications') and hasattr(rule, 'successes'):
            if rule.applications > 0:
                success_rate = rule.successes / rule.applications
                return success_rate > 0.5
        
        # Default to accepting the rule
        return True
    
    def estimate_rule_utility(
        self,
        rule: RewriteRule,
        historical_tasks: Optional[List[Any]] = None
    ) -> float:
        """
        Estimate the utility of a rule based on historical performance.
        
        Args:
            rule: Rule to evaluate
            historical_tasks: Optional list of historical tasks
            
        Returns:
            Utility score (0.0 to 1.0)
        """
        # Base utility on rule effectiveness
        if hasattr(rule, 'applications') and hasattr(rule, 'successes'):
            if rule.applications > 0:
                effectiveness = rule.successes / rule.applications
                
                # Weight by number of applications
                application_weight = min(1.0, rule.applications / 10.0)
                
                return effectiveness * application_weight
        
        # Default utility for new rules
        return 0.5
    
    def discover_equivalence_patterns(
        self,
        programs: List[Program]
    ) -> List[Tuple[Program, Program]]:
        """
        Discover pairs of programs that might be equivalent.
        
        Uses heuristics like similar structure, same operators, etc.
        
        Args:
            programs: List of programs to analyze
            
        Returns:
            List of (program_a, program_b) pairs that might be equivalent
        """
        equivalence_candidates: List[Tuple[Program, Program]] = []
        
        # Group programs by operator signature
        signature_groups: Dict[Tuple[str, ...], List[Program]] = defaultdict(list)
        
        for program in programs:
            signature = tuple(stage.operator for stage in program.stages)
            signature_groups[signature].append(program)
        
        # Find programs with similar signatures
        for signature, group in signature_groups.items():
            if len(group) >= 2:
                # Programs with same operators might be equivalent
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        equivalence_candidates.append((group[i], group[j]))
        
        LOGGER.debug("Found %d equivalence candidates", len(equivalence_candidates))
        return equivalence_candidates
    
    def generalize_rule(
        self,
        specific_rule: RewriteRule,
        examples: List[Tuple[Program, Program]]
    ) -> Optional[RewriteRule]:
        """
        Generalize a specific rule based on examples.
        
        Args:
            specific_rule: Specific rule to generalize
            examples: List of (before, after) program pairs
            
        Returns:
            Generalized rule or None if generalization fails
        """
        # Placeholder: Full generalization would require anti-unification
        # and pattern matching
        
        if len(examples) < self.min_support:
            return None
        
        # For now, return the original rule
        return specific_rule


class RuleValidator:
    """Validate discovered rules for correctness and utility"""
    
    def __init__(self, interpreter: Optional[Any] = None):
        """
        Initialize the validator.
        
        Args:
            interpreter: Optional DSL interpreter for semantic validation
        """
        self.interpreter = interpreter
    
    def validate_semantic_equivalence(
        self,
        program_a: Program,
        program_b: Program,
        test_inputs: List[Any]
    ) -> bool:
        """
        Validate that two programs are semantically equivalent.
        
        Args:
            program_a: First program
            program_b: Second program
            test_inputs: List of test inputs
            
        Returns:
            True if programs are equivalent on all test inputs
        """
        if self.interpreter is None:
            LOGGER.warning("No interpreter available for semantic validation")
            return False
        
        for test_input in test_inputs:
            try:
                output_a = self.interpreter.run(program_a, test_input)
                output_b = self.interpreter.run(program_b, test_input)
                
                if output_a != output_b:
                    return False
            except Exception as e:
                LOGGER.debug("Validation failed with error: %s", e)
                return False
        
        return True
    
    def validate_rule_preconditions(
        self,
        rule: RewriteRule,
        programs: List[Program]
    ) -> bool:
        """
        Validate that rule preconditions are correctly specified.
        
        Args:
            rule: Rule to validate
            programs: Programs to test against
            
        Returns:
            True if preconditions are valid
        """
        if rule.condition is None:
            return True
        
        # Test condition on sample programs
        for program in programs[:10]:  # Sample first 10
            try:
                result = rule.condition(program)
                if not isinstance(result, bool):
                    return False
            except Exception as e:
                LOGGER.debug("Precondition validation failed: %s", e)
                return False
        
        return True


__all__ = [
    "RuleMiner",
    "RuleValidator",
]
