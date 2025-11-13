"""LLM module coordinator for symbolic solver.

This module provides coordination between the symbolic solver and the
LLM module, enabling exchange of DSL macros, sketches, and failure feedback.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from arc.symbolic.coordination.message_queue import Message, MessageQueue
from arc.symbolic.coordination.types import DSLMacro
from arc.symbolic.dsl.types import Grid, Program
from arc.symbolic.ir.sketch import ProgramSketch

logger = logging.getLogger(__name__)


class LLMCoordinator:
    """Coordinates communication with the LLM module.
    
    The LLM coordinator receives DSL macros and program sketches from
    the LLM module, verifies LLM-generated candidates, and sends failure
    feedback back to LLM for prompt adjustment.
    
    Attributes:
        config: Configuration dictionary
        message_queue: Message queue for communication
        macro_cache: Cache of DSL macros by task_id
        sketch_cache: Cache of program sketches by task_id
        smt_verifier: SMT verifier for mandatory verification
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        message_queue: Optional[MessageQueue] = None,
        smt_verifier: Optional[Any] = None,
    ):
        """Initialize LLM coordinator.
        
        Args:
            config: Configuration dictionary
            message_queue: Optional message queue (creates new one if None)
            smt_verifier: Optional SMT verifier for candidate verification
        """
        self.config = config
        
        # Extract coordination config
        coord_config = config.get("coordination", {})
        llm_config = coord_config.get("llm", {})
        
        self.enabled = llm_config.get("enabled", True)
        self.receive_macros_enabled = llm_config.get("receive_macros", True)
        self.verify_candidates_enabled = llm_config.get("verify_candidates", True)
        self.send_feedback_enabled = llm_config.get("send_feedback", True)
        
        # Message queue
        if message_queue is None:
            queue_config = {
                "enable_logging": llm_config.get("log_messages", False),
                "log_file": llm_config.get("message_log_file"),
            }
            self.message_queue = MessageQueue(max_size=1000, config=queue_config)
            self.message_queue.start()
        else:
            self.message_queue = message_queue
        
        # SMT verifier (lazy initialization)
        self._smt_verifier = smt_verifier
        
        # Caches
        self.macro_cache: Dict[str, List[DSLMacro]] = {}
        self.sketch_cache: Dict[str, List[ProgramSketch]] = {}
        
        # Statistics
        self.stats = {
            "macros_received": 0,
            "sketches_received": 0,
            "candidates_verified": 0,
            "candidates_passed": 0,
            "candidates_failed": 0,
            "feedback_sent": 0,
        }
        
        # Register message handlers
        if self.enabled:
            self.message_queue.register_handler("llm_macro", self._handle_macro_message)
            self.message_queue.register_handler("llm_sketch", self._handle_sketch_message)
        
        logger.info(f"LLMCoordinator initialized (enabled={self.enabled})")
    
    def receive_dsl_macro(
        self,
        task_id: str,
        macro: DSLMacro,
    ) -> None:
        """Receive a DSL macro from LLM module.
        
        DSL macros are high-level program fragments that can be expanded
        into concrete DSL stages during synthesis.
        
        Args:
            task_id: ID of the task
            macro: The DSL macro to receive
        """
        if not self.enabled or not self.receive_macros_enabled:
            return
        
        # Validate macro
        if not macro.validate():
            logger.warning(f"Invalid macro received: {macro.name}")
            return
        
        # Store in cache
        if task_id not in self.macro_cache:
            self.macro_cache[task_id] = []
        self.macro_cache[task_id].append(macro)
        
        # Update statistics
        self.stats["macros_received"] += 1
        
        logger.info(
            f"Received macro '{macro.name}' for task {task_id} "
            f"(confidence={macro.confidence:.2f}, total: {len(self.macro_cache[task_id])})"
        )
    
    def receive_sketch(
        self,
        task_id: str,
        sketch: ProgramSketch,
    ) -> None:
        """Receive a program sketch from LLM module.
        
        Program sketches are partial programs with holes that guide
        the synthesis process.
        
        Args:
            task_id: ID of the task
            sketch: The program sketch to receive
        """
        if not self.enabled or not self.receive_macros_enabled:
            return
        
        # Validate sketch
        if not sketch.validate():
            logger.warning(f"Invalid sketch received for task {task_id}")
            return
        
        # Store in cache
        if task_id not in self.sketch_cache:
            self.sketch_cache[task_id] = []
        self.sketch_cache[task_id].append(sketch)
        
        # Update statistics
        self.stats["sketches_received"] += 1
        
        logger.info(
            f"Received sketch for task {task_id} "
            f"(holes={len(sketch.get_holes())}, total: {len(self.sketch_cache[task_id])})"
        )
    
    def verify_llm_candidate(
        self,
        program: Program,
        examples: List[tuple[Grid, Grid]],
    ) -> Dict[str, Any]:
        """Verify an LLM-generated candidate program.
        
        All LLM candidates MUST go through SMT verification to ensure
        consistency before being submitted to the arbitrator.
        
        Args:
            program: The candidate program to verify
            examples: List of (input, output) grid pairs
            
        Returns:
            Verification result dictionary with status and details
        """
        if not self.enabled or not self.verify_candidates_enabled:
            return {
                "status": "skipped",
                "reason": "verification disabled",
            }
        
        # Update statistics
        self.stats["candidates_verified"] += 1
        
        # Get SMT verifier
        if self._smt_verifier is None:
            # Lazy initialization of SMT verifier
            try:
                from arc.symbolic.smt.verifier import BatchVerifier
                self._smt_verifier = BatchVerifier(self.config)
            except Exception as e:
                logger.error(f"Failed to initialize SMT verifier: {e}")
                return {
                    "status": "error",
                    "reason": f"verifier initialization failed: {e}",
                }
        
        try:
            # Perform SMT verification
            result = self._smt_verifier.verify_single(program, examples)
            
            # Update statistics
            if result.get("status") == "sat":
                self.stats["candidates_passed"] += 1
                logger.info(f"LLM candidate passed verification")
            else:
                self.stats["candidates_failed"] += 1
                logger.info(f"LLM candidate failed verification: {result.get('status')}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error during LLM candidate verification: {e}")
            self.stats["candidates_failed"] += 1
            return {
                "status": "error",
                "reason": str(e),
            }
    
    def send_failure_feedback(
        self,
        task_id: str,
        failure_type: str,
        prompt_adjustment: str,
    ) -> None:
        """Send failure feedback to LLM module.
        
        When synthesis fails, this method sends feedback to the LLM module
        to help it adjust its prompts and improve future generations.
        
        Args:
            task_id: ID of the task that failed
            failure_type: Type of failure (e.g., "verification_failed", "invalid_syntax")
            prompt_adjustment: Suggested prompt adjustment
        """
        if not self.enabled or not self.send_feedback_enabled:
            return
        
        # Create feedback message
        message = Message(
            type="symbolic_failure_llm",
            task_id=task_id,
            payload={
                "failure_type": failure_type,
                "prompt_adjustment": prompt_adjustment,
            },
        )
        
        # Send message
        success = self.message_queue.put(message, block=False)
        
        if success:
            self.stats["feedback_sent"] += 1
            logger.info(f"Sent failure feedback to LLM for task {task_id}: {failure_type}")
        else:
            logger.warning(f"Failed to send LLM feedback for task {task_id} (queue full)")
    
    def get_macros(self, task_id: str) -> List[DSLMacro]:
        """Get all DSL macros for a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of DSL macros for the task
        """
        return self.macro_cache.get(task_id, [])
    
    def get_sketches(self, task_id: str) -> List[ProgramSketch]:
        """Get all program sketches for a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of program sketches for the task
        """
        return self.sketch_cache.get(task_id, [])
    
    def clear_cache(self, task_id: Optional[str] = None) -> None:
        """Clear cached macros and sketches.
        
        Args:
            task_id: ID of task to clear (None = clear all)
        """
        if task_id is None:
            self.macro_cache.clear()
            self.sketch_cache.clear()
            logger.info("Cleared all cached macros and sketches")
        else:
            self.macro_cache.pop(task_id, None)
            self.sketch_cache.pop(task_id, None)
            logger.info(f"Cleared cached data for task {task_id}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get coordination statistics.
        
        Returns:
            Dictionary of statistics
        """
        return self.stats.copy()
    
    def _handle_macro_message(self, message: Message) -> None:
        """Handle incoming DSL macro message.
        
        Args:
            message: The message containing a DSL macro
        """
        try:
            task_id = message.task_id
            macro_data = message.payload.get("macro")
            
            # Deserialize macro
            if isinstance(macro_data, DSLMacro):
                macro = macro_data
            elif isinstance(macro_data, dict):
                macro = DSLMacro.from_dict(macro_data)
            else:
                logger.warning(f"Invalid macro data type: {type(macro_data)}")
                return
            
            # Receive macro
            self.receive_dsl_macro(task_id, macro)
        
        except Exception as e:
            logger.error(f"Error handling macro message: {e}")
    
    def _handle_sketch_message(self, message: Message) -> None:
        """Handle incoming sketch message.
        
        Args:
            message: The message containing a program sketch
        """
        try:
            task_id = message.task_id
            sketch_data = message.payload.get("sketch")
            
            # Deserialize sketch
            if isinstance(sketch_data, ProgramSketch):
                sketch = sketch_data
            elif isinstance(sketch_data, dict):
                sketch = ProgramSketch.from_dict(sketch_data)
            else:
                logger.warning(f"Invalid sketch data type: {type(sketch_data)}")
                return
            
            # Receive sketch
            self.receive_sketch(task_id, sketch)
        
        except Exception as e:
            logger.error(f"Error handling sketch message: {e}")
    
    def shutdown(self) -> None:
        """Shutdown the coordinator and clean up resources."""
        logger.info("Shutting down LLMCoordinator")
        
        # Unregister handlers
        if self.enabled:
            self.message_queue.unregister_handler("llm_macro", self._handle_macro_message)
            self.message_queue.unregister_handler("llm_sketch", self._handle_sketch_message)
        
        # Clear caches
        self.clear_cache()
