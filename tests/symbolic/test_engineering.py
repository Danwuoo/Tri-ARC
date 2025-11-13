"""Unit tests for engineering infrastructure."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.engineering import (
    AdaptiveBudgetManager,
    ArtifactManager,
    CacheManager,
    CircuitBreaker,
    FallbackStrategy,
    SynthesisMetrics,
    TelemetryCollector,
    TimeoutGuard,
)
from arc.symbolic.engineering.budget import TaskFeatures
from arc.symbolic.engineering.circuit_breaker import (
    CircuitBreakerOpenError,
    FallbackManager,
    ResourceLimitGuard,
)
from arc.symbolic.engineering.metrics import AggregateMetrics, MetricsCollector
from arc.symbolic.engineering.telemetry import PhaseTimer
from arc.symbolic.engineering.timeout import SoftTimeoutGuard
from arc.symbolic.search.budget import SearchBudget


class TestCacheManager:
    """Tests for CacheManager."""
    
    def test_lru_cache_basic(self):
        """Test basic LRU cache operations."""
        cache = CacheManager(program_cache_size=3)
        
        # Add items
        cache.program_cache.put("key1", "value1")
        cache.program_cache.put("key2", "value2")
        cache.program_cache.put("key3", "value3")
        
        # All should be present
        assert cache.program_cache.get("key1") == "value1"
        assert cache.program_cache.get("key2") == "value2"
        assert cache.program_cache.get("key3") == "value3"
        
        # Add fourth item, should evict key1 (LRU)
        cache.program_cache.put("key4", "value4")
        assert cache.program_cache.get("key1") is None
        assert cache.program_cache.get("key4") == "value4"
    
    def test_cache_hit_miss_tracking(self):
        """Test cache hit/miss tracking."""
        cache = CacheManager()
        
        cache.program_cache.put("key1", "value1")
        
        # Hit
        cache.program_cache.get("key1")
        # Miss
        cache.program_cache.get("key2")
        
        stats = cache.program_cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
    
    def test_program_caching(self):
        """Test program semantic caching."""
        cache = CacheManager()
        
        program = Program(stages=[Stage(operator="rotate", arguments=[90])])
        examples = [([[1, 2], [3, 4]], [[3, 1], [4, 2]])]
        
        # Cache program
        key = cache.cache_program_semantics(program, examples)
        assert key is not None
        
        # Retrieve cached program
        cached = cache.get_cached_program(key)
        assert cached == program
    
    def test_fragment_caching(self):
        """Test fragment caching."""
        cache = CacheManager()
        
        fragment = {"id": "frag1", "stages": []}
        cache.cache_fragment("frag1", fragment)
        
        cached = cache.get_cached_fragment("frag1")
        assert cached == fragment
    
    def test_verification_caching(self):
        """Test verification result caching."""
        cache = CacheManager()
        
        program = Program(stages=[Stage(operator="rotate", arguments=[90])])
        examples = [([[1, 2], [3, 4]], [[3, 1], [4, 2]])]
        result = {"status": "sat", "time": 1.5}
        
        # Cache verification result
        cache.cache_verification_result(program, examples, result)
        
        # Retrieve cached result
        cached = cache.get_cached_verification(program, examples)
        assert cached == result
    
    def test_cache_stats(self):
        """Test cache statistics."""
        cache = CacheManager()
        
        cache.program_cache.put("key1", "value1")
        cache.fragment_cache.put("frag1", {})
        
        stats = cache.get_stats()
        assert "program_cache" in stats
        assert "fragment_cache" in stats
        assert "verification_cache" in stats
        assert stats["program_cache"]["size"] == 1
        assert stats["fragment_cache"]["size"] == 1


class TestAdaptiveBudgetManager:
    """Tests for AdaptiveBudgetManager."""
    
    def test_task_features_extraction(self):
        """Test task feature extraction."""
        task = {
            "train": [
                {"input": [[1, 2], [3, 4]], "output": [[4, 3], [2, 1]]}
            ]
        }
        
        features = TaskFeatures.from_task(task)
        assert features.grid_size == 4
        assert features.color_count > 0
    
    def test_small_grid_budget_allocation(self):
        """Test budget allocation for small grids."""
        manager = AdaptiveBudgetManager()
        
        task = {"train": [{"input": [[1, 2]], "output": [[2, 1]]}]}
        global_budget = SearchBudget(
            max_depth=10,
            max_expansions=1000,
            soft_timeout_s=60.0,
            hard_timeout_s=90.0,
        )
        
        adapted = manager.allocate_budget(task, global_budget)
        
        # Small grids should get deeper search
        assert adapted.max_depth > global_budget.max_depth
    
    def test_large_grid_budget_allocation(self):
        """Test budget allocation for large grids."""
        manager = AdaptiveBudgetManager()
        
        # Create large grid task
        large_grid = [[i for i in range(30)] for _ in range(30)]
        task = {"train": [{"input": large_grid, "output": large_grid}]}
        global_budget = SearchBudget(
            max_depth=10,
            max_expansions=1000,
            soft_timeout_s=60.0,
            hard_timeout_s=90.0,
        )
        
        adapted = manager.allocate_budget(task, global_budget)
        
        # Large grids should get shallower search
        assert adapted.max_depth < global_budget.max_depth
    
    def test_performance_tracking(self):
        """Test performance tracking."""
        manager = AdaptiveBudgetManager()
        
        features = TaskFeatures.default()
        manager.record_performance(
            task_id="task_001",
            success=True,
            elapsed_time=45.2,
            expansions=1234,
            features=features,
        )
        
        stats = manager.get_statistics()
        assert stats["total_tasks"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["avg_time"] == 45.2


class TestTimeoutGuard:
    """Tests for TimeoutGuard."""
    
    def test_timeout_check(self):
        """Test timeout checking."""
        guard = TimeoutGuard(timeout_s=0.1)
        
        assert guard.check() is True
        time.sleep(0.15)
        assert guard.check() is False
    
    def test_remaining_time(self):
        """Test remaining time calculation."""
        guard = TimeoutGuard(timeout_s=1.0)
        
        remaining = guard.remaining()
        assert 0.9 < remaining <= 1.0
        
        time.sleep(0.5)
        remaining = guard.remaining()
        assert 0.4 < remaining < 0.6
    
    def test_cooperative_cancellation(self):
        """Test cooperative cancellation."""
        guard = TimeoutGuard(timeout_s=10.0)
        
        assert guard.check() is True
        guard.cancel()
        assert guard.check() is False
        assert guard.is_cancelled() is True
    
    def test_context_manager(self):
        """Test context manager usage."""
        with TimeoutGuard(timeout_s=1.0) as guard:
            assert guard.check() is True
    
    def test_soft_timeout_guard(self):
        """Test soft/hard timeout guard."""
        guard = SoftTimeoutGuard(soft_timeout_s=0.1, hard_timeout_s=0.2)
        
        assert guard.check_soft() is True
        assert guard.check_hard() is True
        
        time.sleep(0.15)
        assert guard.check_soft() is False
        assert guard.check_hard() is True
        assert guard.is_soft_timeout() is True
        
        time.sleep(0.1)
        assert guard.check_hard() is False


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""
    
    def test_circuit_closed_state(self):
        """Test circuit breaker in closed state."""
        breaker = CircuitBreaker(failure_threshold=3)
        
        def success_func():
            return "success"
        
        result = breaker.call(success_func)
        assert result == "success"
        assert breaker.state.value == "closed"
    
    def test_circuit_opens_on_failures(self):
        """Test circuit opens after threshold failures."""
        breaker = CircuitBreaker(failure_threshold=3)
        
        def failing_func():
            raise ValueError("Test error")
        
        # Trigger failures
        for _ in range(3):
            try:
                breaker.call(failing_func)
            except ValueError:
                pass
        
        assert breaker.state.value == "open"
    
    def test_circuit_with_fallback(self):
        """Test circuit breaker with fallback."""
        breaker = CircuitBreaker(failure_threshold=2)
        
        def failing_func():
            raise ValueError("Test error")
        
        def fallback_func():
            return "fallback"
        
        # Trigger failures to open circuit
        for _ in range(2):
            try:
                breaker.call(failing_func, fallback=fallback_func)
            except ValueError:
                pass
        
        # Circuit is open, should use fallback
        result = breaker.call(failing_func, fallback=fallback_func)
        assert result == "fallback"
    
    def test_circuit_recovery(self):
        """Test circuit breaker recovery."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1,
        )
        
        def failing_func():
            raise ValueError("Test error")
        
        def success_func():
            return "success"
        
        # Open circuit
        for _ in range(2):
            try:
                breaker.call(failing_func)
            except ValueError:
                pass
        
        assert breaker.state.value == "open"
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Should attempt half-open
        result = breaker.call(success_func)
        assert result == "success"
        assert breaker.state.value == "closed"
    
    def test_fallback_manager(self):
        """Test fallback manager."""
        manager = FallbackManager()
        
        manager.register_strategy("smt_solver", FallbackStrategy.RETURN_NONE)
        manager.register_strategy("search", FallbackStrategy.RETURN_EMPTY)
        
        result1 = manager.execute_fallback("smt_solver", ValueError())
        assert result1 is None
        
        result2 = manager.execute_fallback("search", ValueError())
        assert result2 == []
        
        stats = manager.get_stats()
        assert stats["total_fallbacks"] == 2
    
    def test_resource_limit_guard(self):
        """Test resource limit guard."""
        guard = ResourceLimitGuard(max_nodes=100, max_expansions=50)
        
        assert guard.check_nodes() is True
        guard.increment_nodes(50)
        assert guard.check_nodes() is True
        guard.increment_nodes(60)
        assert guard.check_nodes() is False
        
        assert guard.check_expansions() is True
        guard.increment_expansions(60)
        assert guard.check_expansions() is False


