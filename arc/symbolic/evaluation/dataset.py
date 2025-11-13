"""Dataset management for evaluation."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set


class DatasetSplit(Enum):
    """Dataset split types."""
    
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    FULL = "full"


@dataclass
class TaskMetadata:
    """Metadata for a task."""
    
    task_id: str
    difficulty: Optional[str] = None
    grid_size: Optional[int] = None
    num_examples: Optional[int] = None
    has_symmetry: Optional[bool] = None
    has_color_mapping: Optional[bool] = None
    tags: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "difficulty": self.difficulty,
            "grid_size": self.grid_size,
            "num_examples": self.num_examples,
            "has_symmetry": self.has_symmetry,
            "has_color_mapping": self.has_color_mapping,
            "tags": list(self.tags),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskMetadata:
        """Create from dictionary."""
        tags = set(data.get("tags", []))
        return cls(
            task_id=data["task_id"],
            difficulty=data.get("difficulty"),
            grid_size=data.get("grid_size"),
            num_examples=data.get("num_examples"),
            has_symmetry=data.get("has_symmetry"),
            has_color_mapping=data.get("has_color_mapping"),
            tags=tags,
        )


class DatasetManager:
    """Manages dataset splits and task selection."""
    
    def __init__(
        self,
        dataset_root: Path,
        metadata_path: Optional[Path] = None,
        seed: int = 1337,
    ):
        """Initialize dataset manager.
        
        Args:
            dataset_root: Root directory of dataset
            metadata_path: Optional path to task metadata file
            seed: Random seed for reproducibility
        """
        self.dataset_root = Path(dataset_root)
        self.metadata_path = metadata_path
        self.seed = seed
        self.rng = random.Random(seed)
        
        self.task_metadata: Dict[str, TaskMetadata] = {}
        if metadata_path and Path(metadata_path).exists():
            self._load_metadata()
    
    def _load_metadata(self) -> None:
        """Load task metadata from file."""
        if not self.metadata_path:
            return
        
        with Path(self.metadata_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        for task_id, task_data in data.items():
            task_data["task_id"] = task_id
            self.task_metadata[task_id] = TaskMetadata.from_dict(task_data)
    
    def save_metadata(self, output_path: Path) -> None:
        """Save task metadata to file.
        
        Args:
            output_path: Path to save metadata
        """
        data = {
            task_id: metadata.to_dict()
            for task_id, metadata in self.task_metadata.items()
        }
        
        with Path(output_path).open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def get_task_ids(
        self,
        split: DatasetSplit = DatasetSplit.TRAIN,
    ) -> List[str]:
        """Get task IDs for a split.
        
        Args:
            split: Dataset split
            
        Returns:
            List of task IDs
        """
        split_dir = self.dataset_root / split.value
        if not split_dir.exists():
            return []
        
        task_ids = []
        for task_file in split_dir.glob("*.json"):
            task_ids.append(task_file.stem)
        
        return sorted(task_ids)
    
    def create_train_validation_split(
        self,
        train_ratio: float = 0.8,
        shuffle: bool = True,
    ) -> tuple[List[str], List[str]]:
        """Create train/validation split from training data.
        
        Args:
            train_ratio: Ratio of training data (0.0 to 1.0)
            shuffle: Whether to shuffle before splitting
            
        Returns:
            Tuple of (train_ids, validation_ids)
        """
        all_task_ids = self.get_task_ids(DatasetSplit.TRAIN)
        
        if shuffle:
            self.rng.shuffle(all_task_ids)
        
        split_index = int(len(all_task_ids) * train_ratio)
        train_ids = all_task_ids[:split_index]
        validation_ids = all_task_ids[split_index:]
        
        return train_ids, validation_ids
    
    def select_hard_examples(
        self,
        task_ids: Sequence[str],
        difficulty_threshold: str = "hard",
        max_count: Optional[int] = None,
    ) -> List[str]:
        """Select hard examples from task list.
        
        Args:
            task_ids: List of task IDs to filter
            difficulty_threshold: Minimum difficulty level
            max_count: Maximum number of tasks to return
            
        Returns:
            List of hard task IDs
        """
        hard_tasks = []
        
        for task_id in task_ids:
            metadata = self.task_metadata.get(task_id)
            if metadata and metadata.difficulty == difficulty_threshold:
                hard_tasks.append(task_id)
        
        # If no metadata, return all tasks
        if not hard_tasks and not self.task_metadata:
            hard_tasks = list(task_ids)
        
        if max_count is not None:
            hard_tasks = hard_tasks[:max_count]
        
        return hard_tasks
    
    def select_by_tags(
        self,
        task_ids: Sequence[str],
        required_tags: Optional[Set[str]] = None,
        excluded_tags: Optional[Set[str]] = None,
    ) -> List[str]:
        """Select tasks by tags.
        
        Args:
            task_ids: List of task IDs to filter
            required_tags: Tags that must be present
            excluded_tags: Tags that must not be present
            
        Returns:
            List of filtered task IDs
        """
        required_tags = required_tags or set()
        excluded_tags = excluded_tags or set()
        
        filtered = []
        
        for task_id in task_ids:
            metadata = self.task_metadata.get(task_id)
            if not metadata:
                # Include tasks without metadata if no filters
                if not required_tags and not excluded_tags:
                    filtered.append(task_id)
                continue
            
            # Check required tags
            if required_tags and not required_tags.issubset(metadata.tags):
                continue
            
            # Check excluded tags
            if excluded_tags and excluded_tags.intersection(metadata.tags):
                continue
            
            filtered.append(task_id)
        
        return filtered
    
    def select_by_grid_size(
        self,
        task_ids: Sequence[str],
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
    ) -> List[str]:
        """Select tasks by grid size.
        
        Args:
            task_ids: List of task IDs to filter
            min_size: Minimum grid size
            max_size: Maximum grid size
            
        Returns:
            List of filtered task IDs
        """
        filtered = []
        
        for task_id in task_ids:
            metadata = self.task_metadata.get(task_id)
            if not metadata or metadata.grid_size is None:
                # Include tasks without metadata
                filtered.append(task_id)
                continue
            
            if min_size is not None and metadata.grid_size < min_size:
                continue
            
            if max_size is not None and metadata.grid_size > max_size:
                continue
            
            filtered.append(task_id)
        
        return filtered
    
    def sample_tasks(
        self,
        task_ids: Sequence[str],
        count: int,
        stratify_by: Optional[str] = None,
    ) -> List[str]:
        """Sample tasks from list.
        
        Args:
            task_ids: List of task IDs to sample from
            count: Number of tasks to sample
            stratify_by: Optional field to stratify by (e.g., "difficulty")
            
        Returns:
            List of sampled task IDs
        """
        task_ids = list(task_ids)
        
        if count >= len(task_ids):
            return task_ids
        
        if stratify_by is None:
            return self.rng.sample(task_ids, count)
        
        # Stratified sampling
        strata: Dict[Any, List[str]] = {}
        for task_id in task_ids:
            metadata = self.task_metadata.get(task_id)
            if metadata:
                key = getattr(metadata, stratify_by, None)
            else:
                key = None
            
            strata.setdefault(key, []).append(task_id)
        
        # Sample proportionally from each stratum
        sampled = []
        for stratum_tasks in strata.values():
            stratum_count = max(1, int(count * len(stratum_tasks) / len(task_ids)))
            stratum_count = min(stratum_count, len(stratum_tasks))
            sampled.extend(self.rng.sample(stratum_tasks, stratum_count))
        
        # Adjust to exact count
        if len(sampled) > count:
            sampled = self.rng.sample(sampled, count)
        elif len(sampled) < count:
            remaining = [t for t in task_ids if t not in sampled]
            additional = min(count - len(sampled), len(remaining))
            sampled.extend(self.rng.sample(remaining, additional))
        
        return sampled
    
    def create_evaluation_subset(
        self,
        split: DatasetSplit = DatasetSplit.VALIDATION,
        max_count: Optional[int] = None,
        difficulty: Optional[str] = None,
        required_tags: Optional[Set[str]] = None,
        excluded_tags: Optional[Set[str]] = None,
        min_grid_size: Optional[int] = None,
        max_grid_size: Optional[int] = None,
        shuffle: bool = True,
    ) -> List[str]:
        """Create evaluation subset with filters.
        
        Args:
            split: Dataset split to use
            max_count: Maximum number of tasks
            difficulty: Filter by difficulty
            required_tags: Required tags
            excluded_tags: Excluded tags
            min_grid_size: Minimum grid size
            max_grid_size: Maximum grid size
            shuffle: Whether to shuffle results
            
        Returns:
            List of task IDs
        """
        task_ids = self.get_task_ids(split)
        
        # Apply filters
        if difficulty:
            task_ids = self.select_hard_examples(task_ids, difficulty)
        
        if required_tags or excluded_tags:
            task_ids = self.select_by_tags(task_ids, required_tags, excluded_tags)
        
        if min_grid_size is not None or max_grid_size is not None:
            task_ids = self.select_by_grid_size(task_ids, min_grid_size, max_grid_size)
        
        # Shuffle if requested
        if shuffle:
            self.rng.shuffle(task_ids)
        
        # Limit count
        if max_count is not None:
            task_ids = task_ids[:max_count]
        
        return task_ids
    
    def save_split(
        self,
        task_ids: Sequence[str],
        output_path: Path,
        split_name: str,
    ) -> None:
        """Save task split to file.
        
        Args:
            task_ids: List of task IDs
            output_path: Path to save split
            split_name: Name of split
        """
        data = {
            "split_name": split_name,
            "seed": self.seed,
            "task_count": len(task_ids),
            "task_ids": list(task_ids),
        }
        
        with Path(output_path).open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def load_split(self, split_path: Path) -> List[str]:
        """Load task split from file.
        
        Args:
            split_path: Path to split file
            
        Returns:
            List of task IDs
        """
        with Path(split_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        return data["task_ids"]
    
    def reset_seed(self, seed: int) -> None:
        """Reset random seed.
        
        Args:
            seed: New random seed
        """
        self.seed = seed
        self.rng = random.Random(seed)
