"""Unit tests for module coordination infrastructure.

Tests cover:
- Invariant and Relation data structures
- DSLMacro data structure
- TTTCoordinator functionality
- LLMCoordinator functionality
- MessageQueue operations
- CoordinationIntegration
"""

import json
import time
from pathlib import Path

import pytest

from arc.symbolic.coordination import (
    CoordinationIntegration,
    DSLMacro,
    Invariant,
    LLMCoordinator,
    Message,
    MessageQueue,
    Relation,
    TTTCoordinator,
)
from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.ir.sketch import Hole, ProgramSketch


class TestInvariant:
    """Test Invariant data structure."""
    
    def test_create_invariant(self):
        """Test creating an invariant."""
        inv = Invariant(
            type="color_conservation",
            constraint={"colors": [0, 1, 2]},
            confidence=0.9,
            source="ttt",
        )
        
        assert inv.type == "color_conservation"
        assert inv.confidence == 0.9
        assert inv.source == "ttt"
    
    def test_invariant_validation(self):
        """Test invariant validation."""
        # Valid invariant
        inv = Invariant(
            type="color_conservation",
            constraint={},
            confidence=0.9,
            source="ttt",
        )
        assert inv.validate()
        
        # Invalid confidence
        inv_invalid = Invariant(
            type="color_conservation",
            constraint={},
            confidence=1.5,
            source="ttt",
        )
        assert not inv_invalid.validate()
    
    def test_invariant_serialization(self):
        """Test invariant serialization and deserialization."""
        inv = Invariant(
            type="object_count",
            constraint={"min": 2, "max": 5},
            confidence=0.85,
            source="symbolic",
        )
        
        # To dict
        inv_dict = inv.to_dict()
        assert inv_dict["type"] == "object_count"
        assert inv_dict["confidence"] == 0.85
        
        # From dict
        inv_restored = Invariant.from_dict(inv_dict)
        assert inv_restored.type == inv.type
        assert inv_restored.confidence == inv.confidence
        assert inv_restored.source == inv.source
        
        # To/from JSON
        inv_json = inv.to_json()
        inv_from_json = Invariant.from_json(inv_json)
        assert inv_from_json.type == inv.type


class TestRelation:
    """Test Relation data structure."""
    
    def test_create_relation(self):
        """Test creating a relation."""
        rel = Relation(
            relation_type="spatial",
            objects=[1, 2],
            parameters={"distance": 3, "direction": "horizontal"},
            confidence=0.95,
        )
        
        assert rel.relation_type == "spatial"
        assert len(rel.objects) == 2
        assert rel.parameters["distance"] == 3
    
    def test_relation_validation(self):
        """Test relation validation."""
        # Valid relation
        rel = Relation(
            relation_type="color",
            objects=[1, 2, 3],
            confidence=0.8,
        )
        assert rel.validate()
        
        # Invalid - empty objects
        rel_invalid = Relation(
            relation_type="color",
            objects=[],
            confidence=0.8,
        )
        assert not rel_invalid.validate()
    
    def test_relation_serialization(self):
        """Test relation serialization."""
        rel = Relation(
            relation_type="size",
            objects=[1, 2],
            parameters={"ratio": 2.0},
            confidence=0.9,
        )
        
        rel_dict = rel.to_dict()
        rel_restored = Relation.from_dict(rel_dict)
        
        assert rel_restored.relation_type == rel.relation_type
        assert rel_restored.objects == rel.objects
        assert rel_restored.confidence == rel.confidence