class TestSynthesisMetrics:
    """Tests for SynthesisMetrics."""
    
    def test_metrics_creation(self):
        """Test metrics creation."""
        metrics = SynthesisMetrics(
            task_id="task_001",
            elapsed_s=45.2,
            expansions=1234,
            generated_nodes=5678,
            pruned_nodes=3456,
            verified_candidates=12,
        )
        
        assert metrics.task_id == "task_001"
        assert metrics.elapsed_s == 45.2
    
    def test_pruning_rate_calculation(self):
        """Test pruning rate calculation."""
        metrics = SynthesisMetrics(
            task_id="task_001",
            elapsed_s=45.2,
            expansions=1234,
            generated_nodes=6000,
            pruned_nodes=4000,
            verified_candidates=12,
        )
        
        pruning_rate = metrics.compute_pruning_rate()
        assert pruning_rate == 0.4
    
    def test_cache_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        metrics = SynthesisMetrics(
            task_id="task_001",
            elapsed_s=45.2,
            expansions=1234,
            generated_nodes=5678,
            pruned_nodes=3456,
            verified_candidates=12,
            cache_hits=80,
            cache_misses=20,
        )
        
        hit_rate = metrics.compute_cache_hit_rate()
        assert hit_rate == 0.8
    
    def test_metrics_serialization(self):
        """Test metrics serialization."""
        metrics = SynthesisMetrics(
            task_id="task_001",
            elapsed_s=45.2,
            expansions=1234,
            generated_nodes=5678,
            pruned_nodes=3456,
            verified_candidates=12,
        )
        
        data = metrics.to_dict()
        assert data["task_id"] == "task_001"
        assert data["elapsed_s"] == 45.2
        
        restored = SynthesisMetrics.from_dict(data)
        assert restored.task_id == metrics.task_id
    
    def test_aggregate_metrics(self):
        """Test aggregate metrics."""
        aggregate = AggregateMetrics()
        
        metrics1 = SynthesisMetrics(
            task_id="task_001",
            elapsed_s=45.2,
            expansions=1234,
            generated_nodes=5678,
            pruned_nodes=3456,
            verified_candidates=12,
            success=True,
        )
        
        metrics2 = SynthesisMetrics(
            task_id="task_002",
            elapsed_s=30.5,
            expansions=890,
            generated_nodes=4000,
            pruned_nodes=2000,
            verified_candidates=8,
            success=False,
        )
        
        aggregate.add_metrics(metrics1)
        aggregate.add_metrics(metrics2)
        
        assert aggregate.total_tasks == 2
        assert aggregate.successful_tasks == 1
        assert aggregate.compute_success_rate() == 0.5
        assert aggregate.compute_avg_time() == (45.2 + 30.5) / 2
    
    def test_metrics_collector(self):
        """Test metrics collector."""
        collector = MetricsCollector()
        
        collector.start_task("task_001")
        collector.record_expansion(10)
        collector.record_node_generation(50)
        collector.record_node_pruning(30)
        collector.record_verification(5)
        
        metrics = collector.finish_task(success=True, elapsed_s=45.2)
        
        assert metrics.task_id == "task_001"
        assert metrics.expansions == 10
        assert metrics.generated_nodes == 50
        assert metrics.pruned_nodes == 30
        assert metrics.verified_candidates == 5


