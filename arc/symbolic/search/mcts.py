"""Monte Carlo Tree Search (MCTS) for program synthesis.

This module implements MCTS-based program search, which balances
exploration and exploitation using UCB1 and can be guided by
policy and value models.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.search.budget import SearchBudget
from arc.symbolic.search.types import TrainingExample

logger = logging.getLogger(__name__)


class PolicyModel(Protocol):
    """Protocol for policy models that guide MCTS expansion.
    
    A policy model predicts which actions (stages) are most promising
    to explore from a given state.
    """
    
    def predict_policy(
        self,
        program: Program,
        examples: List[TrainingExample],
    ) -> Dict[str, float]:
        """Predict action probabilities for a program state.
        
        Args:
            program: Current partial program
            examples: Training examples
            
        Returns:
            Dictionary mapping operators to probabilities
        """
        ...


class ValueModel(Protocol):
    """Protocol for value models that estimate program quality.
    
    A value model predicts how likely a partial program is to lead
    to a successful solution.
    """
    
    def predict_value(
        self,
        program: Program,
        examples: List[TrainingExample],
    ) -> float:
        """Predict the value (expected reward) of a program state.
        
        Args:
            program: Current partial program
            examples: Training examples
            
        Returns:
            Predicted value in [0, 1]
        """
        ...


@dataclass
class MCTSNode:
    """Node in the MCTS search tree.
    
    Attributes:
        program: Partial or complete program at this node
        parent: Parent node (None for root)
        children: List of child nodes
        visits: Number of times this node has been visited
        total_reward: Cumulative reward from all visits
        metadata: Additional metadata about the node
    """
    
    program: Program
    parent: Optional[MCTSNode] = None
    children: List[MCTSNode] = field(default_factory=list)
    visits: int = 0
    total_reward: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def average_reward(self) -> float:
        """Compute the average reward for this node.
        
        Returns:
            Average reward, or 0.0 if never visited
        """
        if self.visits == 0:
            return 0.0
        return self.total_reward / self.visits
    
    def ucb1_score(
        self,
        exploration_constant: float = 1.414,
    ) -> float:
        """Compute the UCB1 score for this node.
        
        The UCB1 score balances exploitation (average reward) and
        exploration (visit count).
        
        Args:
            exploration_constant: Exploration constant (typically sqrt(2))
            
        Returns:
            UCB1 score
        """
        if self.visits == 0:
            return float('inf')
        
        if self.parent is None or self.parent.visits == 0:
            return self.average_reward
        
        exploitation = self.average_reward
        exploration = exploration_constant * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )
        
        return exploitation + exploration
    
    def is_leaf(self) -> bool:
        """Check if this node is a leaf (has no children).
        
        Returns:
            True if node is a leaf, False otherwise
        """
        return len(self.children) == 0
    
    def add_child(self, child: MCTSNode) -> None:
        """Add a child node.
        
        Args:
            child: Child node to add
        """
        child.parent = self
        self.children.append(child)


class MCTSSearcher:
    """Monte Carlo Tree Search for program synthesis.
    
    This class implements MCTS with optional policy and value model guidance.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the MCTS searcher.
        
        Args:
            config: Configuration dictionary with optional parameters:
                - exploration_constant: UCB1 exploration constant
                - max_depth: Maximum program depth
                - simulation_depth: Depth for rollout simulations
                - use_policy_model: Whether to use policy model
                - use_value_model: Whether to use value model
        """
        self.config = config or {}
        self.exploration_constant = self.config.get("exploration_constant", 1.414)
        self.max_depth = self.config.get("max_depth", 10)
        self.simulation_depth = self.config.get("simulation_depth", 5)
        self.use_policy_model = self.config.get("use_policy_model", False)
        self.use_value_model = self.config.get("use_value_model", False)
        
        logger.info(
            f"Initialized MCTSSearcher with "
            f"exploration_constant={self.exploration_constant}, "
            f"max_depth={self.max_depth}"
        )
    
    def search(
        self,
        examples: List[TrainingExample],
        budget: SearchBudget,
        policy_model: Optional[PolicyModel] = None,
        value_model: Optional[ValueModel] = None,
        interpreter: Any = None,
        seed: Optional[int] = None,
    ) -> List[Program]:
        """Perform MCTS search for program synthesis.
        
        Args:
            examples: Training examples to satisfy
            budget: Search budget
            policy_model: Optional policy model for guidance
            value_model: Optional value model for evaluation
            interpreter: DSL interpreter for program execution
            seed: Random seed for reproducibility
            
        Returns:
            List of best programs found
        """
        logger.info(f"Starting MCTS search with budget={budget.max_expansions}")
        
        rng = random.Random(seed)
        
        # Initialize root node with empty program
        root = MCTSNode(program=Program(stages=()))
        
        # Run MCTS iterations
        iterations = 0
        while iterations < budget.max_expansions and budget.has_time_remaining():
            # Selection: select a leaf node to expand
            node = self.select_node(root, self.exploration_constant)
            
            # Expansion: expand the selected node
            if not self._is_terminal(node.program) and node.visits > 0:
                self.expand_node(node, examples, policy_model, rng)
                # Select one of the new children for simulation
                if node.children:
                    node = node.children[0]
            
            # Simulation: simulate from the node to estimate value
            reward = self.simulate(
                node.program,
                examples,
                interpreter,
                value_model,
                rng,
            )
            
            # Backpropagation: update node statistics
            self.backpropagate(node, reward)
            
            iterations += 1
        
        logger.info(f"MCTS completed {iterations} iterations")
        
        # Extract best programs
        return self._extract_best_programs(root, top_k=budget.max_candidates)
    
    def select_node(
        self,
        root: MCTSNode,
        exploration_constant: float = 1.414,
    ) -> MCTSNode:
        """Select a node to expand using UCB1.
        
        Args:
            root: Root node to start selection from
            exploration_constant: UCB1 exploration constant
            
        Returns:
            Selected leaf node
        """
        node = root
        
        while not node.is_leaf():
            # Select child with highest UCB1 score
            best_child = max(
                node.children,
                key=lambda child: child.ucb1_score(exploration_constant),
            )
            node = best_child
        
        return node
    
    def expand_node(
        self,
        node: MCTSNode,
        examples: List[TrainingExample],
        policy_model: Optional[PolicyModel] = None,
        rng: Optional[random.Random] = None,
    ) -> List[MCTSNode]:
        """Expand a node by adding child nodes.
        
        Args:
            node: Node to expand
            examples: Training examples
            policy_model: Optional policy model for guidance
            rng: Random number generator
            
        Returns:
            List of newly created child nodes
        """
        rng = rng or random.Random()
        
        # Get possible actions (operators to add)
        if policy_model and self.use_policy_model:
            # Use policy model to guide expansion
            policy = policy_model.predict_policy(node.program, examples)
            operators = list(policy.keys())
        else:
            # Use default operator set
            operators = self._get_default_operators()
        
        # Create child nodes for each operator
        children = []
        for operator in operators:
            # Create new program with operator appended
            new_stage = Stage(operator=operator, arguments=())
            new_program = Program(stages=node.program.stages + (new_stage,))
            
            # Create child node
            child = MCTSNode(program=new_program)
            node.add_child(child)
            children.append(child)
        
        return children
    
    def simulate(
        self,
        program: Program,
        examples: List[TrainingExample],
        interpreter: Any,
        value_model: Optional[ValueModel] = None,
        rng: Optional[random.Random] = None,
    ) -> float:
        """Simulate from a program to estimate its value.
        
        Args:
            program: Program to simulate from
            examples: Training examples
            interpreter: DSL interpreter
            value_model: Optional value model for evaluation
            rng: Random number generator
            
        Returns:
            Estimated reward in [0, 1]
        """
        # If value model is available, use it
        if value_model and self.use_value_model:
            return value_model.predict_value(program, examples)
        
        # Otherwise, perform rollout simulation
        rng = rng or random.Random()
        current_program = program
        
        # Extend program randomly up to simulation depth
        for _ in range(self.simulation_depth):
            if self._is_terminal(current_program):
                break
            
            # Add random operator
            operators = self._get_default_operators()
            operator = rng.choice(operators)
            new_stage = Stage(operator=operator, arguments=())
            current_program = Program(stages=current_program.stages + (new_stage,))
        
        # Evaluate the simulated program
        if interpreter:
            return self._evaluate_program(current_program, examples, interpreter)
        else:
            # Without interpreter, return neutral reward
            return 0.5
    
    def backpropagate(
        self,
        node: MCTSNode,
        reward: float,
    ) -> None:
        """Backpropagate reward up the tree.
        
        Args:
            node: Node to start backpropagation from
            reward: Reward to backpropagate
        """
        current = node
        
        while current is not None:
            current.visits += 1
            current.total_reward += reward
            current = current.parent
    
    def _is_terminal(self, program: Program) -> bool:
        """Check if a program is terminal (complete).
        
        Args:
            program: Program to check
            
        Returns:
            True if program is terminal, False otherwise
        """
        return len(program.stages) >= self.max_depth
    
    def _get_default_operators(self) -> List[str]:
        """Get default set of operators for expansion.
        
        Returns:
            List of operator names
        """
        return [
            "rotate_cw",
            "rotate_ccw",
            "rotate_180",
            "reflect_horizontal",
            "reflect_vertical",
            "flood_fill",
            "paint_region",
            "detect_objects",
            "select_object",
        ]
    
    def _evaluate_program(
        self,
        program: Program,
        examples: List[TrainingExample],
        interpreter: Any,
    ) -> float:
        """Evaluate a program on examples.
        
        Args:
            program: Program to evaluate
            examples: Training examples
            interpreter: DSL interpreter
            
        Returns:
            Reward in [0, 1] based on number of satisfied examples
        """
        if not examples:
            return 0.0
        
        satisfied = 0
        for example in examples:
            try:
                result = interpreter.run(program, example.input_grid)
                if self._grids_equal(result, example.output_grid):
                    satisfied += 1
            except Exception:
                pass
        
        return satisfied / len(examples)
    
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
    
    def _extract_best_programs(
        self,
        root: MCTSNode,
        top_k: int = 10,
    ) -> List[Program]:
        """Extract the best programs from the search tree.
        
        Args:
            root: Root node of the search tree
            top_k: Number of top programs to extract
            
        Returns:
            List of best programs
        """
        # Collect all nodes with their average rewards
        nodes = []
        
        def collect_nodes(node: MCTSNode) -> None:
            if node.visits > 0:
                nodes.append((node.average_reward, node.program))
            for child in node.children:
                collect_nodes(child)
        
        collect_nodes(root)
        
        # Sort by average reward (descending)
        nodes.sort(key=lambda x: x[0], reverse=True)
        
        # Extract top-k programs
        return [program for _, program in nodes[:top_k]]


__all__ = [
    "MCTSNode",
    "MCTSSearcher",
    "PolicyModel",
    "ValueModel",
]
