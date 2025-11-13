"""Module coordination infrastructure for TTT and LLM integration.

This module provides data structures and coordinators for exchanging
information between the symbolic solver and other modules (TTT, LLM).
"""

from arc.symbolic.coordination.types import (
    DSLMacro,
    Invariant,
    Relation,
)
from arc.symbolic.coordination.ttt_coordinator import TTTCoordinator
from arc.symbolic.coordination.llm_coordinator import LLMCoordinator
from arc.symbolic.coordination.message_queue import MessageQueue, Message
from arc.symbolic.coordination.integration import CoordinationIntegration

__all__ = [
    "Invariant",
    "Relation",
    "DSLMacro",
    "TTTCoordinator",
    "LLMCoordinator",
    "MessageQueue",
    "Message",
    "CoordinationIntegration",
]
