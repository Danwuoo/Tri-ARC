from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence

LOGGER = logging.getLogger("arc.data.loader")

SPLIT_ALIASES = {
    "train": ("train", "training"),
    "evaluation": ("evaluation", "test", "public_evaluation"),
    "smoke": ("smoke",),
}


def _normalise_split_name(split: str) -> str:
    token = split.lower()
    if token in SPLIT_ALIASES:
        return token
    for canonical, aliases in SPLIT_ALIASES.items():
        if token in aliases:
            return canonical
    return token


def _candidate_directories(split: str) -> List[str]:
    canonical = _normalise_split_name(split)
    if canonical in SPLIT_ALIASES:
        return list(SPLIT_ALIASES[canonical])
    return [split]


def _grid_shape(grid: Any) -> Optional[List[int]]:
    if not isinstance(grid, list) or not grid:
        return None
    if not isinstance(grid[0], list):
        return [len(grid), 0]
    return [len(grid), len(grid[0])]


def load_sample_task(data_root: Path) -> Optional[Dict[str, Any]]:
    """Return the contents of the first ARC task JSON file under training data."""
    root = Path(data_root)
    for split in _candidate_directories("train"):
        split_root = root / split
        if not split_root.exists():
            continue
        candidates = sorted(split_root.glob("*.json"))
        if not candidates:
            candidates = sorted(split_root.rglob("*.json"))
        for candidate in candidates:
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
            except json.JSONDecodeError:
                LOGGER.warning("Sample task %s is not valid JSON; skipping.", candidate)
                continue
    return None


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    split: str
    path: Path
    payload: Mapping[str, Any]
    checksum: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        data = dict(self.payload)
        metadata = dict(data.get("metadata", {}))
        metadata.setdefault("task_id", self.task_id)
        metadata.setdefault("split", self.split)
        metadata.setdefault("source_path", str(self.path))
        if self.checksum:
            metadata.setdefault("checksum", self.checksum)
        data["metadata"] = metadata
        return data


