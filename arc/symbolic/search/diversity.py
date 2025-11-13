"""Diversity control for program synthesis.

This module implements diversity control mechanisms to ensure that
candidate programs are sufficiently different from each other,
avoiding redundant exploration of similar solutions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.search.types import TrainingExample

logger = logging.getLogger(__name__)


class DiversityController:
    """Controller for managing diversity in candidate programs.
    
    This class provides methods to compute distances between programs
    and deduplicate candidates based on semantic and syntactic similarity.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the diversity controller.
        
        Args:
            config: Configuration dictionary with optional parameters:
                - semantic_threshold: Threshold for semantic similarity
                - syntactic_threshold: Threshold for syntactic similarity
                - use_semantic_distance: Whether to use semantic distance
                - use_edit_distance: Whether to use edit distance
        """
        self.config = config or {}
        self.semantic_threshold = self.config.get("semantic_threshold", 0.1)
        self.syntactic_threshold = self.config.get("syntactic_threshold", 3)
        self.use_semantic_distance = self.config.get("use_semantic_distance", True)
        self.use_edit_distance = self.config.get("use_edit_distance", True)
        
        logger.info(
            f"Initialized DiversityController with "
            f"semantic_threshold={self.semantic_threshold}, "
            f"syntactic_threshold={self.syntactic_threshold}"
        )
    
    def compute_semantic_distance(
        self,
        program_a: Program,
        program_b: Program,
        examples: List[TrainingExample],
        interpreter: Any = None,
    ) -> float:
        """Compute semantic distance between two programs.
        
        Semantic distance measures how differently two programs behave
        on the given examples. Programs that produce the same outputs
        have distance 0, while programs with completely different outputs
        have distance 1.
        
        Args:
            program_a: First program
            program_b: Second program
            examples: Training examples to evaluate on
            interpreter: DSL interpreter for program execution
            
        Returns:
            Semantic distance in [0, 1]
        """
        if not interpreter or not examples:
            # Without interpreter or examples, fall back to syntactic distance
            return self._normalized_edit_distance(program_a, program_b)
        
        # Execute both programs on all examples
        outputs_a = []
        outputs_b = []
        
        for example in examples:
            try:
                output_a = interpreter.run(program_a, example.input_grid)
                outputs_a.append(output_a)
            except Exception:
                outputs_a.append(None)
            
            try:
                output_b = interpreter.run(program_b, example.input_grid)
                outputs_b.append(output_b)
            except Exception:
                outputs_b.append(None)
        
        # Compute distance based on output differences
        differences = 0
        total = 0
        
        for output_a, output_b in zip(outputs_a, outputs_b):
            if output_a is None or output_b is None:
                # If either program failed, count as different
                differences += 1
            elif not self._grids_equal(output_a, output_b):
                differences += 1
            total += 1
        
        if total == 0:
            return 0.0
        
        return differences / total
    
    def compute_edit_distance(
        self,
        program_a: Program,
        program_b: Program,
    ) -> int:
        """Compute edit distance between two programs.
        
        Edit distance (Levenshtein distance) measures the minimum number
        of stage insertions, deletions, or substitutions needed to transform
        one program into another.
        
        Args:
            program_a: First program
            program_b: Second program
            
        Returns:
            Edit distance (number of operations)
        """
        stages_a = program_a.stages
        stages_b = program_b.stages
        
        m, n = len(stages_a), len(stages_b)
        
        # Create DP table
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        # Initialize base cases
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        
        # Fill DP table
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if self._stages_equal(stages_a[i - 1], stages_b[j - 1]):
                    # Stages are equal, no operation needed
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    # Take minimum of insert, delete, or substitute
                    dp[i][j] = 1 + min(
                        dp[i - 1][j],      # Delete from a
                        dp[i][j - 1],      # Insert into a
                        dp[i - 1][j - 1],  # Substitute
                    )
        
        return dp[m][n]
    
    def deduplicate_candidates(
        self,
        candidates: List[Program],
        examples: Optional[List[TrainingExample]] = None,
        interpreter: Any = None,
        threshold: Optional[float] = None,
    ) -> List[Program]:
        """Deduplicate candidates based on similarity.
        
        This method removes candidates that are too similar to each other,
        keeping only diverse programs.
        
        Args:
            candidates: List of candidate programs
            examples: Training examples for semantic distance
            interpreter: DSL interpreter for semantic distance
            threshold: Similarity threshold (uses config default if None)
            
        Returns:
            Deduplicated list of programs
        """
        if not candidates:
            return []
        
        threshold = threshold or self.semantic_threshold
        
        logger.info(
            f"Deduplicating {len(candidates)} candidates with threshold={threshold}"
        )
        
        # Keep track of selected programs
        selected = []
        
        for candidate in candidates:
            # Check if candidate is sufficiently different from all selected
            is_diverse = True
            
            for selected_program in selected:
                # Compute distance
                if self.use_semantic_distance and examples and interpreter:
                    distance = self.compute_semantic_distance(
                        candidate,
                        selected_program,
                        examples,
                        interpreter,
                    )
                elif self.use_edit_distance:
                    edit_dist = self.compute_edit_distance(candidate, selected_program)
                    distance = self._normalized_edit_distance(candidate, selected_program)
                else:
                    # No distance metric available, keep all candidates
                    distance = 1.0
                
                # Check if too similar
                if distance < threshold:
                    is_diverse = False
                    break
            
            if is_diverse:
                selected.append(candidate)
        
        logger.info(f"Deduplicated to {len(selected)} diverse candidates")
        return selected
    
    def compute_diversity_score(
        self,
        candidates: List[Program],
        examples: Optional[List[TrainingExample]] = None,
        interpreter: Any = None,
    ) -> float:
        """Compute overall diversity score for a set of candidates.
        
        Higher scores indicate more diverse candidate sets.
        
        Args:
            candidates: List of candidate programs
            examples: Training examples for semantic distance
            interpreter: DSL interpreter for semantic distance
            
        Returns:
            Diversity score in [0, 1]
        """
        if len(candidates) <= 1:
            return 0.0
        
        # Compute pairwise distances
        total_distance = 0.0
        num_pairs = 0
        
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                if self.use_semantic_distance and examples and interpreter:
                    distance = self.compute_semantic_distance(
                        candidates[i],
                        candidates[j],
                        examples,
                        interpreter,
                    )
                else:
                    distance = self._normalized_edit_distance(
                        candidates[i],
                        candidates[j],
                    )
                
                total_distance += distance
                num_pairs += 1
        
        if num_pairs == 0:
            return 0.0
        
        # Average pairwise distance
        return total_distance / num_pairs
    
    def select_diverse_subset(
        self,
        candidates: List[Program],
        k: int,
        examples: Optional[List[TrainingExample]] = None,
        interpreter: Any = None,
    ) -> List[Program]:
        """Select a diverse subset of k programs from candidates.
        
        This method uses a greedy algorithm to select programs that
        maximize diversity.
        
        Args:
            candidates: List of candidate programs
            k: Number of programs to select
            examples: Training examples for semantic distance
            interpreter: DSL interpreter for semantic distance
            
        Returns:
            List of k diverse programs
        """
        if len(candidates) <= k:
            return candidates
        
        logger.info(f"Selecting {k} diverse programs from {len(candidates)} candidates")
        
        # Start with a random program
        selected = [candidates[0]]
        remaining = candidates[1:]
        
        # Greedily add programs that maximize minimum distance to selected
        while len(selected) < k and remaining:
            best_candidate = None
            best_min_distance = -1.0
            
            for candidate in remaining:
                # Compute minimum distance to selected programs
                min_distance = float('inf')
                
                for selected_program in selected:
                    if self.use_semantic_distance and examples and interpreter:
                        distance = self.compute_semantic_distance(
                            candidate,
                            selected_program,
                            examples,
                            interpreter,
                        )
                    else:
                        distance = self._normalized_edit_distance(
                            candidate,
                            selected_program,
                        )
                    
                    min_distance = min(min_distance, distance)
                
                # Update best candidate
                if min_distance > best_min_distance:
                    best_min_distance = min_distance
                    best_candidate = candidate
            
            if best_candidate:
                selected.append(best_candidate)
                remaining.remove(best_candidate)
        
        logger.info(f"Selected {len(selected)} diverse programs")
        return selected
    
    def _stages_equal(self, stage_a: Stage, stage_b: Stage) -> bool:
        """Check if two stages are equal.
        
        Args:
            stage_a: First stage
            stage_b: Second stage
            
        Returns:
            True if stages are equal, False otherwise
        """
        return (
            stage_a.operator == stage_b.operator and
            stage_a.arguments == stage_b.arguments
        )
    
    def _grids_equal(self, grid1: Any, grid2: Any) -> bool:
        """Check if two grids are equal.
        
        Args:
            grid1: First grid
            grid2: Second grid
            
        Returns:
            True if grids are equal, False otherwise
        """
        try:
            import numpy as np
            return np.array_equal(grid1, grid2)
        except Exception:
            return grid1 == grid2
    
    def _normalized_edit_distance(
        self,
        program_a: Program,
        program_b: Program,
    ) -> float:
        """Compute normalized edit distance between programs.
        
        Args:
            program_a: First program
            program_b: Second program
            
        Returns:
            Normalized edit distance in [0, 1]
        """
        edit_dist = self.compute_edit_distance(program_a, program_b)
        max_len = max(len(program_a.stages), len(program_b.stages))
        
        if max_len == 0:
            return 0.0
        
        return edit_dist / max_len


__all__ = [
    "DiversityController",
]
