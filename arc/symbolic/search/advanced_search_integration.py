"""Integration module for advanced search strategies.

This module provides a unified interface for using advanced search strategies
including sketch-guided synthesis, abstract interpretation, PCFG, MCTS, and
diversity control.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from arc.symbolic.dsl.types import Program
from arc.symbolic.search.abstract_interpreter import AbstractGrid, AbstractInterpreter
from arc.symbolic.search.budget import SearchBudget
from arc.symbolic.search.diversity import DiversityController
from arc.symbolic.search.mcts import MCTSSearcher
from arc.symbolic.search.neural_models import (
    FrequencyBasedPolicyModel,
    HeuristicValueModel,
    UniformPolicyModel,
)
from arc.symbolic.search.pcfg import PCFG, ProbabilisticEnumerator
from arc.symbolic.search.sketch_guided import SketchGuidedSynthesizer
from arc.symbolic.search.types import TrainingExample

logger = logging.getLogger(__name__)


class AdvancedSearchCoordinator:
    """Coordinator for advanced search strategies.
    
    This class manages the integration of multiple advanced search strategies
    and provides a unified interface for the solver.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the advanced search coordinator.
        
        Args:
            config: Configuration dictionary with optional parameters:
                - enable_sketch_guided: Enable sketch-guided synthesis
                - enable_abstract_interpretation: Enable abstract interpretation
                - enable_pcfg: Enable PCFG-based search
                - enable_mcts: Enable MCTS search
                - enable_diversity_control: Enable diversity control
                - search_strategy: Primary search strategy to use
        """
        self.config = config or {}
        
        # Feature flags
        self.enable_sketch_guided = self.config.get("enable_sketch_guided", False)
        self.enable_abstract_interpretation = self.config.get("enable_abstract_interpretation", False)
        self.enable_pcfg = self.config.get("enable_pcfg", False)
        self.enable_mcts = self.config.get("enable_mcts", False)
        self.enable_diversity_control = self.config.get("enable_diversity_control", True)
        
        # Primary search strategy
        self.search_strategy = self.config.get("search_strategy", "beam")
        
        # Initialize components
        self.sketch_synthesizer = None
        self.abstract_interpreter = None
        self.pcfg_enumerator = None
        self.mcts_searcher = None
        self.diversity_controller = None
        
        if self.enable_sketch_guided:
            self.sketch_synthesizer = SketchGuidedSynthesizer(
                self.config.get("sketch_guided", {})
            )
            logger.info("Enabled sketch-guided synthesis")
        
        if self.enable_abstract_interpretation:
            self.abstract_interpreter = AbstractInterpreter(
                self.config.get("abstract_interpretation", {})
            )
            logger.info("Enabled abstract interpretation")
        
        if self.enable_pcfg:
            self.pcfg_enumerator = ProbabilisticEnumerator(
                self.config.get("pcfg", {})
            )
            logger.info("Enabled PCFG-based search")
        
        if self.enable_mcts:
            self.mcts_searcher = MCTSSearcher(
                self.config.get("mcts", {})
            )
            logger.info("Enabled MCTS search")
        
        if self.enable_diversity_control:
            self.diversity_controller = DiversityController(
                self.config.get("diversity", {})
            )
            logger.info("Enabled diversity control")
        
        logger.info(
            f"Initialized AdvancedSearchCoordinator with strategy={self.search_strategy}"
        )
    
    def search(
        self,
        examples: List[TrainingExample],
        budget: SearchBudget,
        interpreter: Any = None,
    ) -> List[Program]:
        """Perform search using the configured strategy.
        
        Args:
            examples: Training examples to satisfy
            budget: Search budget
            interpreter: DSL interpreter for program execution
            
        Returns:
            List of candidate programs
        """
        logger.info(f"Starting advanced search with strategy={self.search_strategy}")
        
        candidates = []
        
        # Dispatch to appropriate search strategy
        if self.search_strategy == "sketch_guided" and self.sketch_synthesizer:
            candidates = self._search_sketch_guided(examples, budget, interpreter)
        elif self.search_strategy == "pcfg" and self.pcfg_enumerator:
            candidates = self._search_pcfg(examples, budget, interpreter)
        elif self.search_strategy == "mcts" and self.mcts_searcher:
            candidates = self._search_mcts(examples, budget, interpreter)
        else:
            logger.warning(f"Strategy {self.search_strategy} not available, using default")
            return []
        
        # Apply abstract interpretation for pruning if enabled
        if self.enable_abstract_interpretation and self.abstract_interpreter and examples:
            candidates = self._prune_with_abstract_interpretation(
                candidates, examples, interpreter
            )
        
        # Apply diversity control if enabled
        if self.enable_diversity_control and self.diversity_controller:
            candidates = self.diversity_controller.deduplicate_candidates(
                candidates, examples, interpreter
            )
        
        logger.info(f"Advanced search completed with {len(candidates)} candidates")
        return candidates
    
    def train_from_successful_programs(
        self,
        successful_programs: List[Program],
    ) -> None:
        """Train advanced search components from successful programs.
        
        Args:
            successful_programs: List of successful programs
        """
        logger.info(f"Training from {len(successful_programs)} successful programs")
        
        # Train sketch library
        if self.sketch_synthesizer:
            programs_with_stats = [(p, 1.0, True) for p in successful_programs]
            self.sketch_synthesizer.extract_sketch_library(programs_with_stats)
        
        # Train PCFG
        if self.pcfg_enumerator:
            self.pcfg_enumerator.train_pcfg(successful_programs)
        
        logger.info("Training completed")
    
    def _search_sketch_guided(
        self,
        examples: List[TrainingExample],
        budget: SearchBudget,
        interpreter: Any,
    ) -> List[Program]:
        """Perform sketch-guided search.
        
        Args:
            examples: Training examples
            budget: Search budget
            interpreter: DSL interpreter
            
        Returns:
            List of candidate programs
        """
        if not self.sketch_synthesizer:
            return []
        
        # Get best sketches from library
        sketches = self.sketch_synthesizer.get_best_sketches(top_k=5)
        
        if not sketches:
            logger.info("No sketches available, skipping sketch-guided search")
            return []
        
        # Synthesize from each sketch
        all_candidates = []
        for sketch in sketches:
            candidates = self.sketch_synthesizer.synthesize_from_sketch(
                sketch, examples, budget, interpreter
            )
            all_candidates.extend(candidates)
            
            if len(all_candidates) >= budget.max_candidates:
                break
        
        return all_candidates[:budget.max_candidates]
    
    def _search_pcfg(
        self,
        examples: List[TrainingExample],
        budget: SearchBudget,
        interpreter: Any,
    ) -> List[Program]:
        """Perform PCFG-based search.
        
        Args:
            examples: Training examples
            budget: Search budget
            interpreter: DSL interpreter
            
        Returns:
            List of candidate programs
        """
        if not self.pcfg_enumerator or not self.pcfg_enumerator.pcfg:
            logger.info("No PCFG available, skipping PCFG search")
            return []
        
        # Use beam search with PCFG
        candidates = self.pcfg_enumerator.beam_search_with_pcfg(
            examples=examples,
            beam_width=budget.beam_width or 10,
            max_depth=budget.max_depth,
            interpreter=interpreter,
        )
        
        return candidates[:budget.max_candidates]
    
    def _search_mcts(
        self,
        examples: List[TrainingExample],
        budget: SearchBudget,
        interpreter: Any,
    ) -> List[Program]:
        """Perform MCTS search.
        
        Args:
            examples: Training examples
            budget: Search budget
            interpreter: DSL interpreter
            
        Returns:
            List of candidate programs
        """
        if not self.mcts_searcher:
            return []
        
        # Create policy and value models
        policy_model = UniformPolicyModel()
        value_model = HeuristicValueModel()
        
        # Perform MCTS search
        candidates = self.mcts_searcher.search(
            examples=examples,
            budget=budget,
            policy_model=policy_model,
            value_model=value_model,
            interpreter=interpreter,
            seed=budget.seed,
        )
        
        return candidates[:budget.max_candidates]
    
    def _prune_with_abstract_interpretation(
        self,
        candidates: List[Program],
        examples: List[TrainingExample],
        interpreter: Any,
    ) -> List[Program]:
        """Prune candidates using abstract interpretation.
        
        Args:
            candidates: Candidate programs
            examples: Training examples
            interpreter: DSL interpreter
            
        Returns:
            Pruned list of candidates
        """
        if not self.abstract_interpreter or not examples:
            return candidates
        
        logger.info(f"Pruning {len(candidates)} candidates with abstract interpretation")
        
        pruned = []
        for candidate in candidates:
            # Check feasibility for each example
            is_feasible = True
            
            for example in examples:
                # Create abstract input
                abstract_input = AbstractGrid.from_concrete_grid(example.input_grid)
                
                # Execute abstractly
                abstract_output = self.abstract_interpreter.abstract_execute(
                    candidate, abstract_input
                )
                
                # Check feasibility
                if not self.abstract_interpreter.check_feasibility(
                    abstract_output, example.output_grid
                ):
                    is_feasible = False
                    break
            
            if is_feasible:
                pruned.append(candidate)
        
        logger.info(f"Pruned to {len(pruned)} feasible candidates")
        return pruned


__all__ = [
    "AdvancedSearchCoordinator",
]