class DatasetLoader:
    """Iterates ARC task files and prepares scheduler-compatible payloads."""

    def __init__(
        self,
        data_root: Path,
        *,
        enable_checksums: bool = False,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.enable_checksums = enable_checksums
        self.logger = logger or LOGGER
        self._indices: Dict[str, List[Path]] = {}
        self._lookups: Dict[str, Dict[str, Path]] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def iter_split(
        self,
        split: str,
        *,
        limit: Optional[int] = None,
        task_ids: Optional[Sequence[str]] = None,
        exclude_task_ids: Optional[Sequence[str]] = None,
    ) -> Iterator[TaskRecord]:
        canonical = _normalise_split_name(split)
        paths = self._resolve_selection(canonical, task_ids=task_ids, exclude_task_ids=exclude_task_ids)
        emitted = 0
        for path in paths:
            if limit is not None and emitted >= limit:
                break
            try:
                record = self._load_task(path, canonical)
            except Exception as exc:
                self.logger.error("Failed to load task %s: %s", path, exc)
                continue
            yield record
            emitted += 1

    def load_task(self, split: str, task_id: str) -> TaskRecord:
        canonical = _normalise_split_name(split)
        lookup = self._ensure_lookup(canonical)
        if task_id not in lookup:
            raise KeyError(f"Task '{task_id}' not found in split '{split}'.")
        return self._load_task(lookup[task_id], canonical)

    def list_task_ids(self, split: str) -> List[str]:
        canonical = _normalise_split_name(split)
        lookup = self._ensure_lookup(canonical)
        return list(lookup.keys())

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _resolve_selection(
        self,
        split: str,
        *,
        task_ids: Optional[Sequence[str]],
        exclude_task_ids: Optional[Sequence[str]],
    ) -> List[Path]:
        index = self._ensure_index(split)
        lookup = self._ensure_lookup(split)

        if task_ids:
            selection: List[Path] = []
            missing: List[str] = []
            seen: set[str] = set()
            for task_id in task_ids:
                if task_id in seen:
                    continue
                seen.add(task_id)
                path = lookup.get(task_id)
                if path is None:
                    missing.append(task_id)
                    continue
                selection.append(path)
            if missing:
                self.logger.warning(
                    "Skipping %d requested task(s) absent from split '%s': %s",
                    len(missing),
                    split,
                    ", ".join(missing[:5]) + ("..." if len(missing) > 5 else ""),
                )
            return selection

        exclusion = set(exclude_task_ids or [])
        return [path for path in index if self._derive_task_id(split, path) not in exclusion]

    def _ensure_index(self, split: str) -> List[Path]:
        if split in self._indices:
            return self._indices[split]

        paths: List[Path] = []
        for candidate in _candidate_directories(split):
            split_root = self.data_root / candidate
            if not split_root.exists():
                continue
            direct = sorted(split_root.glob("*.json"))
            nested = sorted(split_root.rglob("*.json")) if not direct else []
            sources = direct or nested
            if not sources:
                continue
            paths.extend(sources)
        if not paths:
            raise FileNotFoundError(f"No task files discovered for split '{split}' under {self.data_root}.")
        ordered = sorted(set(paths))
        self._indices[split] = ordered
        return ordered

    def _ensure_lookup(self, split: str) -> Dict[str, Path]:
        if split in self._lookups:
            return self._lookups[split]
        index = self._ensure_index(split)
        mapping: Dict[str, Path] = {}
        duplicates: Dict[str, List[Path]] = {}
        for path in index:
            task_id = self._derive_task_id(split, path)
            if task_id in mapping:
                duplicates.setdefault(task_id, [mapping[task_id]]).append(path)
                continue
            mapping[task_id] = path
        if duplicates:
            sample = next(iter(duplicates.items()))
            self.logger.warning(
                "Detected duplicate task IDs for split '%s'; using first occurrences. Example: %s -> %s",
                split,
                sample[0],
                ", ".join(str(item) for item in sample[1]),
            )
        self._lookups[split] = mapping
        return mapping

    def _derive_task_id(self, split: str, path: Path) -> str:
        try:
            split_root = self._root_for_path(split, path)
            relative = path.relative_to(split_root)
        except ValueError:
            relative = path.name
        else:
            relative = relative.as_posix()
        if isinstance(relative, Path):
            relative = relative.as_posix()
        identifier = str(relative)
        if identifier.endswith(".json"):
            identifier = identifier[:-5]
        identifier = identifier.replace("/", "__")
        return identifier

    def _root_for_path(self, split: str, path: Path) -> Path:
        for candidate in _candidate_directories(split):
            split_root = self.data_root / candidate
            try:
                path.relative_to(split_root)
                return split_root
            except ValueError:
                continue
        return path.parent

    def _load_task(self, path: Path, split: str) -> TaskRecord:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        task_id = self._derive_task_id(split, path)
        checksum = self._compute_checksum(path) if self.enable_checksums else None

        train_examples = _normalise_examples(raw.get("train", []), require_output=True)
        if not train_examples:
            raise ValueError(f"Task {task_id} missing train examples.")
        evaluation_examples = _normalise_examples(raw.get("test") or raw.get("evaluation") or [], require_output=False)
        metadata = _extract_metadata(
            raw_metadata=raw.get("metadata"),
            split=split,
            path=path,
            checksum=checksum,
            train_examples=train_examples,
            eval_examples=evaluation_examples,
            data_root=self.data_root,
        )
        payload: Dict[str, Any] = {
            "task_id": task_id,
            "train_examples": train_examples,
            "test_examples": evaluation_examples,
            "eval_examples": evaluation_examples,
            "metadata": metadata,
        }
        return TaskRecord(task_id=task_id, split=split, path=path, payload=payload, checksum=checksum)

    def _compute_checksum(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()


def _normalise_examples(
    examples: Iterable[Mapping[str, Any]],
    *,
    require_output: bool,
) -> List[Dict[str, Any]]:
    normalised: List[Dict[str, Any]] = []
    for index, example in enumerate(examples):
        if not isinstance(example, Mapping):
            continue
        grid_input = example.get("input")
        grid_output = example.get("output")
        payload: Dict[str, Any] = {"input": grid_input, "index": index}
        if grid_output is not None:
            payload["output"] = grid_output
        if require_output and "output" not in payload:
            continue
        normalised.append(payload)
    return normalised


def _extract_metadata(
    *,
    raw_metadata: Any,
    split: str,
    path: Path,
    checksum: Optional[str],
    train_examples: Sequence[Mapping[str, Any]],
    eval_examples: Sequence[Mapping[str, Any]],
    data_root: Path,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    if isinstance(raw_metadata, Mapping):
        metadata.update({str(key): value for key, value in raw_metadata.items()})
    metadata.setdefault("source_split", split)
    metadata.setdefault("source_path", str(path))
    try:
        metadata.setdefault("relative_path", str(path.relative_to(data_root)))
    except ValueError:
        metadata.setdefault("relative_path", path.name)
    metadata.setdefault("train_example_shapes", _collect_shapes(train_examples))
    metadata.setdefault("eval_example_shapes", _collect_shapes(eval_examples))
    if checksum:
        metadata.setdefault("checksum", checksum)
    return metadata


def _collect_shapes(examples: Sequence[Mapping[str, Any]]) -> List[List[int]]:
    shapes: List[List[int]] = []
    for example in examples:
        grid = example.get("input")
        shape = _grid_shape(grid)
        if shape:
            shapes.append(shape)
    return shapes
