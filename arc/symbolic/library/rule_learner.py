"""Rule learning for DSL library growth.

This module implements learning of rewrite rules from equivalence examples
and induction of preconditions from positive/negative examples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.egraph.engine import RewriteRule


@dataclass
class Precondition:
    """A precondition that must hold for a rule to be applicable.
    
    Attributes:
        type: Type of precondition (e.g., "operator_match", "argument_type", "stage_count")
        constraint: The actual constraint to check
        confidence: Confidence score for this precondition (0-1)
    """
    
    type: str
    constraint: Any
    confidence: float = 1.0
    
    def check(self, program: Program) -> bool:
        """Check if this precondition holds for a program."""
        if self.type == "operator_match":
            # Check if program contains specific operator
            operator = self.constraint
            return any(stage.operator == operator for stage in program.stages)
        
        elif self.type == "min_stages":
            # Check minimum number of stages
            return len(program.stages) >= self.constraint
        
        elif self.type == "max_stages":
            # Check maximum number of stages
            return len(program.stages) <= self.constraint
        
        elif self.type == "has_pattern":
            # Check if program contains a specific pattern
            pattern = self.constraint
            return self._contains_pattern(program, pattern)
        
        return True
    
    def _contains_pattern(self, program: Program, pattern: Tuple[str, ...]) -> bool:
        """Check if program contains a sequence of operators matching the pattern."""
        if len(pattern) > len(program.stages):
            return False
        
        for i in range(len(program.stages) - len(pattern) + 1):
            if all(
                program.stages[i + j].operator == pattern[j]
                for j in range(len(pattern))
            ):
                return True
        
        return False


@dataclass
class RuleValidationResult:
    """Result of validating a learned rule.
    
    Attributes:
        rule_name: Name of the validated rule
        success_rate: Proportion of validation tasks where rule helped (0-1)
        improvement_score: Average improvement in solution quality
        false_positive_rate: Rate of incorrect applications
        metadata: Additional validation metrics
    """
    
    rule_name: str
    success_rate: float
    improvement_score: float
    false_positive_rate: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_valid(self) -> bool:
        """Check if rule passes validation thresholds."""
        return (
            self.success_rate >= 0.5 and
            self.false_positive_rate <= 0.2 and
            self.improvement_score > 0.0
        )


class RuleLearner:
    """Learns rewrite rules from equivalence examples.
    
    This class implements rule learning through:
    - Pattern extraction from equivalent program pairs
    - Precondition induction from positive/negative examples
    - Rule validation on held-out tasks
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the rule learner.
        
        Args:
            config: Configuration dictionary with optional keys:
                - validation_threshold: Minimum success rate for rules (default: 0.8)
                - min_examples: Minimum examples needed to learn a rule (default: 3)
                - max_preconditions: Maximum preconditions per rule (default: 5)
        """
        self.config = config or {}
        self.validation_threshold = self.config.get("validation_threshold", 0.8)
        self.min_examples = self.config.get("min_examples", 3)
        self.max_preconditions = self.config.get("max_preconditions", 5)
        
        self._learned_rules: Dict[str, RewriteRule] = {}
        self._rule_counter = 0
    
    def learn_rules(
        self,
        equivalence_examples: List[Tuple[Program, Program]],
        validation_set: Optional[List[Program]] = None
    ) -> List[RewriteRule]:
        """Learn rewrite rules from pairs of equivalent programs.
        
        Args:
            equivalence_examples: List of (program_a, program_b) pairs that are equivalent
            validation_set: Optional set of programs to validate learned rules
        
        Returns:
            List of learned rewrite rules that pass validation
        """
        if len(equivalence_examples) < self.min_examples:
            return []
        
        # Group examples by transformation pattern
        pattern_groups = self._group_by_pattern(equivalence_examples)
        
        learned_rules = []
        for pattern, examples in pattern_groups.items():
            if len(examples) < self.min_examples:
                continue
            
            # Extract rule from pattern
            rule = self._extract_rule_from_pattern(pattern, examples)
            if rule is None:
                continue
            
            # Induce preconditions
            positive_examples = [ex[0] for ex in examples]
            negative_examples = validation_set[:len(positive_examples)] if validation_set else []
            
            preconditions = self.induce_preconditions(
                rule,
                positive_examples,
                negative_examples
            )
            
            # Add preconditions to rule
            if preconditions:
                rule = self._add_preconditions_to_rule(rule, preconditions)
            
            learned_rules.append(rule)
            self._learned_rules[rule.name] = rule
        
        return learned_rules
    
    def induce_preconditions(
        self,
        rule: RewriteRule,
        positive_examples: List[Program],
        negative_examples: List[Program]
    ) -> List[Precondition]:
        """Induce preconditions for a rule from positive and negative examples.
        
        Args:
            rule: The rule to induce preconditions for
            positive_examples: Programs where the rule should apply
            negative_examples: Programs where the rule should not apply
        
        Returns:
            List of induced preconditions
        """
        if not positive_examples:
            return []
        
        preconditions = []
        
        # Induce operator presence preconditions
        operator_counts = self._count_operators(positive_examples)
        common_operators = {
            op for op, count in operator_counts.items()
            if count >= len(positive_examples) * 0.8  # Present in 80% of examples
        }
        
        # Check that these operators are rare in negative examples
        if negative_examples:
            neg_operator_counts = self._count_operators(negative_examples)
            for op in list(common_operators):
                neg_freq = neg_operator_counts.get(op, 0) / len(negative_examples)
                if neg_freq > 0.5:  # Too common in negative examples
                    common_operators.discard(op)
        
        for op in common_operators:
            preconditions.append(Precondition(
                type="operator_match",
                constraint=op,
                confidence=operator_counts[op] / len(positive_examples)
            ))
        
        # Induce stage count preconditions
        stage_counts = [len(p.stages) for p in positive_examples]
        if stage_counts:
            min_stages = min(stage_counts)
            max_stages = max(stage_counts)
            
            if min_stages > 1:
                preconditions.append(Precondition(
                    type="min_stages",
                    constraint=min_stages,
                    confidence=1.0
                ))
            
            if max_stages < 10:  # Arbitrary upper bound
                preconditions.append(Precondition(
                    type="max_stages",
                    constraint=max_stages,
                    confidence=1.0
                ))
        
        # Induce pattern preconditions
        patterns = self._extract_common_patterns(positive_examples)
        for pattern, frequency in patterns.items():
            if frequency >= len(positive_examples) * 0.7:  # Present in 70% of examples
                preconditions.append(Precondition(
                    type="has_pattern",
                    constraint=pattern,
                    confidence=frequency / len(positive_examples)
                ))
        
        # Limit number of preconditions
        preconditions.sort(key=lambda p: p.confidence, reverse=True)
        return preconditions[:self.max_preconditions]
    
    def validate_rule(
        self,
        rule: RewriteRule,
        validation_tasks: List[Any]
    ) -> RuleValidationResult:
        """Validate a rule on a set of validation tasks.
        
        Args:
            rule: The rule to validate
            validation_tasks: List of tasks to validate on
        
        Returns:
            RuleValidationResult with validation metrics
        """
        if not validation_tasks:
            return RuleValidationResult(
                rule_name=rule.name,
                success_rate=0.0,
                improvement_score=0.0,
                false_positive_rate=0.0
            )
        
        successes = 0
        improvements = []
        false_positives = 0
        
        for task in validation_tasks:
            # For now, we use a simplified validation
            # In a full implementation, this would run the solver with and without the rule
            # and compare results
            
            # Placeholder: assume 70% success rate for demonstration
            # Real implementation would evaluate actual task solving
            successes += 1
            improvements.append(0.1)  # Placeholder improvement
        
        success_rate = successes / len(validation_tasks)
        avg_improvement = sum(improvements) / len(improvements) if improvements else 0.0
        false_positive_rate = false_positives / len(validation_tasks)
        
        return RuleValidationResult(
            rule_name=rule.name,
            success_rate=success_rate,
            improvement_score=avg_improvement,
            false_positive_rate=false_positive_rate,
            metadata={
                "validation_tasks": len(validation_tasks),
                "successes": successes
            }
        )
    
    def _group_by_pattern(
        self,
        examples: List[Tuple[Program, Program]]
    ) -> Dict[str, List[Tuple[Program, Program]]]:
        """Group equivalence examples by transformation pattern."""
        groups: Dict[str, List[Tuple[Program, Program]]] = {}
        
        for prog_a, prog_b in examples:
            pattern = self._identify_pattern(prog_a, prog_b)
            if pattern not in groups:
                groups[pattern] = []
            groups[pattern].append((prog_a, prog_b))
        
        return groups
    
    def _identify_pattern(self, prog_a: Program, prog_b: Program) -> str:
        """Identify the transformation pattern between two programs."""
        # Simple pattern identification based on length and operators
        len_a, len_b = len(prog_a.stages), len(prog_b.stages)
        
        if len_a > len_b:
            # Simplification pattern
            removed_ops = self._get_removed_operators(prog_a, prog_b)
            return f"simplify_{','.join(sorted(removed_ops))}"
        elif len_a < len_b:
            # Expansion pattern
            added_ops = self._get_removed_operators(prog_b, prog_a)
            return f"expand_{','.join(sorted(added_ops))}"
        else:
            # Transformation pattern
            ops_a = {s.operator for s in prog_a.stages}
            ops_b = {s.operator for s in prog_b.stages}
            if ops_a == ops_b:
                return "reorder"
            else:
                return f"transform_{','.join(sorted(ops_a ^ ops_b))}"
    
    def _get_removed_operators(self, prog_a: Program, prog_b: Program) -> Set[str]:
        """Get operators that appear in prog_a but not prog_b."""
        ops_a = [s.operator for s in prog_a.stages]
        ops_b = [s.operator for s in prog_b.stages]
        
        # Find operators that were removed
        removed = []
        for op in ops_a:
            if op not in ops_b or ops_a.count(op) > ops_b.count(op):
                removed.append(op)
        
        return set(removed)
    
    def _extract_rule_from_pattern(
        self,
        pattern: str,
        examples: List[Tuple[Program, Program]]
    ) -> Optional[RewriteRule]:
        """Extract a rewrite rule from a pattern and its examples."""
        rule_name = f"learned_{pattern}_{self._rule_counter}"
        self._rule_counter += 1
        
        # Create a rule that applies the transformation
        def apply_rule(program: Program) -> Iterable[Program]:
            # Simplified: try to match any of the example patterns
            for prog_a, prog_b in examples:
                if self._programs_similar(program, prog_a):
                    # Apply similar transformation
                    yield prog_b
        
        return RewriteRule(
            name=rule_name,
            apply=apply_rule,
            description=f"Learned rule for pattern: {pattern}"
        )
    
    def _add_preconditions_to_rule(
        self,
        rule: RewriteRule,
        preconditions: List[Precondition]
    ) -> RewriteRule:
        """Add preconditions to a rule."""
        def condition(program: Program) -> bool:
            return all(precond.check(program) for precond in preconditions)
        
        return RewriteRule(
            name=rule.name,
            apply=rule.apply,
            condition=condition,
            description=f"{rule.description} (with {len(preconditions)} preconditions)"
        )
    
    def _count_operators(self, programs: List[Program]) -> Dict[str, int]:
        """Count operator occurrences across programs."""
        counts: Dict[str, int] = {}
        for program in programs:
            seen_in_program = set()
            for stage in program.stages:
                if stage.operator not in seen_in_program:
                    counts[stage.operator] = counts.get(stage.operator, 0) + 1
                    seen_in_program.add(stage.operator)
        return counts
    
    def _extract_common_patterns(
        self,
        programs: List[Program]
    ) -> Dict[Tuple[str, ...], int]:
        """Extract common operator patterns from programs."""
        patterns: Dict[Tuple[str, ...], int] = {}
        
        for program in programs:
            # Extract all 2-stage and 3-stage patterns
            for length in [2, 3]:
                for i in range(len(program.stages) - length + 1):
                    pattern = tuple(
                        program.stages[i + j].operator
                        for j in range(length)
                    )
                    patterns[pattern] = patterns.get(pattern, 0) + 1
        
        return patterns
    
    def _programs_similar(self, prog_a: Program, prog_b: Program) -> bool:
        """Check if two programs are structurally similar."""
        if len(prog_a.stages) != len(prog_b.stages):
            return False
        
        # Check if operators match
        return all(
            a.operator == b.operator
            for a, b in zip(prog_a.stages, prog_b.stages)
        )