class TestDSLMacro:
    """Test DSLMacro data structure."""
    
    def test_create_macro(self):
        """Test creating a DSL macro."""
        macro = DSLMacro(
            name="rotate_and_reflect",
            parameters=["angle", "axis"],
            body=[
                Stage(operator="rotate", arguments=("angle",)),
                Stage(operator="reflect", arguments=("axis",)),
            ],
            documentation="Rotates and reflects a grid",
            confidence=0.85,
        )
        
        assert macro.name == "rotate_and_reflect"
        assert len(macro.parameters) == 2
        assert len(macro.body) == 2
    
    def test_macro_validation(self):
        """Test macro validation."""
        # Valid macro
        macro = DSLMacro(
            name="test_macro",
            parameters=["p1"],
            body=[Stage(operator="op1", arguments=())],
        )
        assert macro.validate()
        
        # Invalid - empty name
        macro_invalid = DSLMacro(
            name="",
            parameters=[],
            body=[Stage(operator="op1", arguments=())],
        )
        assert not macro_invalid.validate()
    
    def test_macro_serialization(self):
        """Test macro serialization."""
        macro = DSLMacro(
            name="test_macro",
            parameters=["p1", "p2"],
            body=[
                Stage(operator="op1", arguments=("p1",)),
                Stage(operator="op2", arguments=("p2",)),
            ],
            documentation="Test macro",
            confidence=0.9,
        )
        
        macro_dict = macro.to_dict()
        macro_restored = DSLMacro.from_dict(macro_dict)
        
        assert macro_restored.name == macro.name
        assert macro_restored.parameters == macro.parameters
        assert len(macro_restored.body) == len(macro.body)
    
    def test_macro_expansion(self):
        """Test macro expansion."""
        macro = DSLMacro(
            name="test_macro",
            parameters=["p1"],
            body=[Stage(operator="op1", arguments=("p1",))],
        )
        
        expanded = macro.expand({"p1": "value1"})
        assert len(expanded) == 1


class TestMessage:
    """Test Message data structure."""
    
    def test_create_message(self):
        """Test creating a message."""
        msg = Message(
            type="ttt_invariants",
            task_id="task_001",
            payload={"invariants": []},
        )
        
        assert msg.type == "ttt_invariants"
        assert msg.task_id == "task_001"
        assert isinstance(msg.timestamp, float)
    
    def test_message_serialization(self):
        """Test message serialization."""
        msg = Message(
            type="llm_sketch",
            task_id="task_002",
            payload={"sketch": "test"},
            metadata={"source": "llm"},
        )
        
        msg_dict = msg.to_dict()
        msg_restored = Message.from_dict(msg_dict)
        
        assert msg_restored.type == msg.type
        assert msg_restored.task_id == msg.task_id
        assert msg_restored.metadata == msg.metadata


class TestMessageQueue:
    """Test MessageQueue functionality."""
    
    def test_create_queue(self):
        """Test creating a message queue."""
        queue = MessageQueue(max_size=10)
        assert queue.max_size == 10
        assert queue.is_empty()
    
    def test_put_get_message(self):
        """Test putting and getting messages."""
        queue = MessageQueue()
        
        msg = Message(
            type="test",
            task_id="task_001",
            payload={"data": "test"},
        )
        
        # Put message
        success = queue.put(msg, block=False)
        assert success
        assert not queue.is_empty()
        
        # Get message
        retrieved = queue.get(block=False)
        assert retrieved is not None
        assert retrieved.type == msg.type
        assert retrieved.task_id == msg.task_id
    
    def test_queue_full(self):
        """Test queue full behavior."""
        queue = MessageQueue(max_size=2)
        
        msg1 = Message(type="test", task_id="task_001", payload={})
        msg2 = Message(type="test", task_id="task_002", payload={})
        msg3 = Message(type="test", task_id="task_003", payload={})
        
        assert queue.put(msg1, block=False)
        assert queue.put(msg2, block=False)
        assert not queue.put(msg3, block=False)  # Should fail
    
    def test_message_filtering(self):
        """Test filtered message retrieval."""
        queue = MessageQueue()
        
        msg1 = Message(type="type_a", task_id="task_001", payload={})
        msg2 = Message(type="type_b", task_id="task_001", payload={})
        msg3 = Message(type="type_a", task_id="task_002", payload={})
        
        queue.put(msg1, block=False)
        queue.put(msg2, block=False)
        queue.put(msg3, block=False)
        
        # Filter by type
        filtered = queue.get_filtered(message_type="type_a", timeout=0.5)
        assert len(filtered) == 2
        assert all(m.type == "type_a" for m in filtered)
    
    def test_queue_stats(self):
        """Test queue statistics."""
        queue = MessageQueue()
        
        msg = Message(type="test", task_id="task_001", payload={})
        queue.put(msg, block=False)
        queue.get(block=False)
        
        stats = queue.get_stats()
        assert stats["messages_sent"] == 1
        assert stats["messages_received"] == 1
    
    def test_handler_registration(self):
        """Test message handler registration."""
        queue = MessageQueue()
        
        handled_messages = []
        
        def handler(msg: Message):
            handled_messages.append(msg)
        
        queue.register_handler("test_type", handler)
        queue.start()
        
        msg = Message(type="test_type", task_id="task_001", payload={})
        queue.put(msg, block=False)
        
        # Give handler time to process
        time.sleep(0.2)
        
        queue.stop()
        
        # Handler should have been called
        assert len(handled_messages) > 0