class TestTelemetryCollector:
    """Tests for TelemetryCollector."""
    
    def test_event_recording(self):
        """Test event recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = TelemetryCollector(log_dir=tmpdir)
            
            telemetry.record_search_event(
                event_type="candidate_found",
                payload={"program_length": 5},
                task_id="task_001",
            )
            
            telemetry.flush()
            
            # Check event was written
            events_file = Path(tmpdir) / "events.jsonl"
            assert events_file.exists()
            
            with open(events_file) as f:
                event = json.loads(f.readline())
                assert event["event_type"] == "candidate_found"
                assert event["task_id"] == "task_001"
    
    def test_metric_recording(self):
        """Test metric recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = TelemetryCollector(log_dir=tmpdir)
            
            telemetry.record_metric(
                metric_name="search_time",
                value=45.2,
                tags={"strategy": "beam"},
                task_id="task_001",
            )
            
            telemetry.flush()
            
            # Check metric was written
            metrics_file = Path(tmpdir) / "metrics.jsonl"
            assert metrics_file.exists()
            
            with open(metrics_file) as f:
                metric = json.loads(f.readline())
                assert metric["metric"] == "search_time"
                assert metric["value"] == 45.2
    
    def test_phase_timing(self):
        """Test phase timing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = TelemetryCollector(log_dir=tmpdir)
            
            with PhaseTimer(telemetry, "search", "task_001") as timer:
                time.sleep(0.1)
                timer.mark_success()
            
            telemetry.flush()
            
            # Check phase events were written
            events_file = Path(tmpdir) / "events.jsonl"
            with open(events_file) as f:
                lines = f.readlines()
                assert len(lines) == 2  # start and end
                
                start_event = json.loads(lines[0])
                assert start_event["event_type"] == "phase_start"
                
                end_event = json.loads(lines[1])
                assert end_event["event_type"] == "phase_end"
                assert end_event["payload"]["success"] is True
    
    def test_context_manager(self):
        """Test telemetry context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with TelemetryCollector(log_dir=tmpdir) as telemetry:
                telemetry.record_search_event(
                    event_type="test",
                    payload={},
                )
            
            # Should auto-flush on exit
            events_file = Path(tmpdir) / "events.jsonl"
            assert events_file.exists()


