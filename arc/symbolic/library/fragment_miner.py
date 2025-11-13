"""Fragment mining for DSL library growth.

This module implements fragment mining from successful programs using
anti-unification and frequency analysis.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage


@dataclass(frozen=True)
class ProgramFragment:
    """Represents a reusable program fragment extracted from successful programs.
    
    Attributes:
        id: Unique identifier for the fragment
        stages: Sequence of stages in the fragment
        parameters: List of parameter names that can be instantiated
        frequency: Number of times this fragment appears in the corpus
        complexity_reduction: Estimated complexity reduction when using this fragment
        applicability_score: Score indicating how broadly applicable this fragment is
        metadata: Additional metadata about the fragment
    """
    
    id: str
    stages: Tuple[Stage, ...]
    parameters: Tuple[str, ...] = field(default_factory=tuple)
    frequency: int = 1
    complexity_reduction: float = 0.0
    applicability_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self) -> int:
        return hash(self.id)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProgramFragment):
            return False
        return self.id == other.id


@dataclass(frozen=True)
class FragmentScore:
    """Scoring metrics for a program fragment.
    
    Attributes:
        utility: Overall utility score combining multiple factors
        generality: How general/reusable the fragment is (0-1)
        complexity_reduction: Estimated reduction in program complexity
        frequency: Number of occurrences in the corpus
    """
    
    utility: float
    generality: float
    complexity_reduction: float
    frequency: int
    
    def __lt__(self, other: FragmentScore) -> bool:
        """Compare scores for sorting (higher utility is better)."""
        return self.utility < other.utility
    
    def __le__(self, other: FragmentScore) -> bool:
        return self.utility <= other.utility
    
    def __gt__(self, other: FragmentScore) -> bool:
        return self.utility > other.utility
    
    def __ge__(self, other: FragmentScore) -> bool:
        return self.utility >= other.utility


@dataclass
class ProgramTemplate:
    """A generalized program template with holes for parameters.
    
    Attributes:
        stages: Sequence of stages, some may contain parameter placeholders
        parameters: Set of parameter names used in the template
        source_programs: Programs that were anti-unified to create this template
    """
    
    stages: Tuple[Stage, ...]
    parameters: Set[str] = field(default_factory=set)
    source_programs: List[Program] = field(default_factory=list)


class FragmentMiner:
    """Mines reusable fragments from successful programs.
    
    This class implements fragment mining using:
    - Frequency analysis to find common subsequences
    - Anti-unification to generalize program pairs
    - Utility scoring to rank fragments
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the fragment miner.
        
        Args:
            config: Configuration dictionary with optional keys:
                - min_frequency: Minimum frequency threshold (default: 2)
                - min_utility: Minimum utility score (default: 0.1)
                - max_fragment_length: Maximum stages in a fragment (default: 5)
        """
        self.config = config or {}
        self.min_frequency = self.config.get("min_frequency", 2)
        self.min_utility = self.config.get("min_utility", 0.1)
        self.max_fragment_length = self.config.get("max_fragment_length", 5)
        
        # Cache for mined fragments
        self._fragment_cache: Dict[str, ProgramFragment] = {}
        self._next_fragment_id = 0
    
    def mine_fragments(
        self,
        successful_programs: List[Program],
        min_frequency: Optional[int] = None
    ) -> List[ProgramFragment]:
        """Mine high-frequency fragments from successful programs.
        
        Args:
            successful_programs: List of programs that successfully solved tasks
            min_frequency: Minimum frequency threshold (overrides config)
        
        Returns:
            List of program fragments sorted by utility score
        """
        if not successful_programs:
            return []
        
        threshold = min_frequency if min_frequency is not None else self.min_frequency
        
        # Extract all subsequences and count frequencies
        subsequence_counts: Counter[Tuple[Stage, ...]] = Counter()
        
        for program in successful_programs:
            for length in range(1, min(len(program.stages) + 1, self.max_fragment_length + 1)):
                for start in range(len(program.stages) - length + 1):
                    subsequence = program.stages[start:start + length]
                    subsequence_counts[subsequence] += 1
        
        # Filter by frequency and create fragments
        fragments = []
        for subsequence, frequency in subsequence_counts.items():
            if frequency >= threshold and len(subsequence) > 1:  # Only multi-stage fragments
                fragment_id = self._generate_fragment_id()
                
                # Score the fragment
                score = self.score_fragment(
                    subsequence,
                    frequency,
                    successful_programs
                )
                
                if score.utility >= self.min_utility:
                    fragment = ProgramFragment(
                        id=fragment_id,
                        stages=subsequence,
                        parameters=tuple(),  # No parameters for direct subsequences
                        frequency=frequency,
                        complexity_reduction=score.complexity_reduction,
                        applicability_score=score.generality,
                        metadata={"score": score}
                    )
                    fragments.append(fragment)
                    self._fragment_cache[fragment_id] = fragment
        
        # Sort by utility score (descending)
        fragments.sort(key=lambda f: f.metadata["score"].utility, reverse=True)
        
        return fragments
    
    def anti_unify(
        self,
        program_a: Program,
        program_b: Program
    ) -> Optional[ProgramTemplate]:
        """Perform anti-unification on two programs to find their most general common structure.
        
        Anti-unification finds the least general generalization (lgg) of two programs,
        creating a template with parameters where the programs differ.
        
        Args:
            program_a: First program
            program_b: Second program
        
        Returns:
            ProgramTemplate if a meaningful generalization exists, None otherwise
        """
        # Programs must have the same length for simple anti-unification
        if len(program_a.stages) != len(program_b.stages):
            return None
        
        if len(program_a.stages) == 0:
            return None
        
        generalized_stages = []
        parameters: Set[str] = set()
        param_counter = 0
        
        for stage_a, stage_b in zip(program_a.stages, program_b.stages):
            # If stages are identical, keep them as-is
            if self._stages_equal(stage_a, stage_b):
                generalized_stages.append(stage_a)
            else:
                # If operators differ, cannot generalize
                if stage_a.operator != stage_b.operator:
                    return None
                
                # Generalize arguments
                if len(stage_a.arguments) != len(stage_b.arguments):
                    return None
                
                generalized_args = []
                for arg_a, arg_b in zip(stage_a.arguments, stage_b.arguments):
                    if arg_a == arg_b:
                        generalized_args.append(arg_a)
                    else:
                        # Create a parameter placeholder
                        param_name = f"?param_{param_counter}"
                        param_counter += 1
                        parameters.add(param_name)
                        generalized_args.append(param_name)
                
                generalized_stages.append(Stage(
                    operator=stage_a.operator,
                    arguments=tuple(generalized_args)
                ))
        
        # Only return template if we found at least one parameter
        # (otherwise it's just identical to the input programs)
        if not parameters:
            return None
        
        return ProgramTemplate(
            stages=tuple(generalized_stages),
            parameters=parameters,
            source_programs=[program_a, program_b]
        )
    
    def score_fragment(
        self,
        fragment: Tuple[Stage, ...],
        frequency: int,
        corpus: List[Program]
    ) -> FragmentScore:
        """Evaluate the utility of a program fragment.
        
        Args:
            fragment: The fragment to score
            frequency: Number of occurrences in the corpus
            corpus: Full corpus of programs for context
        
        Returns:
            FragmentScore with computed metrics
        """
        # Complexity reduction: longer fragments reduce more complexity
        fragment_length = len(fragment)
        complexity_reduction = float(fragment_length - 1)  # Replacing N stages with 1 macro
        
        # Generality: how many different programs contain this fragment
        programs_with_fragment = 0
        for program in corpus:
            if self._contains_subsequence(program.stages, fragment):
                programs_with_fragment += 1
        
        generality = programs_with_fragment / len(corpus) if corpus else 0.0
        
        # Utility combines frequency, complexity reduction, and generality
        # Normalize frequency by corpus size
        normalized_frequency = frequency / len(corpus) if corpus else 0.0
        
        utility = (
            0.4 * normalized_frequency +
            0.3 * (complexity_reduction / self.max_fragment_length) +
            0.3 * generality
        )
        
        return FragmentScore(
            utility=utility,
            generality=generality,
            complexity_reduction=complexity_reduction,
            frequency=frequency
        )
    
    def _generate_fragment_id(self) -> str:
        """Generate a unique fragment ID."""
        fragment_id = f"fragment_{self._next_fragment_id:04d}"
        self._next_fragment_id += 1
        return fragment_id
    
    def _stages_equal(self, stage_a: Stage, stage_b: Stage) -> bool:
        """Check if two stages are equal."""
        if stage_a.operator != stage_b.operator:
            return False
        if len(stage_a.arguments) != len(stage_b.arguments):
            return False
        return all(a == b for a, b in zip(stage_a.arguments, stage_b.arguments))
    
    def _contains_subsequence(
        self,
        sequence: Tuple[Stage, ...],
        subsequence: Tuple[Stage, ...]
    ) -> bool:
        """Check if sequence contains subsequence."""
        if len(subsequence) > len(sequence):
            return False
        
        for i in range(len(sequence) - len(subsequence) + 1):
            if all(
                self._stages_equal(sequence[i + j], subsequence[j])
                for j in range(len(subsequence))
            ):
                return True
        
        return False
