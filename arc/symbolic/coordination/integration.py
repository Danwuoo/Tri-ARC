"""Integration module for coordination components into the symbolic solver.

This module provides a unified interface for integrating TTT and LLM
coordination into the symbolic solver.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from arc.symbolic.coordination.llm_coordinator import LLMCoordinator
from arc.symbolic.coordination.message_queue import MessageQueue
from arc.symbolic.coordination.ttt_coordinator import TTTCoordinator
from arc.symbolic.coordination.types import DSLMacro, Invariant, Relation
from arc.symbolic.ir.sketch import ProgramSketch

logger = logging.getLogger(__name__)


class CoordinationIntegration:
    """Unified coordination integration for symbolic solver.
    
    This class manages both TTT and LLM coordinators and provides
    a simplified interface for the solver to interact with them.
    
    Attributes:
        config: Configuration dictionary
        ttt_coordinator: TTT module coordinator
        llm_coordinator: LLM module coordinator
        message_queue: Shared message queue
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize coordination integration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        
        # Extract coordination config
        coord_config = config.get("coordination", {})
        self.enabled = coord_config.get("enabled", False)
        
        if not self.enabled:
            logger.info("Coordination integration disabled")
            self.ttt_coordinator = None
            self.llm_coordinator = None
            self.message_queue = None
            return
        
        # Create shared message queue
        queue_config = {
            "enable_logging": coord_config.get("log_messages", False),
            "log_file": coord_config.get("message_log_file"),
        }
        self.message_queue = MessageQueue(max_size=1000, config=queue_config)
        self.message_queue.start()
        
        # Initialize coordinators
        ttt_config = coord_config.get("ttt", {})
        if ttt_config.get("enabled", True):
            self.ttt_coordinator = TTTCoordinator(config, self.message_queue)
            logger.info("TTT coordinator initialized")
        else:
            self.ttt_coordinator = None
            logger.info("TTT coordinator disabled")
        
        llm_config = coord_config.get("llm", {})
        if llm_config.get("enabled", True):
            self.llm_coordinator = LLMCoordinator(config, self.message_queue)
            logger.info("LLM coordinator initialized")
        else:
            self.llm_coordinator = None
            logger.info("LLM coordinator disabled")
        
        logger.info("Coordination integration initialized")
    
    def get_invariants(self, task_id: str) -> List[Invariant]:
        """Get all invariants for a task from TTT.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of invariants (empty if TTT disabled)
        """
        if not self.enabled or not self.ttt_coordinator:
            return []
        
        return self.ttt_coordinator.get_invariants(task_id)
    
    def get_relations(self, task_id: str) -> List[Relation]:
        """Get all relations for a task from TTT.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of relations (empty if TTT disabled)
        """
        if not self.enabled or not self.ttt_coordinator:
            return []
        
        return self.ttt_coordinator.get_relations(task_id)
    
    def get_macros(self, task_id: str) -> List[DSLMacro]:
        """Get all DSL macros for a task from LLM.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of DSL macros (empty if LLM disabled)
        """
        if not self.enabled or not self.llm_coordinator:
            return []
        
        return self.llm_coordinator.get_macros(task_id)
    
    def get_sketches(self, task_id: str) -> List[ProgramSketch]:
        """Get all program sketches for a task from LLM.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of program sketches (empty if LLM disabled)
        """
        if not self.enabled or not self.llm_coordinator:
            return []
        
        return self.llm_coordinator.get_sketches(task_id)
    
    def send_failure_feedback(
        self,
        task_id: str,
        failure_type: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Send failure feedback to both TTT and LLM modules.
        
        Args:
            task_id: ID of the task that failed
            failure_type: Type of failure
            metadata: Additional metadata about the failure
        """
        if not self.enabled:
            return
        
        # Send to TTT
        if self.ttt_coordinator:
            self.ttt_coordinator.send_failure_feedback(task_id, failure_type, metadata)
        
        # Send to LLM with prompt adjustment suggestion
        if self.llm_coordinator:
            prompt_adjustment = self._generate_prompt_adjustment(failure_type, metadata)
            self.llm_coordinator.send_failure_feedback(task_id, failure_type, prompt_adjustment)
    
    def verify_llm_candidate(self, program: Any, examples: List[Any]) -> Dict[str, Any]:
        """Verify an LLM-generated candidate program.
        
        Args:
            program: The candidate program
            examples: List of examples
            
        Returns:
            Verification result
        """
        if not self.enabled or not self.llm_coordinator:
            return {"status": "skipped", "reason": "LLM coordinator disabled"}
        
        return self.llm_coordinator.verify_llm_candidate(program, examples)
    
    def clear_cache(self, task_id: Optional[str] = None) -> None:
        """Clear cached data for a task.
        
        Args:
            task_id: ID of task to clear (None = clear all)
        """
        if not self.enabled:
            return
        
        if self.ttt_coordinator:
            self.ttt_coordinator.clear_cache(task_id)
        
        if self.llm_coordinator:
            self.llm_coordinator.clear_cache(task_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get coordination statistics.
        
        Returns:
            Dictionary of statistics from all coordinators
        """
        stats = {
            "enabled": self.enabled,
            "ttt": {},
            "llm": {},
            "queue": {},
        }
        
        if not self.enabled:
            return stats
        
        if self.ttt_coordinator:
            stats["ttt"] = self.ttt_coordinator.get_stats()
        
        if self.llm_coordinator:
            stats["llm"] = self.llm_coordinator.get_stats()
        
        if self.message_queue:
            stats["queue"] = self.message_queue.get_stats()
        
        return stats
    
    def shutdown(self) -> None:
        """Shutdown coordination and clean up resources."""
        if not self.enabled:
            return
        
        logger.info("Shutting down coordination integration")
        
        if self.ttt_coordinator:
            self.ttt_coordinator.shutdown()
        
        if self.llm_coordinator:
            self.llm_coordinator.shutdown()
        
        if self.message_queue:
            self.message_queue.stop()
    
    def _generate_prompt_adjustment(
        self,
        failure_type: str,
        metadata: Dict[str, Any],
    ) -> str:
        """Generate a prompt adjustment suggestion based on failure type.
        
        Args:
            failure_type: Type of failure
            metadata: Failure metadata
            
        Returns:
            Suggested prompt adjustment
        """
        # Simple heuristic-based prompt adjustment
        if failure_type == "verification_failed":
            return "Focus on generating programs that satisfy all input-output examples"
        elif failure_type == "invalid_syntax":
            return "Ensure generated programs use valid DSL syntax"
        elif failure_type == "search_exhausted":
            return "Try simpler program structures or different operator combinations"
        elif failure_type == "timeout":
            return "Generate more efficient programs with fewer stages"
        else:
            return "Review program structure and operator usage"
