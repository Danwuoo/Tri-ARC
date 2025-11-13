"""Telemetry collection and structured logging."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class TelemetryCollector:
    """Collects telemetry events and metrics with structured logging."""
    
    def __init__(
        self,
        log_dir: Optional[str] = None,
        enable_file_logging: bool = True,
    ):
        """Initialize telemetry collector.
        
        Args:
            log_dir: Directory for log files
            enable_file_logging: Whether to write logs to files
        """
        self.log_dir = Path(log_dir) if log_dir else Path("logs/symbolic")
        self.enable_file_logging = enable_file_logging
        
        if self.enable_file_logging:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.events_file = self.log_dir / "events.jsonl"
            self.metrics_file = self.log_dir / "metrics.jsonl"
        
        self.events_buffer = []
        self.metrics_buffer = []
        self.buffer_size = 100
    
    def record_search_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        task_id: Optional[str] = None,
    ) -> None:
        """Record a search event.
        
        Args:
            event_type: Type of event (e.g., "node_expanded", "candidate_found")
            payload: Event data
            task_id: Optional task identifier
        """
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "task_id": task_id,
            "payload": payload,
        }
        
        self.events_buffer.append(event)
        
        if len(self.events_buffer) >= self.buffer_size:
            self._flush_events()
    
    def record_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Record a metric value.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            tags: Optional tags for grouping/filtering
            task_id: Optional task identifier
        """
        metric = {
            "timestamp": time.time(),
            "metric": metric_name,
            "value": value,
            "tags": tags or {},
            "task_id": task_id,
        }
        
        self.metrics_buffer.append(metric)
        
        if len(self.metrics_buffer) >= self.buffer_size:
            self._flush_metrics()
    
    def record_phase_start(
        self,
        phase: str,
        task_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record the start of a synthesis phase.
        
        Args:
            phase: Phase name (e.g., "search", "verification", "egraph")
            task_id: Task identifier
            metadata: Optional phase metadata
        """
        self.record_search_event(
            event_type="phase_start",
            payload={
                "phase": phase,
                "metadata": metadata or {},
            },
            task_id=task_id,
        )
    
    def record_phase_end(
        self,
        phase: str,
        task_id: str,
        success: bool,
        elapsed_s: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record the end of a synthesis phase.
        
        Args:
            phase: Phase name
            task_id: Task identifier
            success: Whether phase succeeded
            elapsed_s: Phase duration
            metadata: Optional phase metadata
        """
        self.record_search_event(
            event_type="phase_end",
            payload={
                "phase": phase,
                "success": success,
                "elapsed_s": elapsed_s,
                "metadata": metadata or {},
            },
            task_id=task_id,
        )
        
        # Also record as metric
        self.record_metric(
            metric_name=f"phase_{phase}_time",
            value=elapsed_s,
            tags={"success": str(success)},
            task_id=task_id,
        )
    
    def record_candidate_generated(
        self,
        task_id: str,
        program_length: int,
        depth: int,
        score: float,
    ) -> None:
        """Record candidate program generation.
        
        Args:
            task_id: Task identifier
            program_length: Length of generated program
            depth: Search depth
            score: Candidate score
        """
        self.record_search_event(
            event_type="candidate_generated",
            payload={
                "program_length": program_length,
                "depth": depth,
                "score": score,
            },
            task_id=task_id,
        )
    
    def record_candidate_verified(
        self,
        task_id: str,
        success: bool,
        verification_time: float,
        method: str = "smt",
    ) -> None:
        """Record candidate verification.
        
        Args:
            task_id: Task identifier
            success: Whether verification succeeded
            verification_time: Time taken for verification
            method: Verification method
        """
        self.record_search_event(
            event_type="candidate_verified",
            payload={
                "success": success,
                "verification_time": verification_time,
                "method": method,
            },
            task_id=task_id,
        )
        
        self.record_metric(
            metric_name="verification_time",
            value=verification_time,
            tags={"success": str(success), "method": method},
            task_id=task_id,
        )
    
    def record_egraph_saturation(
        self,
        task_id: str,
        iterations: int,
        rewrites: int,
        unique_programs: int,
        elapsed_s: float,
    ) -> None:
        """Record e-graph saturation.
        
        Args:
            task_id: Task identifier
            iterations: Number of iterations
            rewrites: Number of rewrites applied
            unique_programs: Number of unique programs
            elapsed_s: Time taken
        """
        self.record_search_event(
            event_type="egraph_saturation",
            payload={
                "iterations": iterations,
                "rewrites": rewrites,
                "unique_programs": unique_programs,
                "elapsed_s": elapsed_s,
            },
            task_id=task_id,
        )
        
        self.record_metric(
            metric_name="egraph_rewrites",
            value=rewrites,
            task_id=task_id,
        )
    
    def record_cache_access(
        self,
        cache_type: str,
        hit: bool,
        task_id: Optional[str] = None,
    ) -> None:
        """Record cache access.
        
        Args:
            cache_type: Type of cache (e.g., "program", "fragment", "verification")
            hit: Whether it was a cache hit
            task_id: Optional task identifier
        """
        self.record_search_event(
            event_type="cache_access",
            payload={
                "cache_type": cache_type,
                "hit": hit,
            },
            task_id=task_id,
        )
    
    def record_error(
        self,
        error_type: str,
        message: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an error.
        
        Args:
            error_type: Type of error
            message: Error message
            task_id: Optional task identifier
            metadata: Optional error metadata
        """
        self.record_search_event(
            event_type="error",
            payload={
                "error_type": error_type,
                "message": message,
                "metadata": metadata or {},
            },
            task_id=task_id,
        )
    
    def _flush_events(self) -> None:
        """Flush events buffer to file."""
        if not self.enable_file_logging or not self.events_buffer:
            return
        
        try:
            with open(self.events_file, "a") as f:
                for event in self.events_buffer:
                    f.write(json.dumps(event) + "\n")
            self.events_buffer.clear()
        except Exception as e:
            print(f"Failed to flush events: {e}")
    
    def _flush_metrics(self) -> None:
        """Flush metrics buffer to file."""
        if not self.enable_file_logging or not self.metrics_buffer:
            return
        
        try:
            with open(self.metrics_file, "a") as f:
                for metric in self.metrics_buffer:
                    f.write(json.dumps(metric) + "\n")
            self.metrics_buffer.clear()
        except Exception as e:
            print(f"Failed to flush metrics: {e}")
    
    def flush(self) -> None:
        """Flush all buffers to disk."""
        self._flush_events()
        self._flush_metrics()
    
    def close(self) -> None:
        """Close telemetry collector and flush buffers."""
        self.flush()
    
    def __enter__(self) -> TelemetryCollector:
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


class PhaseTimer:
    """Context manager for timing synthesis phases."""
    
    def __init__(
        self,
        telemetry: TelemetryCollector,
        phase: str,
        task_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize phase timer.
        
        Args:
            telemetry: Telemetry collector
            phase: Phase name
            task_id: Task identifier
            metadata: Optional phase metadata
        """
        self.telemetry = telemetry
        self.phase = phase
        self.task_id = task_id
        self.metadata = metadata or {}
        self.start_time: Optional[float] = None
        self.success = False
    
    def __enter__(self) -> PhaseTimer:
        """Start phase timing."""
        self.start_time = time.perf_counter()
        self.telemetry.record_phase_start(
            phase=self.phase,
            task_id=self.task_id,
            metadata=self.metadata,
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """End phase timing."""
        if self.start_time is None:
            return
        
        elapsed = time.perf_counter() - self.start_time
        self.success = exc_type is None
        
        self.telemetry.record_phase_end(
            phase=self.phase,
            task_id=self.task_id,
            success=self.success,
            elapsed_s=elapsed,
            metadata=self.metadata,
        )
    
    def mark_success(self) -> None:
        """Mark phase as successful."""
        self.success = True
