from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional


MetricSink = Callable[[Dict[str, Any]], None]


@dataclass
class ModuleContext:
    """Carries shared runtime handles made available to modules."""

    module_name: str
    config: Mapping[str, Any]
    shared_cache: MutableMapping[str, Any]
    run_id: str
    logger: Any  # Accepts logging.Logger without importing logging here.
    metrics_sink: Optional[MetricSink] = None
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleTaskContext:
    """Task-scoped view composed during `prepare_task`."""

    task_id: str
    task_payload: Mapping[str, Any]
    module_context: ModuleContext
    cache_namespace: MutableMapping[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
