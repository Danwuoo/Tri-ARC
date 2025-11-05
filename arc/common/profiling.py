from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

__all__ = [
    "PerformanceSnapshot",
    "capture_performance_snapshot",
    "summarise_snapshot_delta",
]


def _round(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _import_optional(name: str) -> Optional[Any]:
    try:
        module = importlib.import_module(name)
    except Exception:
        return None
    return module


_PSUTIL = _import_optional("psutil")
_TORCH = _import_optional("torch")


@dataclass
class PerformanceSnapshot:
    timestamp: float
    cpu_rss_mb: Optional[float]
    cpu_vms_mb: Optional[float]
    io_read_mb: Optional[float]
    io_write_mb: Optional[float]
    gpu_allocated_mb: Dict[str, float] = field(default_factory=dict)
    gpu_reserved_mb: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "timestamp": self.timestamp,
            "cpu_rss_mb": self.cpu_rss_mb,
            "cpu_vms_mb": self.cpu_vms_mb,
            "io_read_mb": self.io_read_mb,
            "io_write_mb": self.io_write_mb,
            "gpu_allocated_mb": dict(self.gpu_allocated_mb),
            "gpu_reserved_mb": dict(self.gpu_reserved_mb),
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def _bytes_to_mb(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return float(value) / (1024.0 * 1024.0)


def capture_performance_snapshot() -> PerformanceSnapshot:
    timestamp = time.time()
    cpu_rss_mb: Optional[float] = None
    cpu_vms_mb: Optional[float] = None
    io_read_mb: Optional[float] = None
    io_write_mb: Optional[float] = None
    metadata: Dict[str, Any] = {}

    if _PSUTIL is not None:
        process = _PSUTIL.Process()
        with process.oneshot():
            try:
                mem_info = process.memory_info()
                cpu_rss_mb = _bytes_to_mb(mem_info.rss)
                cpu_vms_mb = _bytes_to_mb(getattr(mem_info, "vms", None))
            except Exception:
                cpu_rss_mb = None
                cpu_vms_mb = None
            try:
                io_counters = process.io_counters()
                io_read_mb = _bytes_to_mb(getattr(io_counters, "read_bytes", None))
                io_write_mb = _bytes_to_mb(getattr(io_counters, "write_bytes", None))
            except Exception:
                io_read_mb = None
                io_write_mb = None
            try:
                metadata["pid"] = process.pid
                metadata["num_threads"] = process.num_threads()
            except Exception:
                pass

    gpu_allocated: Dict[str, float] = {}
    gpu_reserved: Dict[str, float] = {}
    torch = _TORCH
    if torch is not None:
        try:
            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
                for index in range(device_count):
                    device = torch.cuda.device(index)
                    name = f"cuda:{index}"
                    try:
                        allocated = torch.cuda.memory_allocated(device)
                        reserved = torch.cuda.memory_reserved(device)
                    except Exception:
                        allocated = None
                        reserved = None
                    gpu_allocated[name] = _bytes_to_mb(allocated) or 0.0
                    gpu_reserved[name] = _bytes_to_mb(reserved) or 0.0
        except Exception:
            # Ignore GPU metrics if CUDA is misconfigured.
            gpu_allocated = {}
            gpu_reserved = {}

    return PerformanceSnapshot(
        timestamp=timestamp,
        cpu_rss_mb=_round(cpu_rss_mb),
        cpu_vms_mb=_round(cpu_vms_mb),
        io_read_mb=_round(io_read_mb),
        io_write_mb=_round(io_write_mb),
        gpu_allocated_mb={device: _round(value) or 0.0 for device, value in gpu_allocated.items()},
        gpu_reserved_mb={device: _round(value) or 0.0 for device, value in gpu_reserved.items()},
        metadata=metadata,
    )


def summarise_snapshot_delta(
    before: PerformanceSnapshot,
    after: PerformanceSnapshot,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "duration_s": _round(after.timestamp - before.timestamp),
    }

    if before.cpu_rss_mb is not None or after.cpu_rss_mb is not None:
        cpu_payload: Dict[str, Any] = {
            "rss_mb": after.cpu_rss_mb,
            "rss_delta_mb": (
                _round(after.cpu_rss_mb - before.cpu_rss_mb)
                if before.cpu_rss_mb is not None and after.cpu_rss_mb is not None
                else None
            ),
            "vms_mb": after.cpu_vms_mb,
            "vms_delta_mb": (
                _round(after.cpu_vms_mb - before.cpu_vms_mb)
                if before.cpu_vms_mb is not None and after.cpu_vms_mb is not None
                else None
            ),
        }
        result["cpu"] = cpu_payload

    if before.io_read_mb is not None or after.io_read_mb is not None:
        io_payload: Dict[str, Any] = {
            "read_mb": after.io_read_mb,
            "write_mb": after.io_write_mb,
            "read_delta_mb": (
                _round(after.io_read_mb - before.io_read_mb)
                if before.io_read_mb is not None and after.io_read_mb is not None
                else None
            ),
            "write_delta_mb": (
                _round(after.io_write_mb - before.io_write_mb)
                if before.io_write_mb is not None and after.io_write_mb is not None
                else None
            ),
        }
        result["io"] = io_payload

    if after.gpu_allocated_mb or after.gpu_reserved_mb:
        allocated_delta: Dict[str, Optional[float]] = {}
        for device, value in after.gpu_allocated_mb.items():
            delta = None
            if device in before.gpu_allocated_mb:
                delta = _round(value - before.gpu_allocated_mb.get(device, 0.0))
            allocated_delta[device] = delta
        reserved_delta: Dict[str, Optional[float]] = {}
        for device, value in after.gpu_reserved_mb.items():
            delta = None
            if device in before.gpu_reserved_mb:
                delta = _round(value - before.gpu_reserved_mb.get(device, 0.0))
            reserved_delta[device] = delta
        result["gpu"] = {
            "allocated_mb": after.gpu_allocated_mb,
            "allocated_delta_mb": allocated_delta,
            "reserved_mb": after.gpu_reserved_mb,
            "reserved_delta_mb": reserved_delta,
        }

    if after.metadata:
        result.setdefault("metadata", {}).update(after.metadata)

    return result