class TestTTTCoordinator:
    """Test TTTCoordinator functionality."""
    
    def test_create_coordinator(self):
        """Test creating TTT coordinator."""
        config = {
            "coordination": {
                "ttt": {
                    "enabled": True,
                    "receive_invariants": True,
                    "send_feedback": True,
                }
            }
        }
        
        coordinator = TTTCoordinator(config)
        assert coordinator.enabled
        assert coordinator.receive_invariants_enabled
    
    def test_receive_invariants(self):
        """Test receiving invariants."""
        config = {"coordination": {"ttt": {"enabled": True}}}
        coordinator = TTTCoordinator(config)
        
        invariants = [
            Invariant(
                type="color_conservation",
                constraint={},
                confidence=0.9,
                source="ttt",
            )
        ]
        
        coordinator.receive_invariants("task_001", invariants)
        
        retrieved = coordinator.get_invariants("task_001")
        assert len(retrieved) == 1
        assert retrieved[0].type == "color_conservation"
    
    def test_receive_relations(self):
        """Test receiving relations."""
        config = {"coordination": {"ttt": {"enabled": True}}}
        coordinator = TTTCoordinator(config)
        
        relations = [
            Relation(
                relation_type="spatial",
                objects=[1, 2],
                confidence=0.85,
            )
        ]
        
        coordinator.receive_candidate_relations("task_001", relations)
        
        retrieved = coordinator.get_relations("task_001")
        assert len(retrieved) == 1
        assert retrieved[0].relation_type == "spatial"
    
    def test_send_failure_feedback(self):
        """Test sending failure feedback."""
        config = {"coordination": {"ttt": {"enabled": True}}}
        coordinator = TTTCoordinator(config)
        
        coordinator.send_failure_feedback(
            "task_001",
            "search_exhausted",
            {"elapsed_s": 10.0},
        )
        
        stats = coordinator.get_stats()
        assert stats["feedback_sent"] == 1
    
    def test_clear_cache(self):
        """Test clearing cache."""
        config = {"coordination": {"ttt": {"enabled": True}}}
        coordinator = TTTCoordinator(config)
        
        invariants = [
            Invariant(type="test", constraint={}, confidence=0.9, source="ttt")
        ]
        coordinator.receive_invariants("task_001", invariants)
        
        assert len(coordinator.get_invariants("task_001")) == 1
        
        coordinator.clear_cache("task_001")
        assert len(coordinator.get_invariants("task_001")) == 0


class TestLLMCoordinator:
    """Test LLMCoordinator functionality."""
    
    def test_create_coordinator(self):
        """Test creating LLM coordinator."""
        config = {
            "coordination": {
                "llm": {
                    "enabled": True,
                    "receive_macros": True,
                    "verify_candidates": True,
                }
            }
        }
        
        coordinator = LLMCoordinator(config)
        assert coordinator.enabled
        assert coordinator.receive_macros_enabled
    
    def test_receive_macro(self):
        """Test receiving DSL macro."""
        config = {"coordination": {"llm": {"enabled": True}}}
        coordinator = LLMCoordinator(config)
        
        macro = DSLMacro(
            name="test_macro",
            parameters=["p1"],
            body=[Stage(operator="op1", arguments=())],
        )
        
        coordinator.receive_dsl_macro("task_001", macro)
        
        retrieved = coordinator.get_macros("task_001")
        assert len(retrieved) == 1
        assert retrieved[0].name == "test_macro"
    
    def test_receive_sketch(self):
        """Test receiving program sketch."""
        config = {"coordination": {"llm": {"enabled": True}}}
        coordinator = LLMCoordinator(config)
        
        sketch = ProgramSketch(
            stages=[
                Stage(operator="op1", arguments=()),
                Hole(id="hole1", type="operator", domain={"op2", "op3"}),
            ],
        )
        
        coordinator.receive_sketch("task_001", sketch)
        
        retrieved = coordinator.get_sketches("task_001")
        assert len(retrieved) == 1
        assert len(retrieved[0].stages) == 2
    
    def test_send_failure_feedback(self):
        """Test sending failure feedback to LLM."""
        config = {"coordination": {"llm": {"enabled": True}}}
        coordinator = LLMCoordinator(config)
        
        coordinator.send_failure_feedback(
            "task_001",
            "verification_failed",
            "Focus on valid programs",
        )
        
        stats = coordinator.get_stats()
        assert stats["feedback_sent"] == 1
    
    def test_clear_cache(self):
        """Test clearing cache."""
        config = {"coordination": {"llm": {"enabled": True}}}
        coordinator = LLMCoordinator(config)
        
        macro = DSLMacro(
            name="test",
            parameters=[],
            body=[Stage(operator="op1", arguments=())],
        )
        coordinator.receive_dsl_macro("task_001", macro)
        
        assert len(coordinator.get_macros("task_001")) == 1
        
        coordinator.clear_cache("task_001")
        assert len(coordinator.get_macros("task_001")) == 0


