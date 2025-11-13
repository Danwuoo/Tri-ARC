"""Program repair and multi-solution arbitration.

This module implements constraint-based program repair for fixing
partially failing programs, and multi-solution arbitration for
ranking and selecting among multiple candidate solutions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.verification.cegis import Example


@dataclass
class ProgramEdit:
    """Represents an edit operation on a program.
    
    Attributes:
        edit_type: Type of edit ("insert", "delete", "replace", "reorder")
        location: Stage index where edit is applied
        content: New stage content (for insert/replace)
        cost: Cost of this edit operation
        metadata: Additional metadata about the edit
    """
    
    edit_type: str  # "insert", "delete", "replace", "reorder"
    location: int
    content: Optional[Stage] = None
    cost: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize ProgramEdit to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "edit_type": self.edit_type,
            "location": self.location,
            "content": str(self.content) if self.content else None,
            "cost": self.cost,
            "metadata": self.metadata,
        }


class ConstraintBasedRepairer:
    """Repairs programs that fail on some examples using constraint solving.
    
    The repairer attempts to find minimal edits to a program that will
    make it pass all examples. It uses constraint-based search to find
    valid repairs.
    
    Attributes:
        config: Configuration dictionary
        verifier: Program verifier for checking repairs
        synthesizer: Program synthesizer for generating repair candidates
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        verifier: Optional[Any] = None,
        synthesizer: Optional[Any] = None,
    ):
        """Initialize constraint-based repairer.
        
        Args:
            config: Configuration dictionary
            verifier: Program verifier (optional)
            synthesizer: Program synthesizer (optional)
        """
        self.config = config
        self.verifier = verifier
        self.synthesizer = synthesizer
        
        # Extract configuration
        repair_config = config.get("repair", {})
        self.max_repairs = repair_config.get("max_repairs", 5)
        self.max_edit_distance = repair_config.get("max_edit_distance", 3)
        self.allow_insert = repair_config.get("allow_insert", True)
        self.allow_delete = repair_config.get("allow_delete", True)
        self.allow_replace = repair_config.get("allow_replace", True)
        self.allow_reorder = repair_config.get("allow_reorder", False)
    
    def repair_program(
        self,
        program: Program,
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> List[Program]:
        """Repair a program that fails on some examples.
        
        Args:
            program: The program to repair
            failed_examples: Examples that the program fails on
            passed_examples: Examples that the program passes on
            
        Returns:
            List of repaired programs (may be empty if no repair found)
        """
        if not failed_examples:
            # No failures, no repair needed
            return [program]
        
        repairs = []
        
        # Try different repair strategies
        # Strategy 1: Single-stage replacement
        if self.allow_replace:
            replace_repairs = self._try_replace_stages(
                program, failed_examples, passed_examples
            )
            repairs.extend(replace_repairs)
        
        # Strategy 2: Insert new stage
        if self.allow_insert:
            insert_repairs = self._try_insert_stages(
                program, failed_examples, passed_examples
            )
            repairs.extend(insert_repairs)
        
        # Strategy 3: Delete stage
        if self.allow_delete:
            delete_repairs = self._try_delete_stages(
                program, failed_examples, passed_examples
            )
            repairs.extend(delete_repairs)
        
        # Strategy 4: Reorder stages
        if self.allow_reorder:
            reorder_repairs = self._try_reorder_stages(
                program, failed_examples, passed_examples
            )
            repairs.extend(reorder_repairs)
        
        # Return top repairs (sorted by quality)
        repairs = self._rank_repairs(repairs, failed_examples, passed_examples)
        return repairs[:self.max_repairs]
    
    def compute_minimal_edit(
        self,
        program: Program,
        target_behavior: Dict[Example, Any],
    ) -> Optional[ProgramEdit]:
        """Compute a minimal edit to achieve target behavior.
        
        Args:
            program: The program to edit
            target_behavior: Mapping from examples to desired outputs
            
        Returns:
            A ProgramEdit if found, None otherwise
        """
        # This is a simplified implementation
        # A full implementation would use constraint solving (SMT/SAT)
        
        # Try each possible single edit
        min_edit = None
        min_cost = float('inf')
        
        # Try replacing each stage
        for i in range(len(program.stages)):
            # Generate candidate replacements
            # (In practice, this would use the synthesizer)
            candidates = self._generate_stage_candidates(program, i)
            
            for candidate_stage in candidates:
                edit = ProgramEdit(
                    edit_type="replace",
                    location=i,
                    content=candidate_stage,
                    cost=1.0,
                )
                
                # Check if this edit achieves target behavior
                repaired = self.apply_edit(program, edit)
                if self._check_target_behavior(repaired, target_behavior):
                    if edit.cost < min_cost:
                        min_edit = edit
                        min_cost = edit.cost
        
        return min_edit
    
    def apply_edit(
        self,
        program: Program,
        edit: ProgramEdit,
    ) -> Program:
        """Apply an edit to a program.
        
        Args:
            program: The program to edit
            edit: The edit to apply
            
        Returns:
            The edited program
        """
        stages = list(program.stages)
        
        if edit.edit_type == "insert":
            if edit.content is None:
                raise ValueError("Insert edit requires content")
            stages.insert(edit.location, edit.content)
        
        elif edit.edit_type == "delete":
            if 0 <= edit.location < len(stages):
                stages.pop(edit.location)
        
        elif edit.edit_type == "replace":
            if edit.content is None:
                raise ValueError("Replace edit requires content")
            if 0 <= edit.location < len(stages):
                stages[edit.location] = edit.content
        
        elif edit.edit_type == "reorder":
            # Reorder requires metadata specifying new order
            new_order = edit.metadata.get("new_order", [])
            if new_order:
                stages = [stages[i] for i in new_order if 0 <= i < len(stages)]
        
        return Program(stages=tuple(stages))
    
    def _try_replace_stages(
        self,
        program: Program,
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> List[Program]:
        """Try replacing individual stages to fix failures.
        
        Args:
            program: The program to repair
            failed_examples: Examples that fail
            passed_examples: Examples that pass
            
        Returns:
            List of repaired programs
        """
        repairs = []
        
        for i in range(len(program.stages)):
            # Generate candidate replacements
            candidates = self._generate_stage_candidates(program, i)
            
            for candidate_stage in candidates:
                # Create repaired program
                stages = list(program.stages)
                stages[i] = candidate_stage
                repaired = Program(stages=tuple(stages))
                
                # Check if repair works
                if self._verify_repair(repaired, failed_examples, passed_examples):
                    repairs.append(repaired)
                    if len(repairs) >= self.max_repairs:
                        return repairs
        
        return repairs
    
    def _try_insert_stages(
        self,
        program: Program,
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> List[Program]:
        """Try inserting new stages to fix failures.
        
        Args:
            program: The program to repair
            failed_examples: Examples that fail
            passed_examples: Examples that pass
            
        Returns:
            List of repaired programs
        """
        repairs = []
        
        # Try inserting at each position
        for i in range(len(program.stages) + 1):
            # Generate candidate stages to insert
            candidates = self._generate_stage_candidates(program, i)
            
            for candidate_stage in candidates:
                # Create repaired program
                stages = list(program.stages)
                stages.insert(i, candidate_stage)
                repaired = Program(stages=tuple(stages))
                
                # Check if repair works
                if self._verify_repair(repaired, failed_examples, passed_examples):
                    repairs.append(repaired)
                    if len(repairs) >= self.max_repairs:
                        return repairs
        
        return repairs
    
    def _try_delete_stages(
        self,
        program: Program,
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> List[Program]:
        """Try deleting stages to fix failures.
        
        Args:
            program: The program to repair
            failed_examples: Examples that fail
            passed_examples: Examples that pass
            
        Returns:
            List of repaired programs
        """
        repairs = []
        
        # Try deleting each stage
        for i in range(len(program.stages)):
            # Create repaired program
            stages = list(program.stages)
            stages.pop(i)
            repaired = Program(stages=tuple(stages))
            
            # Check if repair works
            if self._verify_repair(repaired, failed_examples, passed_examples):
                repairs.append(repaired)
                if len(repairs) >= self.max_repairs:
                    return repairs
        
        return repairs
    
    def _try_reorder_stages(
        self,
        program: Program,
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> List[Program]:
        """Try reordering stages to fix failures.
        
        Args:
            program: The program to repair
            failed_examples: Examples that fail
            passed_examples: Examples that pass
            
        Returns:
            List of repaired programs
        """
        # This is a simplified implementation
        # A full implementation would try different permutations
        repairs = []
        
        # Try swapping adjacent stages
        for i in range(len(program.stages) - 1):
            stages = list(program.stages)
            stages[i], stages[i + 1] = stages[i + 1], stages[i]
            repaired = Program(stages=tuple(stages))
            
            if self._verify_repair(repaired, failed_examples, passed_examples):
                repairs.append(repaired)
                if len(repairs) >= self.max_repairs:
                    return repairs
        
        return repairs
    
    def _generate_stage_candidates(
        self,
        program: Program,
        position: int,
    ) -> List[Stage]:
        """Generate candidate stages for repair.
        
        Args:
            program: The program being repaired
            position: Position where stage will be inserted/replaced
            
        Returns:
            List of candidate stages
        """
        # This is a placeholder implementation
        # A full implementation would use the synthesizer to generate candidates
        candidates = []
        
        # For now, return empty list
        # In practice, this would query the synthesizer for relevant stages
        
        return candidates
    
    def _verify_repair(
        self,
        program: Program,
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> bool:
        """Verify that a repaired program works.
        
        Args:
            program: The repaired program
            failed_examples: Examples that originally failed
            passed_examples: Examples that originally passed
            
        Returns:
            True if repair is valid, False otherwise
        """
        if self.verifier is None:
            return False
        
        # Check that all originally failed examples now pass
        for example in failed_examples:
            result = self.verifier.verify(
                program, example.input_grid, example.output_grid
            )
            if not result.get("success", False):
                return False
        
        # Check that all originally passed examples still pass
        for example in passed_examples:
            result = self.verifier.verify(
                program, example.input_grid, example.output_grid
            )
            if not result.get("success", False):
                return False
        
        return True
    
    def _check_target_behavior(
        self,
        program: Program,
        target_behavior: Dict[Example, Any],
    ) -> bool:
        """Check if program achieves target behavior.
        
        Args:
            program: The program to check
            target_behavior: Mapping from examples to desired outputs
            
        Returns:
            True if target behavior is achieved, False otherwise
        """
        if self.verifier is None:
            return False
        
        for example, target_output in target_behavior.items():
            result = self.verifier.verify(
                program, example.input_grid, target_output
            )
            if not result.get("success", False):
                return False
        
        return True
    
    def _rank_repairs(
        self,
        repairs: List[Program],
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> List[Program]:
        """Rank repairs by quality.
        
        Args:
            repairs: List of repaired programs
            failed_examples: Examples that originally failed
            passed_examples: Examples that originally passed
            
        Returns:
            Sorted list of repairs (best first)
        """
        # Score each repair
        scored_repairs = []
        for repair in repairs:
            score = self._score_repair(repair, failed_examples, passed_examples)
            scored_repairs.append((score, repair))
        
        # Sort by score (descending)
        scored_repairs.sort(key=lambda x: x[0], reverse=True)
        
        return [repair for _, repair in scored_repairs]
    
    def _score_repair(
        self,
        program: Program,
        failed_examples: List[Example],
        passed_examples: List[Example],
    ) -> float:
        """Score a repaired program.
        
        Args:
            program: The repaired program
            failed_examples: Examples that originally failed
            passed_examples: Examples that originally passed
            
        Returns:
            Quality score (higher is better)
        """
        # Simple scoring: prefer shorter programs
        length_score = 1.0 / (len(program.stages) + 1)
        
        # Could add more sophisticated scoring here
        # - Complexity of stages
        # - Generalization potential
        # - Similarity to original program
        
        return length_score


class MultiSolutionArbitrator:
    """Arbitrates among multiple candidate solutions.
    
    When multiple solutions are available (e.g., original + repaired),
    this arbitrator ranks them and selects the best one(s).
    
    Attributes:
        config: Configuration dictionary
        verifier: Program verifier for checking solutions
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        verifier: Optional[Any] = None,
    ):
        """Initialize multi-solution arbitrator.
        
        Args:
            config: Configuration dictionary
            verifier: Program verifier (optional)
        """
        self.config = config
        self.verifier = verifier
        
        # Extract configuration
        arbitrator_config = config.get("multi_solution_arbitrator", {})
        self.diversity_weight = arbitrator_config.get("diversity_weight", 0.2)
        self.simplicity_weight = arbitrator_config.get("simplicity_weight", 0.3)
        self.correctness_weight = arbitrator_config.get("correctness_weight", 0.5)
    
    def arbitrate_solutions(
        self,
        solutions: List[Program],
        examples: List[Example],
    ) -> List[Tuple[Program, float]]:
        """Arbitrate among multiple solutions and rank them.
        
        Args:
            solutions: List of candidate programs
            examples: Examples to evaluate against
            
        Returns:
            List of (program, score) tuples, sorted by score (descending)
        """
        scored_solutions = []
        
        for solution in solutions:
            score = self.score_solution(solution, examples, {})
            scored_solutions.append((solution, score))
        
        # Sort by score (descending)
        scored_solutions.sort(key=lambda x: x[1], reverse=True)
        
        # Apply diversity consideration
        if self.diversity_weight > 0:
            scored_solutions = self._apply_diversity(scored_solutions)
        
        return scored_solutions
    
    def score_solution(
        self,
        program: Program,
        examples: List[Example],
        metadata: Dict[str, Any],
    ) -> float:
        """Score a single solution.
        
        Args:
            program: The program to score
            examples: Examples to evaluate against
            metadata: Additional metadata about the program
            
        Returns:
            Quality score (higher is better)
        """
        # Correctness score
        correctness = self._compute_correctness(program, examples)
        
        # Simplicity score (prefer shorter programs)
        simplicity = 1.0 / (len(program.stages) + 1)
        
        # Combine scores
        total_score = (
            self.correctness_weight * correctness +
            self.simplicity_weight * simplicity
        )
        
        return total_score
    
    def _compute_correctness(
        self,
        program: Program,
        examples: List[Example],
    ) -> float:
        """Compute correctness score for a program.
        
        Args:
            program: The program to evaluate
            examples: Examples to check
            
        Returns:
            Correctness score in [0, 1]
        """
        if not examples or self.verifier is None:
            return 0.0
        
        passed = 0
        for example in examples:
            result = self.verifier.verify(
                program, example.input_grid, example.output_grid
            )
            if result.get("success", False):
                passed += 1
        
        return passed / len(examples)
    
    def _apply_diversity(
        self,
        scored_solutions: List[Tuple[Program, float]],
    ) -> List[Tuple[Program, float]]:
        """Apply diversity consideration to solution ranking.
        
        Args:
            scored_solutions: List of (program, score) tuples
            
        Returns:
            Re-ranked list with diversity bonus
        """
        if len(scored_solutions) <= 1:
            return scored_solutions
        
        # Compute pairwise diversity
        diversity_adjusted = []
        
        for i, (program, score) in enumerate(scored_solutions):
            # Compute diversity bonus based on difference from other solutions
            diversity_bonus = 0.0
            
            for j, (other_program, _) in enumerate(scored_solutions):
                if i != j:
                    diversity = self._compute_diversity(program, other_program)
                    diversity_bonus += diversity
            
            # Normalize by number of comparisons
            if len(scored_solutions) > 1:
                diversity_bonus /= (len(scored_solutions) - 1)
            
            # Apply diversity weight
            adjusted_score = score + self.diversity_weight * diversity_bonus
            diversity_adjusted.append((program, adjusted_score))
        
        # Re-sort by adjusted score
        diversity_adjusted.sort(key=lambda x: x[1], reverse=True)
        
        return diversity_adjusted
    
    def _compute_diversity(
        self,
        program1: Program,
        program2: Program,
    ) -> float:
        """Compute diversity between two programs.
        
        Args:
            program1: First program
            program2: Second program
            
        Returns:
            Diversity score in [0, 1]
        """
        # Simple diversity: normalized edit distance
        len1 = len(program1.stages)
        len2 = len(program2.stages)
        
        # Count different stages
        max_len = max(len1, len2)
        if max_len == 0:
            return 0.0
        
        different = abs(len1 - len2)
        for i in range(min(len1, len2)):
            if program1.stages[i].operator != program2.stages[i].operator:
                different += 1
        
        return different / max_len
