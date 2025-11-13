"""Probabilistic Context-Free Grammar (PCFG) for program synthesis.

This module implements PCFG-based program enumeration, which uses
learned probabilities to guide the search toward more likely programs.
"""

from __future__ import annotations

import logging
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.search.budget import SearchBudget
from arc.symbolic.search.types import TrainingExample

logger = logging.getLogger(__name__)


@dataclass
class PCFG:
    """Probabilistic Context-Free Grammar for program synthesis.
    
    A PCFG defines production rules with probabilities, allowing
    probabilistic sampling of programs.
    
    Attributes:
        production_rules: Maps non-terminal to list of (production, probability) tuples
        start_symbol: The start symbol for program generation
        terminal_symbols: Set of terminal symbols (operators, constants)
        metadata: Additional metadata about the grammar
    """
    
    production_rules: Dict[str, List[Tuple[List[str], float]]] = field(default_factory=dict)
    start_symbol: str = "Program"
    terminal_symbols: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate and normalize the PCFG."""
        self._normalize_probabilities()
    
    def _normalize_probabilities(self) -> None:
        """Normalize probabilities for each non-terminal to sum to 1.0."""
        for non_terminal, productions in self.production_rules.items():
            total_prob = sum(prob for _, prob in productions)
            if total_prob > 0:
                self.production_rules[non_terminal] = [
                    (prod, prob / total_prob) for prod, prob in productions
                ]
    
    def sample_production(
        self,
        non_terminal: str,
        temperature: float = 1.0,
        rng: Optional[random.Random] = None,
    ) -> Optional[List[str]]:
        """Sample a production for a non-terminal.
        
        Args:
            non_terminal: Non-terminal to expand
            temperature: Temperature for sampling (higher = more random)
            rng: Random number generator
            
        Returns:
            Sampled production, or None if no productions available
        """
        if non_terminal not in self.production_rules:
            return None
        
        productions = self.production_rules[non_terminal]
        if not productions:
            return None
        
        rng = rng or random.Random()
        
        # Apply temperature to probabilities
        if temperature != 1.0:
            probs = [prob ** (1.0 / temperature) for _, prob in productions]
            total = sum(probs)
            probs = [p / total for p in probs]
        else:
            probs = [prob for _, prob in productions]
        
        # Sample production
        r = rng.random()
        cumulative = 0.0
        for (prod, _), prob in zip(productions, probs):
            cumulative += prob
            if r <= cumulative:
                return prod
        
        # Fallback to last production
        return productions[-1][0]
    
    def get_probability(
        self,
        non_terminal: str,
        production: List[str],
    ) -> float:
        """Get the probability of a production.
        
        Args:
            non_terminal: Non-terminal symbol
            production: Production to look up
            
        Returns:
            Probability of the production, or 0.0 if not found
        """
        if non_terminal not in self.production_rules:
            return 0.0
        
        for prod, prob in self.production_rules[non_terminal]:
            if prod == production:
                return prob
        
        return 0.0
    
    def add_production(
        self,
        non_terminal: str,
        production: List[str],
        probability: float = 1.0,
    ) -> None:
        """Add a production rule to the grammar.
        
        Args:
            non_terminal: Non-terminal symbol
            production: Production (list of symbols)
            probability: Initial probability (will be normalized)
        """
        if non_terminal not in self.production_rules:
            self.production_rules[non_terminal] = []
        
        self.production_rules[non_terminal].append((production, probability))
        self._normalize_probabilities()
    
    def is_terminal(self, symbol: str) -> bool:
        """Check if a symbol is terminal.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if symbol is terminal, False otherwise
        """
        return symbol in self.terminal_symbols


class ProbabilisticEnumerator:
    """Probabilistic enumerator using PCFG for program synthesis.
    
    This class uses a learned PCFG to guide program enumeration,
    prioritizing more likely programs based on learned probabilities.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the probabilistic enumerator.
        
        Args:
            config: Configuration dictionary with optional parameters:
                - smoothing_factor: Smoothing factor for probability estimation
                - min_production_count: Minimum count for production inclusion
                - default_temperature: Default sampling temperature
        """
        self.config = config or {}
        self.smoothing_factor = self.config.get("smoothing_factor", 0.1)
        self.min_production_count = self.config.get("min_production_count", 1)
        self.default_temperature = self.config.get("default_temperature", 1.0)
        
        self.pcfg: Optional[PCFG] = None
        
        logger.info(
            f"Initialized ProbabilisticEnumerator with "
            f"smoothing={self.smoothing_factor}, "
            f"min_count={self.min_production_count}"
        )
    
    def train_pcfg(
        self,
        successful_programs: List[Program],
    ) -> PCFG:
        """Train a PCFG from successful programs.
        
        This method analyzes successful programs to learn production
        probabilities based on their frequency.
        
        Args:
            successful_programs: List of successful programs
            
        Returns:
            Trained PCFG
        """
        logger.info(f"Training PCFG from {len(successful_programs)} programs")
        
        # Count productions
        production_counts = defaultdict(Counter)
        
        for program in successful_programs:
            # Extract productions from program
            productions = self._extract_productions(program)
            
            for non_terminal, production in productions:
                production_counts[non_terminal][tuple(production)] += 1
        
        # Build PCFG from counts
        pcfg = PCFG()
        
        for non_terminal, counter in production_counts.items():
            total_count = sum(counter.values())
            
            for production, count in counter.items():
                if count >= self.min_production_count:
                    # Compute probability with smoothing
                    prob = (count + self.smoothing_factor) / (
                        total_count + self.smoothing_factor * len(counter)
                    )
                    pcfg.add_production(non_terminal, list(production), prob)
        
        # Set terminal symbols
        pcfg.terminal_symbols = self._extract_terminal_symbols(successful_programs)
        
        # Store trained PCFG
        self.pcfg = pcfg
        
        logger.info(
            f"Trained PCFG with {len(pcfg.production_rules)} non-terminals, "
            f"{len(pcfg.terminal_symbols)} terminals"
        )
        
        return pcfg
    
    def sample_program(
        self,
        pcfg: Optional[PCFG] = None,
        max_depth: int = 10,
        temperature: float = 1.0,
        seed: Optional[int] = None,
    ) -> Optional[Program]:
        """Sample a program from the PCFG.
        
        Args:
            pcfg: PCFG to sample from (uses trained PCFG if None)
            max_depth: Maximum derivation depth
            temperature: Sampling temperature (higher = more random)
            seed: Random seed for reproducibility
            
        Returns:
            Sampled program, or None if sampling fails
        """
        pcfg = pcfg or self.pcfg
        if not pcfg:
            logger.warning("No PCFG available for sampling")
            return None
        
        rng = random.Random(seed)
        
        # Start derivation from start symbol
        derivation = [pcfg.start_symbol]
        depth = 0
        
        while depth < max_depth:
            # Find first non-terminal
            non_terminal_idx = None
            for i, symbol in enumerate(derivation):
                if not pcfg.is_terminal(symbol):
                    non_terminal_idx = i
                    break
            
            if non_terminal_idx is None:
                # All symbols are terminal, derivation complete
                break
            
            # Sample production for non-terminal
            non_terminal = derivation[non_terminal_idx]
            production = pcfg.sample_production(non_terminal, temperature, rng)
            
            if production is None:
                # No production available, sampling failed
                return None
            
            # Replace non-terminal with production
            derivation = (
                derivation[:non_terminal_idx] +
                production +
                derivation[non_terminal_idx + 1:]
            )
            
            depth += 1
        
        # Convert derivation to program
        return self._derivation_to_program(derivation)
    
    def beam_search_with_pcfg(
        self,
        pcfg: Optional[PCFG] = None,
        examples: Optional[List[TrainingExample]] = None,
        beam_width: int = 10,
        max_depth: int = 10,
        interpreter: Any = None,
    ) -> List[Program]:
        """Perform beam search guided by PCFG probabilities.
        
        Args:
            pcfg: PCFG to use for guidance (uses trained PCFG if None)
            examples: Training examples to satisfy
            beam_width: Width of the beam
            max_depth: Maximum derivation depth
            interpreter: DSL interpreter for program execution
            
        Returns:
            List of programs found by beam search
        """
        pcfg = pcfg or self.pcfg
        if not pcfg:
            logger.warning("No PCFG available for beam search")
            return []
        
        logger.info(f"Starting beam search with width={beam_width}, max_depth={max_depth}")
        
        # Initialize beam with start symbol
        beam = [(0.0, [pcfg.start_symbol], 0)]  # (log_prob, derivation, depth)
        completed_programs = []
        
        while beam and len(completed_programs) < beam_width:
            # Expand all derivations in beam
            candidates = []
            
            for log_prob, derivation, depth in beam:
                if depth >= max_depth:
                    continue
                
                # Find first non-terminal
                non_terminal_idx = None
                for i, symbol in enumerate(derivation):
                    if not pcfg.is_terminal(symbol):
                        non_terminal_idx = i
                        break
                
                if non_terminal_idx is None:
                    # Derivation complete
                    program = self._derivation_to_program(derivation)
                    if program:
                        completed_programs.append(program)
                    continue
                
                # Expand non-terminal with all productions
                non_terminal = derivation[non_terminal_idx]
                if non_terminal not in pcfg.production_rules:
                    continue
                
                for production, prob in pcfg.production_rules[non_terminal]:
                    new_derivation = (
                        derivation[:non_terminal_idx] +
                        production +
                        derivation[non_terminal_idx + 1:]
                    )
                    new_log_prob = log_prob + math.log(prob + 1e-10)
                    candidates.append((new_log_prob, new_derivation, depth + 1))
            
            # Select top-k candidates for next beam
            candidates.sort(key=lambda x: x[0], reverse=True)
            beam = candidates[:beam_width]
        
        logger.info(f"Beam search completed with {len(completed_programs)} programs")
        return completed_programs
    
    def _extract_productions(
        self,
        program: Program,
    ) -> List[Tuple[str, List[str]]]:
        """Extract productions from a program.
        
        Args:
            program: Program to extract productions from
            
        Returns:
            List of (non_terminal, production) tuples
        """
        productions = []
        
        # Program -> Stage*
        stage_symbols = [f"Stage_{stage.operator}" for stage in program.stages]
        productions.append(("Program", stage_symbols))
        
        # Stage -> Operator Arguments
        for stage in program.stages:
            operator = stage.operator
            arg_symbols = [f"Arg_{type(arg).__name__}" for arg in stage.arguments]
            productions.append((f"Stage_{operator}", [operator] + arg_symbols))
        
        return productions
    
    def _extract_terminal_symbols(
        self,
        programs: List[Program],
    ) -> Set[str]:
        """Extract terminal symbols from programs.
        
        Args:
            programs: List of programs
            
        Returns:
            Set of terminal symbols
        """
        terminals = set()
        
        for program in programs:
            for stage in program.stages:
                terminals.add(stage.operator)
                for arg in stage.arguments:
                    terminals.add(f"Arg_{type(arg).__name__}")
        
        return terminals
    
    def _derivation_to_program(
        self,
        derivation: List[str],
    ) -> Optional[Program]:
        """Convert a derivation to a program.
        
        Args:
            derivation: List of symbols in derivation
            
        Returns:
            Program, or None if conversion fails
        """
        # Extract operators from derivation
        stages = []
        
        for symbol in derivation:
            if symbol.startswith("Stage_"):
                # This is a stage symbol, extract operator
                operator = symbol[6:]  # Remove "Stage_" prefix
                stages.append(Stage(operator=operator, arguments=()))
        
        if not stages:
            return None
        
        return Program(stages=tuple(stages))


__all__ = [
    "PCFG",
    "ProbabilisticEnumerator",
]
