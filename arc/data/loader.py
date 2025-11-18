from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

LOGGER = logging.getLogger("arc.data.loader")

SPLIT_ALIASES = {
    "train": ("train", "training"),
    "evaluation": ("evaluation", "test", "public_evaluation"),
    "smoke": ("smoke",),
}

_SPLIT_DIRECTORY_CANDIDATES: Tuple[str, ...] = tuple(
    sorted(
        {
            token
            for canonical, aliases in SPLIT_ALIASES.items()
            for token in (canonical, *aliases)
        }
    )
)


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
        payload = _build_task_payload(
            raw,
            task_id=task_id,
            split=split,
            path=path,
            checksum=checksum,
            data_root=self.data_root,
        )
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


def _build_task_payload(
    raw: Mapping[str, Any],
    *,
    task_id: str,
    split: str,
    path: Path,
    checksum: Optional[str],
    data_root: Path,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = dict(raw)
    train_source = payload.get("train_examples") or payload.get("train") or payload.get("examples") or []
    train_examples = _normalise_examples(train_source, require_output=True)
    if not train_examples:
        raise ValueError(f"Task {task_id} missing train examples.")
    eval_source = (
        payload.get("test_examples")
        or payload.get("eval_examples")
        or payload.get("test")
        or payload.get("evaluation")
        or payload.get("eval")
        or []
    )
    evaluation_examples = _normalise_examples(eval_source, require_output=False)
    metadata = _extract_metadata(
        raw_metadata=payload.get("metadata"),
        split=split,
        path=path,
        checksum=checksum,
        train_examples=train_examples,
        eval_examples=evaluation_examples,
        data_root=data_root,
    )
    for legacy_key in ("train", "test", "evaluation", "examples", "train_examples", "test_examples", "eval_examples"):
        payload.pop(legacy_key, None)
    payload["task_id"] = task_id
    payload["train_examples"] = train_examples
    payload["test_examples"] = evaluation_examples
    payload["eval_examples"] = evaluation_examples
    payload["metadata"] = metadata
    return payload


def _records_to_payloads(records: Iterable[TaskRecord]) -> List[Dict[str, Any]]:
    return [record.to_payload() for record in records]


def _guess_split_from_name(name: str) -> Optional[str]:
    token = name.lower()
    for canonical, aliases in SPLIT_ALIASES.items():
        if canonical in token:
            return canonical
        for alias in aliases:
            if alias in token:
                return canonical
    return None


def _has_split_subdirectories(directory: Path) -> bool:
    return any((directory / candidate).is_dir() for candidate in _SPLIT_DIRECTORY_CANDIDATES)


def _load_directory_files(
    directory: Path,
    *,
    canonical_split: str,
    limit: Optional[int],
    enable_checksums: bool,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    loader = DatasetLoader(directory, enable_checksums=enable_checksums, logger=logger)
    sources = sorted(directory.glob("*.json"))
    if not sources:
        sources = sorted(directory.rglob("*.json"))
    if not sources:
        raise FileNotFoundError(f"No task files found under {directory}.")
    dataset: List[Dict[str, Any]] = []
    for path in sources:
        if limit is not None and len(dataset) >= limit:
            break
        try:
            record = loader._load_task(path, canonical_split)
        except Exception as exc:
            logger.error("Failed to load task %s: %s", path, exc)
            continue
        dataset.append(record.to_payload())
    return dataset


def _load_dataset_from_directory(
    directory: Path,
    *,
    split: Optional[str],
    limit: Optional[int],
    enable_checksums: bool,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    if _has_split_subdirectories(directory):
        canonical = _normalise_split_name(split or "train")
        loader = DatasetLoader(directory, enable_checksums=enable_checksums, logger=logger)
        return _records_to_payloads(loader.iter_split(canonical, limit=limit))

    parent = directory.parent
    split_guess = split or _guess_split_from_name(directory.name)
    if parent and parent != directory and parent.exists() and split_guess:
        loader = DatasetLoader(parent, enable_checksums=enable_checksums, logger=logger)
        canonical = _normalise_split_name(split_guess)
        try:
            return _records_to_payloads(loader.iter_split(canonical, limit=limit))
        except FileNotFoundError:
            logger.debug("Parent %s did not contain split '%s'. Falling back to direct loading.", parent, canonical)

    canonical = _normalise_split_name(split or split_guess or "train")
    return _load_directory_files(
        directory,
        canonical_split=canonical,
        limit=limit,
        enable_checksums=enable_checksums,
        logger=logger,
    )


def _load_dataset_from_file(
    file_path: Path,
    *,
    split: Optional[str],
    limit: Optional[int],
    enable_checksums: bool,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    entries: List[Any] = []
    suffix = file_path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        with file_path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                candidate = line.strip()
                if not candidate:
                    continue
                try:
                    entries.append(json.loads(candidate))
                except json.JSONDecodeError as exc:
                    logger.error("Skipping invalid JSON line %d in %s: %s", line_no, file_path, exc)
    else:
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            entries = payload
        elif isinstance(payload, Mapping) and isinstance(payload.get("tasks"), list):
            entries = payload["tasks"]
        else:
            entries = [payload]

    canonical = _normalise_split_name(split or _guess_split_from_name(file_path.stem) or "train")
    dataset_root = file_path.parent
    dataset: List[Dict[str, Any]] = []
    safe_base = file_path.stem or "task"

    for index, entry in enumerate(entries):
        if limit is not None and len(dataset) >= limit:
            break
        if not isinstance(entry, Mapping):
            logger.warning("Skipping non-mapping entry at index %d from %s.", index, file_path)
            continue
        task_id = str(entry.get("task_id") or entry.get("id") or f"{safe_base}_{index:05d}")
        safe_id = task_id.replace("/", "__")
        synthetic_path = file_path.with_name(f"{safe_base}__{safe_id}.json")
        try:
            payload = _build_task_payload(
                entry,
                task_id=task_id,
                split=canonical,
                path=synthetic_path,
                checksum=None,
                data_root=dataset_root,
            )
        except ValueError as exc:
            logger.error("Skipping invalid task %s from %s: %s", task_id, file_path, exc)
            continue
        dataset.append(payload)
    return dataset


def load_dataset(
    resource: Union[str, Path],
    *,
    split: Optional[str] = None,
    limit: Optional[int] = None,
    enable_checksums: bool = False,
    logger: Optional[logging.Logger] = None,
) -> List[Dict[str, Any]]:
    """Load ARC task data from files or directories into solver-ready payloads."""
    dataset_path = Path(resource)
    active_logger = logger or LOGGER

    if dataset_path.is_dir():
        return _load_dataset_from_directory(
            dataset_path,
            split=split,
            limit=limit,
            enable_checksums=enable_checksums,
            logger=active_logger,
        )

    if dataset_path.is_file():
        return _load_dataset_from_file(
            dataset_path,
            split=split,
            limit=limit,
            enable_checksums=enable_checksums,
            logger=active_logger,
        )

    parent = dataset_path.parent
    inferred_split = split or _guess_split_from_name(dataset_path.stem)
    if parent.exists() and inferred_split and parent.is_dir() and _has_split_subdirectories(parent):
        active_logger.info(
            "Dataset path %s not found; using parent %s split '%s' instead.",
            dataset_path,
            parent,
            inferred_split,
        )
        return _load_dataset_from_directory(
            parent,
            split=inferred_split,
            limit=limit,
            enable_checksums=enable_checksums,
            logger=active_logger,
        )

    raise FileNotFoundError(f"Dataset resource '{dataset_path}' does not exist.")
