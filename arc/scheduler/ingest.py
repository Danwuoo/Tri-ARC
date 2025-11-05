from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional

from arc.scheduler.cache import FeatureCache, configure_feature_cache
from arc.scheduler.features import (
    GridStats,
    ObjectStats,
    PaletteStats,
    SymmetryStats,
    TaskFeatures,
    compute_task_features,
)

LOGGER = logging.getLogger("arc.scheduler.ingest")


@dataclass(frozen=True)
class IngestedTask:
    task_id: str
    payload: Mapping[str, Any]
    features: TaskFeatures
    metadata: Mapping[str, Any]


def _ensure_logger(config: Mapping[str, Any], *, logger: Optional[logging.Logger] = None) -> logging.Logger:
    ingest_logger = logger or LOGGER
    scheduler_cfg = config.get("scheduler", {})
    logging_cfg = {}
    if isinstance(scheduler_cfg, Mapping):
        logging_cfg = scheduler_cfg.get("logging", {}) or {}
    log_path_value = logging_cfg.get("ingest_log", "logs/scheduler/ingest.log")
    log_path = Path(log_path_value)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    existing_paths = {getattr(handler, "baseFilename", None) for handler in ingest_logger.handlers}
    if str(log_path) not in existing_paths:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(formatter)
        ingest_logger.addHandler(handler)
        ingest_logger.setLevel(logging.INFO)
    return ingest_logger


class SchedulerIngestor:
    """Derives scheduler features for tasks and persists results to cache."""

    def __init__(
        self,
        config: MutableMapping[str, Any],
        *,
        feature_cache: FeatureCache | None = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.logger = _ensure_logger(config, logger=logger)
        self.feature_cache = feature_cache if feature_cache is not None else configure_feature_cache(config)

    def ingest(
        self,
        tasks: Iterable[Mapping[str, Any]],
        *,
        force_refresh: bool = False,
    ) -> List[IngestedTask]:
        prepared: List[IngestedTask] = []
        for task in sorted(tasks, key=lambda item: str(item.get("task_id", ""))):
            ingested = self._ingest_single(task, force_refresh=force_refresh)
            prepared.append(ingested)

        # Persist cache once per batch to amortise IO.
        self.feature_cache.persist()
        return prepared

    def _ingest_single(self, task: Mapping[str, Any], *, force_refresh: bool) -> IngestedTask:
        self._validate_task(task)
        task_id = str(task["task_id"])
        metadata = task.get("metadata", {})
        history = {}
        if isinstance(metadata, Mapping):
            history = metadata.get("scheduler_history", {}) or {}
        train_examples = list(task.get("train_examples") or [])

        cached = None if force_refresh else self.feature_cache.get(task_id)
        if cached is not None:
            features = _deserialise_features(cached)
            self.logger.debug("Reused cached features for task_id=%s", task_id)
        else:
            features = compute_task_features(task_id, train_examples, history=history)
            self.feature_cache.set(task_id, features.to_dict(), metadata={"task_id": task_id})
            self.logger.info("Computed features for task_id=%s", task_id)

        return IngestedTask(
            task_id=task_id,
            payload=task,
            features=features,
            metadata=metadata if isinstance(metadata, Mapping) else {},
        )

    def _validate_task(self, task: Mapping[str, Any]) -> None:
        if "task_id" not in task:
            self.logger.error("Encountered task without task_id; aborting ingestion.")
            raise ValueError("Scheduler requires tasks to include a 'task_id' entry.")

        if "train_examples" not in task:
            self.logger.error("Task %s missing train_examples metadata.", task.get("task_id"))
            raise ValueError("Scheduler requires 'train_examples' to be present.")

        train_examples = task.get("train_examples")
        if not isinstance(train_examples, list) or not train_examples:
            self.logger.error("Task %s has empty or invalid train_examples.", task.get("task_id"))
            raise ValueError("Scheduler expects non-empty list of train_examples.")

        for index, example in enumerate(train_examples):
            if not isinstance(example, Mapping):
                self.logger.error("Task %s train_examples[%d] is not a mapping.", task.get("task_id"), index)
                raise ValueError("Each train example must be a mapping with 'input' and 'output'.")
            for key in ("input", "output"):
                if key not in example:
                    self.logger.error("Task %s train_examples[%d] missing key '%s'.", task.get("task_id"), index, key)
                    raise ValueError(f"Train example {index} missing '{key}' grid.")


def _deserialise_features(payload: Mapping[str, Any]) -> TaskFeatures:
    grid = payload.get("grid", {})
    palette = payload.get("palette", {})
    symmetry = payload.get("symmetry", {})
    objects = payload.get("objects", {})
    history = payload.get("history", {})

    return TaskFeatures(
        task_id=str(payload.get("task_id", "")),
        grid=GridStats(**grid),
        palette=PaletteStats(**palette),
        symmetry=SymmetryStats(**symmetry),
        objects=ObjectStats(**objects),
        history=dict(history) if isinstance(history, Mapping) else {},
    )
