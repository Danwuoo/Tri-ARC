"""Adaptive budget management for search strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from arc.symbolic.search.budget import SearchBudget


@dataclass
class TaskFeatures:
    """Features extracted from a task for budget allocation."""
    
    grid_size: int
    symmetry_score: float
    color_count: int
    object_count: int
    complexity_score: float
    has_patterns: bool
    
    @classmethod
    def from_task(cls, task: Dict[str, Any]) -> TaskFeatures:
        """Extract features from task."""
        # Extract grid dimensions
        train_examples = task.get("train", [])
        if not train_examples:
            return cls.default()
        
        first_input = train_examples[0].get("input", [[]])
        grid_size = len(first_input) * len(first_input[0]) if first_input else 0
        
        # Count unique colors
        colors = set()
        for example in train_examples:
            for row in example.get("input", []):
                colors.update(row)
            for row in example.get("output", []):
                colors.update(row)
        color_count = len(colors)
        
        # Estimate complexity (placeholder heuristics)
        complexity_score = grid_size * 0.01 + color_count * 0.1
        
        return TaskFeatures(
            grid_size=grid_size,
            symmetry_score=0.5,  # Placeholder
            color_count=color_count,
            object_count=0,  # Placeholder
            complexity_score=complexity_score,
            has_patterns=False,  # Placeholder
        )
    
    @classmethod
    def default(cls) -> TaskFeatures:
        """Create default features."""
        return TaskFeatures(
            grid_size=100,
            symmetry_score=0.5,
            color_count=5,
            object_count=5,
            complexity_score=1.0,
            has_patterns=False,
        )


class AdaptiveBudgetManager:
    """Manages adaptive budget allocation based on task features."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.history: Dict[str, Dict[str, Any]] = {}
        
        # Default multipliers
        self.small_grid_depth_multiplier = self.config.get("small_grid_depth_multiplier", 1.5)
        self.large_grid_depth_multiplier = self.config.get("large_grid_depth_multiplier", 0.8)
        self.high_symmetry_time_multiplier = self.config.get("high_symmetry_time_multiplier", 1.3)
        self.high_complexity_time_multiplier = self.config.get("high_complexity_time_multiplier", 1.2)
        
        # Thresholds
        self.small_grid_threshold = self.config.get("small_grid_threshold", 100)
        self.large_grid_threshold = self.config.get("large_grid_threshold", 400)
        self.high_symmetry_threshold = self.config.get("high_symmetry_threshold", 0.7)
        self.high_complexity_threshold = self.config.get("high_complexity_threshold", 2.0)
    
    def allocate_budget(
        self,
        task: Dict[str, Any],
        global_budget: SearchBudget,
        task_features: Optional[TaskFeatures] = None,
    ) -> SearchBudget:
        """Allocate budget based on task features.
        
        Args:
            task: Task dictionary
            global_budget: Global budget constraints
            task_features: Optional pre-computed task features
            
        Returns:
            Adapted search budget
        """
        if task_features is None:
            task_features = TaskFeatures.from_task(task)
        
        # Start with global budget
        depth_multiplier = 1.0
        time_multiplier = 1.0
        expansions_multiplier = 1.0
        
        # Adjust based on grid size
        if task_features.grid_size < self.small_grid_threshold:
            # Small grids: deeper search
            depth_multiplier *= self.small_grid_depth_multiplier
            expansions_multiplier *= 1.2
        elif task_features.grid_size > self.large_grid_threshold:
            # Large grids: shallower but wider search
            depth_multiplier *= self.large_grid_depth_multiplier
            expansions_multiplier *= 1.3
        
        # Adjust based on symmetry
        if task_features.symmetry_score > self.high_symmetry_threshold:
            # High symmetry: more time for symbolic reasoning
            time_multiplier *= self.high_symmetry_time_multiplier
        
        # Adjust based on complexity
        if task_features.complexity_score > self.high_complexity_threshold:
            # High complexity: more resources
            time_multiplier *= self.high_complexity_time_multiplier
            expansions_multiplier *= 1.2
        
        # Adjust based on historical performance
        task_id = task.get("task_id", "unknown")
        if task_id in self.history:
            hist = self.history[task_id]
            if hist.get("success", False):
                # Previously successful: use similar budget
                time_multiplier *= 0.9
            else:
                # Previously failed: allocate more resources
                time_multiplier *= 1.1
                expansions_multiplier *= 1.1
        
        # Apply multipliers
        adapted_budget = SearchBudget(
            max_depth=int(global_budget.max_depth * depth_multiplier),
            max_expansions=int(global_budget.max_expansions * expansions_multiplier),
            max_nodes=global_budget.max_nodes,
            soft_timeout_s=global_budget.soft_timeout_s * time_multiplier,
            hard_timeout_s=global_budget.hard_timeout_s * time_multiplier,
            beam_width=global_budget.beam_width,
        )
        
        return adapted_budget
    
    def record_performance(
        self,
        task_id: str,
        success: bool,
        elapsed_time: float,
        expansions: int,
        features: TaskFeatures,
    ) -> None:
        """Record task performance for future budget allocation.
        
        Args:
            task_id: Task identifier
            success: Whether task was solved successfully
            elapsed_time: Time taken in seconds
            expansions: Number of search expansions
            features: Task features
        """
        self.history[task_id] = {
            "success": success,
            "elapsed_time": elapsed_time,
            "expansions": expansions,
            "grid_size": features.grid_size,
            "symmetry_score": features.symmetry_score,
            "complexity_score": features.complexity_score,
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get budget allocation statistics."""
        if not self.history:
            return {
                "total_tasks": 0,
                "success_rate": 0.0,
                "avg_time": 0.0,
                "avg_expansions": 0.0,
            }
        
        total = len(self.history)
        successes = sum(1 for h in self.history.values() if h["success"])
        avg_time = sum(h["elapsed_time"] for h in self.history.values()) / total
        avg_expansions = sum(h["expansions"] for h in self.history.values()) / total
        
        return {
            "total_tasks": total,
            "success_rate": successes / total,
            "avg_time": avg_time,
            "avg_expansions": avg_expansions,
        }
    
    def clear_history(self) -> None:
        """Clear performance history."""
        self.history.clear()
