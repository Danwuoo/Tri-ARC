"""Artifact management for programs, evidence, and invariants."""

from __future__ import annotations

import gzip
import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ArtifactManager:
    """Manages saving and loading of synthesis artifacts."""
    
    def __init__(
        self,
        artifact_dir: Optional[str] = None,
        enable_compression: bool = True,
        compression_threshold_bytes: int = 1024,
    ):
        """Initialize artifact manager.
        
        Args:
            artifact_dir: Directory for artifacts
            enable_compression: Whether to compress large artifacts
            compression_threshold_bytes: Size threshold for compression
        """
        self.artifact_dir = Path(artifact_dir) if artifact_dir else Path("cache/symbolic/artifacts")
        self.enable_compression = enable_compression
        self.compression_threshold_bytes = compression_threshold_bytes
        
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories for different artifact types
        self.programs_dir = self.artifact_dir / "programs"
        self.evidence_dir = self.artifact_dir / "evidence"
        self.invariants_dir = self.artifact_dir / "invariants"
        self.checkpoints_dir = self.artifact_dir / "checkpoints"
        
        for subdir in [self.programs_dir, self.evidence_dir, self.invariants_dir, self.checkpoints_dir]:
            subdir.mkdir(parents=True, exist_ok=True)
    
    def save_program(
        self,
        task_id: str,
        program: Any,
        metadata: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> Path:
        """Save a program artifact.
        
        Args:
            task_id: Task identifier
            program: Program to save
            metadata: Optional metadata
            version: Optional version tag
            
        Returns:
            Path to saved artifact
        """
        artifact = {
            "task_id": task_id,
            "program": self._serialize_program(program),
            "metadata": metadata or {},
            "version": version,
        }
        
        filename = f"{task_id}"
        if version:
            filename += f"_v{version}"
        filename += ".json"
        
        return self._save_json(self.programs_dir / filename, artifact)
    
    def load_program(
        self,
        task_id: str,
        version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load a program artifact.
        
        Args:
            task_id: Task identifier
            version: Optional version tag
            
        Returns:
            Program artifact or None if not found
        """
        filename = f"{task_id}"
        if version:
            filename += f"_v{version}"
        filename += ".json"
        
        return self._load_json(self.programs_dir / filename)
    
    def save_evidence(
        self,
        task_id: str,
        evidence: Dict[str, Any],
        version: Optional[str] = None,
    ) -> Path:
        """Save verification evidence.
        
        Args:
            task_id: Task identifier
            evidence: Evidence data (counterexamples, proofs, etc.)
            version: Optional version tag
            
        Returns:
            Path to saved artifact
        """
        artifact = {
            "task_id": task_id,
            "evidence": evidence,
            "version": version,
        }
        
        filename = f"{task_id}_evidence"
        if version:
            filename += f"_v{version}"
        filename += ".json"
        
        return self._save_json(self.evidence_dir / filename, artifact)
    
    def load_evidence(
        self,
        task_id: str,
        version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load verification evidence.
        
        Args:
            task_id: Task identifier
            version: Optional version tag
            
        Returns:
            Evidence artifact or None if not found
        """
        filename = f"{task_id}_evidence"
        if version:
            filename += f"_v{version}"
        filename += ".json"
        
        return self._load_json(self.evidence_dir / filename)
    
    def save_invariants(
        self,
        task_id: str,
        invariants: List[Dict[str, Any]],
        source: str = "symbolic",
    ) -> Path:
        """Save task invariants.
        
        Args:
            task_id: Task identifier
            invariants: List of invariants
            source: Source module (e.g., "symbolic", "ttt", "llm")
            
        Returns:
            Path to saved artifact
        """
        artifact = {
            "task_id": task_id,
            "invariants": invariants,
            "source": source,
        }
        
        filename = f"{task_id}_invariants_{source}.json"
        return self._save_json(self.invariants_dir / filename, artifact)
    
    def load_invariants(
        self,
        task_id: str,
        source: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load task invariants.
        
        Args:
            task_id: Task identifier
            source: Optional source filter
            
        Returns:
            Invariants artifact or None if not found
        """
        if source:
            filename = f"{task_id}_invariants_{source}.json"
            return self._load_json(self.invariants_dir / filename)
        else:
            # Load all invariants for task
            pattern = f"{task_id}_invariants_*.json"
            invariants = []
            for path in self.invariants_dir.glob(pattern):
                artifact = self._load_json(path)
                if artifact:
                    invariants.extend(artifact.get("invariants", []))
            return {"task_id": task_id, "invariants": invariants} if invariants else None
    
    def save_checkpoint(
        self,
        checkpoint_id: str,
        state: Dict[str, Any],
    ) -> Path:
        """Save a checkpoint of synthesis state.
        
        Args:
            checkpoint_id: Checkpoint identifier
            state: State dictionary
            
        Returns:
            Path to saved checkpoint
        """
        filename = f"{checkpoint_id}.pkl"
        return self._save_pickle(self.checkpoints_dir / filename, state)
    
    def load_checkpoint(
        self,
        checkpoint_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load a checkpoint.
        
        Args:
            checkpoint_id: Checkpoint identifier
            
        Returns:
            State dictionary or None if not found
        """
        filename = f"{checkpoint_id}.pkl"
        return self._load_pickle(self.checkpoints_dir / filename)
    
    def list_programs(self, task_id: Optional[str] = None) -> List[str]:
        """List available program artifacts.
        
        Args:
            task_id: Optional task filter
            
        Returns:
            List of program artifact names
        """
        pattern = f"{task_id}*.json" if task_id else "*.json"
        return [p.stem for p in self.programs_dir.glob(pattern)]
    
    def list_checkpoints(self) -> List[str]:
        """List available checkpoints.
        
        Returns:
            List of checkpoint IDs
        """
        return [p.stem for p in self.checkpoints_dir.glob("*.pkl")]
    
    def delete_artifact(self, artifact_path: Path) -> bool:
        """Delete an artifact.
        
        Args:
            artifact_path: Path to artifact
            
        Returns:
            True if deleted successfully
        """
        try:
            if artifact_path.exists():
                artifact_path.unlink()
                return True
            return False
        except Exception:
            return False
    
    def _save_json(self, path: Path, data: Dict[str, Any]) -> Path:
        """Save data as JSON with optional compression.
        
        Args:
            path: File path
            data: Data to save
            
        Returns:
            Path to saved file
        """
        json_str = json.dumps(data, indent=2)
        json_bytes = json_str.encode("utf-8")
        
        if self.enable_compression and len(json_bytes) > self.compression_threshold_bytes:
            # Save compressed
            compressed_path = path.with_suffix(path.suffix + ".gz")
            with gzip.open(compressed_path, "wb") as f:
                f.write(json_bytes)
            return compressed_path
        else:
            # Save uncompressed
            with open(path, "w") as f:
                f.write(json_str)
            return path
    
    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load JSON data with automatic decompression.
        
        Args:
            path: File path
            
        Returns:
            Loaded data or None if not found
        """
        # Try compressed version first
        compressed_path = path.with_suffix(path.suffix + ".gz")
        if compressed_path.exists():
            try:
                with gzip.open(compressed_path, "rb") as f:
                    json_bytes = f.read()
                return json.loads(json_bytes.decode("utf-8"))
            except Exception:
                pass
        
        # Try uncompressed
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        
        return None
    
    def _save_pickle(self, path: Path, data: Any) -> Path:
        """Save data as pickle with optional compression.
        
        Args:
            path: File path
            data: Data to save
            
        Returns:
            Path to saved file
        """
        pickle_bytes = pickle.dumps(data)
        
        if self.enable_compression and len(pickle_bytes) > self.compression_threshold_bytes:
            # Save compressed
            compressed_path = path.with_suffix(path.suffix + ".gz")
            with gzip.open(compressed_path, "wb") as f:
                f.write(pickle_bytes)
            return compressed_path
        else:
            # Save uncompressed
            with open(path, "wb") as f:
                f.write(pickle_bytes)
            return path
    
    def _load_pickle(self, path: Path) -> Optional[Any]:
        """Load pickle data with automatic decompression.
        
        Args:
            path: File path
            
        Returns:
            Loaded data or None if not found
        """
        # Try compressed version first
        compressed_path = path.with_suffix(path.suffix + ".gz")
        if compressed_path.exists():
            try:
                with gzip.open(compressed_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass
        
        # Try uncompressed
        if path.exists():
            try:
                with open(path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass
        
        return None
    
    def _serialize_program(self, program: Any) -> Any:
        """Serialize program for storage.
        
        Args:
            program: Program object
            
        Returns:
            Serializable representation
        """
        if hasattr(program, "to_dict"):
            return program.to_dict()
        elif hasattr(program, "stages"):
            # Serialize Program with stages
            return {
                "stages": [
                    {
                        "operator": stage.operator,
                        "arguments": stage.arguments,
                        "metadata": getattr(stage, "metadata", {}),
                    }
                    for stage in program.stages
                ],
                "metadata": getattr(program, "metadata", {}),
            }
        elif hasattr(program, "__dict__"):
            return program.__dict__
        else:
            return str(program)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get artifact storage statistics.
        
        Returns:
            Statistics dictionary
        """
        def count_files(directory: Path) -> int:
            return len(list(directory.glob("*")))
        
        def dir_size(directory: Path) -> int:
            return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
        
        return {
            "programs_count": count_files(self.programs_dir),
            "evidence_count": count_files(self.evidence_dir),
            "invariants_count": count_files(self.invariants_dir),
            "checkpoints_count": count_files(self.checkpoints_dir),
            "total_size_bytes": dir_size(self.artifact_dir),
        }
