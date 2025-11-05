from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

LOGGER = logging.getLogger("arc.scheduler.resources")


@dataclass
class ResourceAllocationRecord:
    task_id: str
    module: str
    device: str
    expected_runtime_s: float
    start_delay_s: float
    timestamp: float


class ResourceTracker:
    """Tracks GPU/CPU allocations to surface utilisation and contention."""

    def __init__(
        self,
        device_map: Mapping[str, Any],
        *,
        gpu_capacity: float = 1.0,
        cpu_worker_capacity: float = 16.0,
    ) -> None:
        self.device_map = {str(module): str(device) for module, device in device_map.items()}
        self._allocations: Dict[str, List[ResourceAllocationRecord]] = defaultdict(list)
        self._max_records = 200
        self.logger = LOGGER
        self._device_capacity: Dict[str, float] = {}
        for device in self.device_map.values():
            if device not in self._device_capacity:
                if str(device).lower().startswith("cuda"):
                    self._device_capacity[device] = float(gpu_capacity)
                else:
                    self._device_capacity[device] = float(cpu_worker_capacity)

    def register(self, task_id: str, module: str, record: ResourceAllocationRecord) -> None:
        device_records = self._allocations[record.device]
        device_records.append(record)
        if len(device_records) > self._max_records:
            del device_records[0 : len(device_records) - self._max_records]
        self.logger.debug(
            "Registered allocation task_id=%s module=%s device=%s runtime=%.2fs",
            task_id,
            module,
            record.device,
            record.expected_runtime_s,
        )

    def create_record(
        self,
        task_id: str,
        module: str,
        *,
        expected_runtime_s: float,
        start_delay_s: float,
    ) -> ResourceAllocationRecord:
        device = self.device_map.get(module)
        if device is None:
            device = "cpu"
            self.logger.warning("Module %s missing device mapping; defaulting to CPU pool.", module)
        timestamp = time.time()
        return ResourceAllocationRecord(
            task_id=task_id,
            module=module,
            device=device,
            expected_runtime_s=expected_runtime_s,
            start_delay_s=start_delay_s,
            timestamp=timestamp,
        )

    def device_summary(self) -> Dict[str, Dict[str, float]]:
        summary: Dict[str, Dict[str, float]] = {}
        for device, records in self._allocations.items():
            total_runtime = sum(item.expected_runtime_s for item in records)
            capacity = self._device_capacity.get(device, 1.0)
            summary[device] = {
                "allocations": float(len(records)),
                "total_expected_runtime_s": float(total_runtime),
                "avg_expected_runtime_s": float(total_runtime / len(records)) if records else 0.0,
                "capacity": float(capacity),
                "utilisation_ratio": float(total_runtime / capacity) if capacity else float(total_runtime),
            }
        return summary

    def contention_score(self, device: str) -> float:
        records = self._allocations.get(device, [])
        total_runtime = sum(item.expected_runtime_s for item in records)
        return float(total_runtime)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "devices": self.device_summary(),
            "timestamp": time.time(),
        }