class TestArtifactManager:
    """Tests for ArtifactManager."""
    
    def test_save_load_program(self):
        """Test program save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = ArtifactManager(artifact_dir=tmpdir)
            
            program = Program(stages=[Stage(operator="rotate", arguments=[90])])
            
            # Save program
            path = artifacts.save_program(
                task_id="task_001",
                program=program,
                metadata={"score": 0.95},
            )
            assert path.exists()
            
            # Load program
            loaded = artifacts.load_program("task_001")
            assert loaded is not None
            assert loaded["task_id"] == "task_001"
            assert loaded["metadata"]["score"] == 0.95
    
    def test_save_load_evidence(self):
        """Test evidence save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = ArtifactManager(artifact_dir=tmpdir)
            
            evidence = {
                "counterexamples": [{"input": [[1, 2]], "output": [[2, 1]]}],
                "proofs": [],
            }
            
            # Save evidence
            path = artifacts.save_evidence("task_001", evidence)
            assert path.exists()
            
            # Load evidence
            loaded = artifacts.load_evidence("task_001")
            assert loaded is not None
            assert "counterexamples" in loaded["evidence"]
    
    def test_save_load_invariants(self):
        """Test invariants save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = ArtifactManager(artifact_dir=tmpdir)
            
            invariants = [
                {"type": "color_conservation", "confidence": 0.9},
                {"type": "object_count", "confidence": 0.8},
            ]
            
            # Save invariants
            path = artifacts.save_invariants("task_001", invariants, source="symbolic")
            assert path.exists()
            
            # Load invariants
            loaded = artifacts.load_invariants("task_001", source="symbolic")
            assert loaded is not None
            assert len(loaded["invariants"]) == 2
    
    def test_save_load_checkpoint(self):
        """Test checkpoint save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = ArtifactManager(artifact_dir=tmpdir)
            
            state = {
                "search_state": {"depth": 5, "nodes": 100},
                "cache_state": {"hits": 50, "misses": 10},
            }
            
            # Save checkpoint
            path = artifacts.save_checkpoint("checkpoint_001", state)
            assert path.exists()
            
            # Load checkpoint
            loaded = artifacts.load_checkpoint("checkpoint_001")
            assert loaded is not None
            assert loaded["search_state"]["depth"] == 5
    
    def test_compression(self):
        """Test artifact compression."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = ArtifactManager(
                artifact_dir=tmpdir,
                enable_compression=True,
                compression_threshold_bytes=100,
            )
            
            # Create large program
            large_program = Program(
                stages=[Stage(operator=f"op_{i}", arguments=[i]) for i in range(100)]
            )
            
            # Save (should compress)
            path = artifacts.save_program("task_001", large_program)
            
            # Should have .gz extension
            assert path.suffix == ".gz" or path.name.endswith(".json.gz")
            
            # Should still load correctly
            loaded = artifacts.load_program("task_001")
            assert loaded is not None
    
    def test_list_artifacts(self):
        """Test artifact listing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = ArtifactManager(artifact_dir=tmpdir)
            
            # Save multiple programs
            program = Program(stages=[])
            artifacts.save_program("task_001", program)
            artifacts.save_program("task_002", program)
            
            # List programs
            programs = artifacts.list_programs()
            assert len(programs) >= 2
            assert any("task_001" in p for p in programs)
    
    def test_artifact_stats(self):
        """Test artifact statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = ArtifactManager(artifact_dir=tmpdir)
            
            program = Program(stages=[])
            artifacts.save_program("task_001", program)
            
            stats = artifacts.get_stats()
            assert stats["programs_count"] >= 1
            assert stats["total_size_bytes"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
