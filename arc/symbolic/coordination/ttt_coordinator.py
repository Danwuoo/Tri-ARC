"""TTT module coordinator for symbolic solver.

This module provides coordination between the symbolic solver and the
Test-Time Training (TTT) module, enabling exchange of invariants,
relations, and failure feedback.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from arc.symbolic.coordination.message_queue import Message, MessageQueue
from arc.symbolic.coordination.types import Invariant, Relation

logger = logging.getLogger(__name__)


class TTTCoordinator:
    """Coordinates communication with the TTT module.
    
    The TTT coordinator receives invariants and candidate relations from
    the TTT module and sends failure feedback back to TTT for learning.
    
    Attributes:
        config: Configuration dictionary
        message_queue: Message queue for communication
        invariant_cache: Cache of invariants by task_id
        relation_cache: Cache of relations by task_id
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        message_queue: Optional[MessageQueue] = None,
    ):
        """Initialize TTT coordinator.
        
        Args:
            config: Configuration dictionary
            message_queue: Optional message queue (creates new one if None)
        """
        self.config = config
        
        # Extract coordination config
        coord_config = config.get("coordination", {})
        ttt_config = coord_config.get("ttt", {})
        
        self.enabled = ttt_config.get("enabled", True)
        self.receive_invariants_enabled = ttt_config.get("receive_invariants", True)
        self.send_feedback_enabled = ttt_config.get("send_feedback", True)
        
        # Message queue
        if message_queue is None:
            queue_config = {
                "enable_logging": ttt_config.get("log_messages", False),
                "log_file": ttt_config.get("message_log_file"),
            }
            self.message_queue = MessageQueue(max_size=1000, config=queue_config)
            self.message_queue.start()
        else:
            self.message_queue = message_queue
        
        # Caches
        self.invariant_cache: Dict[str, List[Invariant]] = {}
        self.relation_cache: Dict[str, List[Relation]] = {}
        
        # Statistics
        self.stats = {
            "invariants_received": 0,
            "relations_received": 0,
            "feedback_sent": 0,
        }
        
        # Register message handlers
        if self.enabled:
            self.message_queue.register_handler("ttt_invariants", self._handle_invariants_message)
            self.message_queue.register_handler("ttt_relations", self._handle_relations_message)
        
        logger.info(f"TTTCoordinator initialized (enabled={self.enabled})")
    
    def receive_invariants(
        self,
        task_id: str,
        invariants: List[Invariant],
    ) -> None:
        """Receive invariants from TTT module.
        
        This method is called when the TTT module sends invariants
        that should be used as constraints during synthesis.
        
        Args:
            task_id: ID of the task
            invariants: List of invariants to apply
        """
        if not self.enabled or not self.receive_invariants_enabled:
            return
        
        # Validate invariants
        valid_invariants = []
        for inv in invariants:
            if inv.validate():
                valid_invariants.append(inv)
            else:
                logger.warning(f"Invalid invariant received: {inv}")
        
        # Store in cache
        if task_id not in self.invariant_cache:
            self.invariant_cache[task_id] = []
        self.invariant_cache[task_id].extend(valid_invariants)
        
        # Update statistics
        self.stats["invariants_received"] += len(valid_invariants)
        
        logger.info(
            f"Received {len(valid_invariants)} invariants for task {task_id} "
            f"(total: {len(self.invariant_cache[task_id])})"
        )
    
    def receive_candidate_relations(
        self,
        task_id: str,
        relations: List[Relation],
    ) -> None:
        """Receive candidate relations from TTT module.
        
        Relations describe spatial or semantic relationships between
        objects that can guide synthesis.
        
        Args:
            task_id: ID of the task
            relations: List of candidate relations
        """
        if not self.enabled or not self.receive_invariants_enabled:
            return
        
        # Validate relations
        valid_relations = []
        for rel in relations:
            if rel.validate():
                valid_relations.append(rel)
            else:
                logger.warning(f"Invalid relation received: {rel}")
        
        # Store in cache
        if task_id not in self.relation_cache:
            self.relation_cache[task_id] = []
        self.relation_cache[task_id].extend(valid_relations)
        
        # Update statistics
        self.stats["relations_received"] += len(valid_relations)
        
        logger.info(
            f"Received {len(valid_relations)} relations for task {task_id} "
            f"(total: {len(self.relation_cache[task_id])})"
        )
    
    def send_failure_feedback(
        self,
        task_id: str,
        failure_type: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Send failure feedback to TTT module.
        
        When synthesis fails, this method sends feedback to the TTT module
        to help it improve its invariant generation and prompt templates.
        
        Args:
            task_id: ID of the task that failed
            failure_type: Type of failure (e.g., "search_exhausted", "verification_failed")
            metadata: Additional metadata about the failure
        """
        if not self.enabled or not self.send_feedback_enabled:
            return
        
        # Create feedback message
        message = Message(
            type="symbolic_failure",
            task_id=task_id,
            payload={
                "failure_type": failure_type,
                "metadata": metadata,
            },
        )
        
        # Send message
        success = self.message_queue.put(message, block=False)
        
        if success:
            self.stats["feedback_sent"] += 1
            logger.info(f"Sent failure feedback for task {task_id}: {failure_type}")
        else:
            logger.warning(f"Failed to send feedback for task {task_id} (queue full)")
    
    def get_invariants(self, task_id: str) -> List[Invariant]:
        """Get all invariants for a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of invariants for the task
        """
        return self.invariant_cache.get(task_id, [])
    
    def get_relations(self, task_id: str) -> List[Relation]:
        """Get all relations for a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of relations for the task
        """
        return self.relation_cache.get(task_id, [])
    
    def clear_cache(self, task_id: Optional[str] = None) -> None:
        """Clear cached invariants and relations.
        
        Args:
            task_id: ID of task to clear (None = clear all)
        """
        if task_id is None:
            self.invariant_cache.clear()
            self.relation_cache.clear()
            logger.info("Cleared all cached invariants and relations")
        else:
            self.invariant_cache.pop(task_id, None)
            self.relation_cache.pop(task_id, None)
            logger.info(f"Cleared cached data for task {task_id}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get coordination statistics.
        
        Returns:
            Dictionary of statistics
        """
        return self.stats.copy()
    
    def _handle_invariants_message(self, message: Message) -> None:
        """Handle incoming invariants message.
        
        Args:
            message: The message containing invariants
        """
        try:
            task_id = message.task_id
            invariants_data = message.payload.get("invariants", [])
            
            # Deserialize invariants
            invariants = []
            for inv_data in invariants_data:
                if isinstance(inv_data, Invariant):
                    invariants.append(inv_data)
                elif isinstance(inv_data, dict):
                    invariants.append(Invariant.from_dict(inv_data))
            
            # Receive invariants
            self.receive_invariants(task_id, invariants)
        
        except Exception as e:
            logger.error(f"Error handling invariants message: {e}")
    
    def _handle_relations_message(self, message: Message) -> None:
        """Handle incoming relations message.
        
        Args:
            message: The message containing relations
        """
        try:
            task_id = message.task_id
            relations_data = message.payload.get("relations", [])
            
            # Deserialize relations
            relations = []
            for rel_data in relations_data:
                if isinstance(rel_data, Relation):
                    relations.append(rel_data)
                elif isinstance(rel_data, dict):
                    relations.append(Relation.from_dict(rel_data))
            
            # Receive relations
            self.receive_candidate_relations(task_id, relations)
        
        except Exception as e:
            logger.error(f"Error handling relations message: {e}")
    
    def shutdown(self) -> None:
        """Shutdown the coordinator and clean up resources."""
        logger.info("Shutting down TTTCoordinator")
        
        # Unregister handlers
        if self.enabled:
            self.message_queue.unregister_handler("ttt_invariants", self._handle_invariants_message)
            self.message_queue.unregister_handler("ttt_relations", self._handle_relations_message)
        
        # Clear caches
        self.clear_cache()
