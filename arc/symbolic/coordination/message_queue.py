"""Thread-safe message queue for module coordination.

This module provides a thread-safe message queue infrastructure for
communication between the symbolic solver and other modules.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a message in the coordination system.
    
    Attributes:
        type: Message type (e.g., "ttt_invariants", "llm_sketch", "symbolic_failure")
        task_id: ID of the task this message relates to
        payload: Message payload (arbitrary data)
        timestamp: Unix timestamp when message was created
        metadata: Additional metadata
    """
    
    type: str
    task_id: str
    payload: Any
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize Message to dictionary.
        
        Returns:
            Dictionary representation of the message
        """
        return {
            "type": self.type,
            "task_id": self.task_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        """Deserialize Message from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed Message
        """
        return cls(
            type=data["type"],
            task_id=data["task_id"],
            payload=data["payload"],
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )
    
    def to_json(self) -> str:
        """Serialize Message to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> Message:
        """Deserialize Message from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            Reconstructed Message
        """
        data = json.loads(json_str)
        return cls.from_dict(data)


class MessageQueue:
    """Thread-safe message queue for module coordination.
    
    This queue supports:
    - Thread-safe put/get operations
    - Message filtering by type and task_id
    - Message routing to registered handlers
    - Monitoring and logging
    
    Attributes:
        max_size: Maximum queue size (0 = unlimited)
        config: Configuration dictionary
    """
    
    def __init__(self, max_size: int = 0, config: Optional[Dict[str, Any]] = None):
        """Initialize message queue.
        
        Args:
            max_size: Maximum queue size (0 = unlimited)
            config: Configuration dictionary
        """
        self.max_size = max_size
        self.config = config or {}
        
        # Internal queue
        self._queue: queue.Queue = queue.Queue(maxsize=max_size)
        
        # Message handlers
        self._handlers: Dict[str, List[Callable[[Message], None]]] = {}
        self._handler_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_dropped": 0,
        }
        self._stats_lock = threading.Lock()
        
        # Logging
        self.enable_logging = self.config.get("enable_logging", True)
        self.log_file = self.config.get("log_file")
        
        # Background processing thread
        self._running = False
        self._processor_thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start background message processing."""
        if self._running:
            return
        
        self._running = True
        self._processor_thread = threading.Thread(
            target=self._process_messages,
            daemon=True
        )
        self._processor_thread.start()
        logger.info("Message queue started")
    
    def stop(self) -> None:
        """Stop background message processing."""
        if not self._running:
            return
        
        self._running = False
        if self._processor_thread:
            self._processor_thread.join(timeout=5.0)
        logger.info("Message queue stopped")
    
    def put(self, message: Message, block: bool = True, timeout: Optional[float] = None) -> bool:
        """Put a message into the queue.
        
        Args:
            message: The message to put
            block: Whether to block if queue is full
            timeout: Timeout in seconds (None = wait forever)
            
        Returns:
            True if message was added, False if queue was full
        """
        try:
            self._queue.put(message, block=block, timeout=timeout)
            
            with self._stats_lock:
                self._stats["messages_sent"] += 1
            
            if self.enable_logging:
                logger.debug(f"Message queued: type={message.type}, task_id={message.task_id}")
                self._log_message(message, "SENT")
            
            return True
        
        except queue.Full:
            with self._stats_lock:
                self._stats["messages_dropped"] += 1
            
            logger.warning(f"Message queue full, dropping message: {message.type}")
            return False
    
    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Message]:
        """Get a message from the queue.
        
        Args:
            block: Whether to block if queue is empty
            timeout: Timeout in seconds (None = wait forever)
            
        Returns:
            The next message, or None if queue is empty (non-blocking mode)
        """
        try:
            message = self._queue.get(block=block, timeout=timeout)
            
            with self._stats_lock:
                self._stats["messages_received"] += 1
            
            if self.enable_logging:
                logger.debug(f"Message retrieved: type={message.type}, task_id={message.task_id}")
                self._log_message(message, "RECEIVED")
            
            return message
        
        except queue.Empty:
            return None
    
    def get_filtered(
        self,
        message_type: Optional[str] = None,
        task_id: Optional[str] = None,
        timeout: float = 1.0,
    ) -> List[Message]:
        """Get all messages matching the filter criteria.
        
        Args:
            message_type: Filter by message type (None = any type)
            task_id: Filter by task ID (None = any task)
            timeout: Maximum time to wait for messages
            
        Returns:
            List of matching messages
        """
        messages = []
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                message = self._queue.get(block=True, timeout=0.1)
                
                # Check if message matches filter
                if message_type and message.type != message_type:
                    # Put back non-matching message
                    self._queue.put(message)
                    continue
                
                if task_id and message.task_id != task_id:
                    # Put back non-matching message
                    self._queue.put(message)
                    continue
                
                messages.append(message)
                
            except queue.Empty:
                continue
        
        return messages
    
    def register_handler(self, message_type: str, handler: Callable[[Message], None]) -> None:
        """Register a handler for a specific message type.
        
        Args:
            message_type: The message type to handle
            handler: Callback function to handle messages
        """
        with self._handler_lock:
            if message_type not in self._handlers:
                self._handlers[message_type] = []
            self._handlers[message_type].append(handler)
        
        logger.info(f"Registered handler for message type: {message_type}")
    
    def unregister_handler(self, message_type: str, handler: Callable[[Message], None]) -> None:
        """Unregister a handler for a specific message type.
        
        Args:
            message_type: The message type
            handler: The handler to remove
        """
        with self._handler_lock:
            if message_type in self._handlers:
                try:
                    self._handlers[message_type].remove(handler)
                except ValueError:
                    pass
    
    def _process_messages(self) -> None:
        """Background thread that processes messages and routes to handlers."""
        while self._running:
            try:
                message = self._queue.get(block=True, timeout=0.5)
                
                # Route to handlers
                with self._handler_lock:
                    handlers = self._handlers.get(message.type, [])
                
                for handler in handlers:
                    try:
                        handler(message)
                    except Exception as e:
                        logger.error(f"Handler error for {message.type}: {e}")
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Message processing error: {e}")
    
    def _log_message(self, message: Message, direction: str) -> None:
        """Log a message to file.
        
        Args:
            message: The message to log
            direction: "SENT" or "RECEIVED"
        """
        if not self.log_file:
            return
        
        try:
            log_entry = {
                "direction": direction,
                "timestamp": message.timestamp,
                "type": message.type,
                "task_id": message.task_id,
                "metadata": message.metadata,
            }
            
            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        
        except Exception as e:
            logger.error(f"Failed to log message: {e}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics.
        
        Returns:
            Dictionary of statistics
        """
        with self._stats_lock:
            return self._stats.copy()
    
    def clear(self) -> None:
        """Clear all messages from the queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        
        logger.info("Message queue cleared")
    
    def size(self) -> int:
        """Get current queue size.
        
        Returns:
            Number of messages in queue
        """
        return self._queue.qsize()
    
    def is_empty(self) -> bool:
        """Check if queue is empty.
        
        Returns:
            True if queue is empty, False otherwise
        """
        return self._queue.empty()
    
    def is_full(self) -> bool:
        """Check if queue is full.
        
        Returns:
            True if queue is full, False otherwise
        """
        return self._queue.full()