class TestCoordinationIntegration:
    """Test CoordinationIntegration."""
    
    def test_create_integration(self):
        """Test creating coordination integration."""
        config = {
            "coordination": {
                "enabled": True,
                "ttt": {"enabled": True},
                "llm": {"enabled": True},
            }
        }
        
        integration = CoordinationIntegration(config)
        assert integration.enabled
        assert integration.ttt_coordinator is not None
        assert integration.llm_coordinator is not None
    
    def test_disabled_integration(self):
        """Test disabled coordination."""
        config = {"coordination": {"enabled": False}}
        
        integration = CoordinationIntegration(config)
        assert not integration.enabled
        assert integration.ttt_coordinator is None
        assert integration.llm_coordinator is None
    
    def test_get_invariants(self):
        """Test getting invariants through integration."""
        config = {
            "coordination": {
                "enabled": True,
                "ttt": {"enabled": True},
                "llm": {"enabled": True},
            }
        }
        
        integration = CoordinationIntegration(config)
        
        invariants = [
            Invariant(type="test", constraint={}, confidence=0.9, source="ttt")
        ]
        integration.ttt_coordinator.receive_invariants("task_001", invariants)
        
        retrieved = integration.get_invariants("task_001")
        assert len(retrieved) == 1
    
    def test_get_sketches(self):
        """Test getting sketches through integration."""
        config = {
            "coordination": {
                "enabled": True,
                "ttt": {"enabled": True},
                "llm": {"enabled": True},
            }
        }
        
        integration = CoordinationIntegration(config)
        
        sketch = ProgramSketch(
            stages=[Stage(operator="op1", arguments=())],
        )
        integration.llm_coordinator.receive_sketch("task_001", sketch)
        
        retrieved = integration.get_sketches("task_001")
        assert len(retrieved) == 1
    
    def test_send_failure_feedback(self):
        """Test sending failure feedback through integration."""
        config = {
            "coordination": {
                "enabled": True,
                "ttt": {"enabled": True},
                "llm": {"enabled": True},
            }
        }
        
        integration = CoordinationIntegration(config)
        
        integration.send_failure_feedback(
            "task_001",
            "search_exhausted",
            {"elapsed_s": 10.0},
        )
        
        stats = integration.get_stats()
        assert stats["ttt"]["feedback_sent"] == 1
        assert stats["llm"]["feedback_sent"] == 1
    
    def test_get_stats(self):
        """Test getting coordination statistics."""
        config = {
            "coordination": {
                "enabled": True,
                "ttt": {"enabled": True},
                "llm": {"enabled": True},
            }
        }
        
        integration = CoordinationIntegration(config)
        
        stats = integration.get_stats()
        assert "ttt" in stats
        assert "llm" in stats
        assert "queue" in stats
    
    def test_shutdown(self):
        """Test shutting down coordination."""
        config = {
            "coordination": {
                "enabled": True,
                "ttt": {"enabled": True},
                "llm": {"enabled": True},
            }
        }
        
        integration = CoordinationIntegration(config)
        integration.shutdown()
        
        # Should not raise any errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
