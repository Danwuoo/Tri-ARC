"""Step normalization for commutative program stages."""

from __future__ import annotations

from typing import List, Set, Tuple

from arc.symbolic.dsl.types import Stage


class StepNormalizer:
    """Normalizes sequences of commutative program stages.
    
    This class identifies commutative operations and reorders them
    into a canonical form to reduce search space.
    """
    
    # Define which operators are known to be commutative with each other
    COMMUTATIVE_GROUPS = [
        # Color operations that don't depend on order
        {"paint_region", "fill_region"},
        # Independent object operations
        {"detect_objects", "select_object"},
    ]
    
    def __init__(self):
        """Initialize the StepNormalizer."""
        # Build a lookup for commutative pairs
        self._commutative_pairs: Set[Tuple[str, str]] = set()
        for group in self.COMMUTATIVE_GROUPS:
            ops = list(group)
            for i, op1 in enumerate(ops):
                for op2 in ops[i:]:
                    self._commutative_pairs.add((op1, op2))
                    self._commutative_pairs.add((op2, op1))
    
    def normalize_sequence(self, stages: List[Stage]) -> List[Stage]:
        """Normalize a sequence of stages by reordering commutative operations.
        
        Args:
            stages: List of stages to normalize
            
        Returns:
            Normalized list of stages with commutative operations in canonical order
        """
        if len(stages) <= 1:
            return stages
        
        # Find groups of consecutive commutative stages
        normalized = []
        i = 0
        
        while i < len(stages):
            # Find the extent of commutative group starting at i
            group_end = i + 1
            while group_end < len(stages):
                if self.detect_commutative_pairs(stages[group_end - 1], stages[group_end]):
                    group_end += 1
                else:
                    break
            
            # If we found a commutative group, normalize it
            if group_end > i + 1:
                group = stages[i:group_end]
                normalized_group = self.canonical_order(group)
                normalized.extend(normalized_group)
                i = group_end
            else:
                # Single non-commutative stage
                normalized.append(stages[i])
                i += 1
        
        return normalized
    
    def detect_commutative_pairs(self, stage_a: Stage, stage_b: Stage) -> bool:
        """Detect if two stages are commutative.
        
        Args:
            stage_a: First stage
            stage_b: Second stage
            
        Returns:
            True if the stages commute, False otherwise
        """
        # Check if operators are in known commutative pairs
        if (stage_a.operator, stage_b.operator) in self._commutative_pairs:
            return True
        
        # Additional heuristics for commutativity
        
        # Same operator with different arguments might commute
        if stage_a.operator == stage_b.operator:
            # Check if they operate on disjoint regions or objects
            if self._operate_on_disjoint_regions(stage_a, stage_b):
                return True
        
        # Operations that don't modify the grid commute with each other
        if self._is_read_only(stage_a) and self._is_read_only(stage_b):
            return True
        
        return False
    
    def canonical_order(self, commutative_stages: List[Stage]) -> List[Stage]:
        """Return canonical ordering of commutative stages.
        
        Args:
            commutative_stages: List of mutually commutative stages
            
        Returns:
            Stages in canonical order
        """
        # Sort by operator name first, then by arguments
        return sorted(
            commutative_stages,
            key=lambda s: (s.operator, self._stage_args_key(s))
        )
    
    def _operate_on_disjoint_regions(self, stage_a: Stage, stage_b: Stage) -> bool:
        """Check if two stages operate on disjoint regions.
        
        This is a heuristic check. A full implementation would need
        to analyze the actual regions being operated on.
        """
        # For now, assume stages with different region arguments are disjoint
        # This is a simplification
        
        # Check if both stages have region arguments
        has_region_a = any(
            hasattr(arg, '__class__') and arg.__class__.__name__ == 'Region'
            for arg in stage_a.arguments
        )
        has_region_b = any(
            hasattr(arg, '__class__') and arg.__class__.__name__ == 'Region'
            for arg in stage_b.arguments
        )
        
        if has_region_a and has_region_b:
            # If they have different region arguments, assume disjoint
            # This is conservative but safe
            return stage_a.arguments != stage_b.arguments
        
        return False
    
    def _is_read_only(self, stage: Stage) -> bool:
        """Check if a stage is read-only (doesn't modify the grid).
        
        Args:
            stage: Stage to check
            
        Returns:
            True if the stage is read-only
        """
        # Define read-only operators
        read_only_ops = {
            "detect_objects",
            "select_object",
            "region_where_colour",
            "get_colour",
            "count_objects",
            "measure_area",
        }
        
        return stage.operator in read_only_ops
    
    def _stage_args_key(self, stage: Stage) -> Tuple:
        """Create a sortable key from stage arguments.
        
        Args:
            stage: Stage to create key for
            
        Returns:
            Tuple that can be used for sorting
        """
        key_parts = []
        for arg in stage.arguments:
            if isinstance(arg, (int, str, bool)):
                key_parts.append((type(arg).__name__, arg))
            elif isinstance(arg, tuple):
                key_parts.append(("tuple", len(arg)))
            elif hasattr(arg, '__class__'):
                key_parts.append((arg.__class__.__name__, id(arg)))
            else:
                key_parts.append(("unknown", str(arg)))
        return tuple(key_parts)
    
    def add_commutative_group(self, operators: Set[str]) -> None:
        """Add a new group of commutative operators.
        
        Args:
            operators: Set of operator names that commute with each other
        """
        ops = list(operators)
        for i, op1 in enumerate(ops):
            for op2 in ops[i:]:
                self._commutative_pairs.add((op1, op2))
                self._commutative_pairs.add((op2, op1))
    
    def add_commutative_pair(self, op1: str, op2: str) -> None:
        """Add a specific commutative pair.
        
        Args:
            op1: First operator name
            op2: Second operator name
        """
        self._commutative_pairs.add((op1, op2))
        self._commutative_pairs.add((op2, op1))
