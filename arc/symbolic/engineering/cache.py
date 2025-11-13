"""Semantic caching for programs, fragments, and verification results."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from arc.symbolic.dsl.types import Program, Stage


class LRUCache:
    """Least Recently Used cache with size limit."""
    
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache, updating access order."""
        if key in self.cache:
            self.hits += 1
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return self.cache[key]
        self.misses += 1
        return None
    
    def put(self, key: str, value: Any) -> None:
        """Put value in cache, evicting LRU if needed."""
        if key in self.cache:
            # Update existing key
            self.cache.move_to_end(key)
        else:
            # Add new key
            if len(self.cache) >= self.maxsize:
                # Evict least recently used
                self.cache.popitem(last=False)
        self.cache[key] = value
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0.0
        return {
            "size": len(self.cache),
            "maxsize": self.maxsize,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
        }


class CacheManager:
    """Manages semantic caching for programs, fragments, and verification results."""
    
    def __init__(
        self,
        program_cache_size: int = 10000,
        fragment_cache_size: int = 5000,
        verification_cache_size: int = 2000,
    ):
        self.program_cache = LRUCache(maxsize=program_cache_size)
        self.fragment_cache = LRUCache(maxsize=fragment_cache_size)
        self.verification_cache = LRUCache(maxsize=verification_cache_size)
    
    def cache_program_semantics(
        self,
        program: Program,
        examples: List[Tuple[Any, Any]],
        interpreter: Optional[Any] = None,
    ) -> str:
        """Cache program semantics based on I/O behavior.
        
        Args:
            program: Program to cache
            examples: List of (input, output) pairs
            interpreter: Optional interpreter for execution
            
        Returns:
            Semantic hash key
        """
        key = self._compute_semantic_hash(program, examples, interpreter)
        self.program_cache.put(key, program)
        return key
    
    def get_cached_program(self, semantic_hash: str) -> Optional[Program]:
        """Retrieve cached program by semantic hash."""
        return self.program_cache.get(semantic_hash)
    
    def cache_fragment(self, fragment_id: str, fragment: Any) -> None:
        """Cache a reusable program fragment."""
        self.fragment_cache.put(fragment_id, fragment)
    
    def get_cached_fragment(self, fragment_id: str) -> Optional[Any]:
        """Retrieve cached fragment."""
        return self.fragment_cache.get(fragment_id)
    
    def cache_verification_result(
        self,
        program: Program,
        examples: List[Tuple[Any, Any]],
        result: Any,
    ) -> None:
        """Cache SMT verification result."""
        key = self._compute_verification_key(program, examples)
        self.verification_cache.put(key, result)
    
    def get_cached_verification(
        self,
        program: Program,
        examples: List[Tuple[Any, Any]],
    ) -> Optional[Any]:
        """Retrieve cached verification result."""
        key = self._compute_verification_key(program, examples)
        return self.verification_cache.get(key)
    
    def _compute_semantic_hash(
        self,
        program: Program,
        examples: List[Tuple[Any, Any]],
        interpreter: Optional[Any] = None,
    ) -> str:
        """Compute semantic hash based on program I/O behavior."""
        if interpreter is not None:
            try:
                # Execute program on examples to get semantic signature
                outputs = []
                for input_grid, _ in examples:
                    try:
                        output = interpreter.run(program, input_grid)
                        outputs.append(self._grid_to_hashable(output))
                    except Exception:
                        outputs.append(None)
                
                # Hash based on outputs
                content = json.dumps(outputs, sort_keys=True)
                return hashlib.sha256(content.encode()).hexdigest()
            except Exception:
                pass
        
        # Fallback: syntactic hash
        return self._compute_syntactic_hash(program)
    
    def _compute_syntactic_hash(self, program: Program) -> str:
        """Compute syntactic hash of program structure."""
        # Serialize program structure
        stages_repr = []
        for stage in program.stages:
            stage_dict = {
                "operator": stage.operator,
                "arguments": self._serialize_args(stage.arguments),
            }
            stages_repr.append(stage_dict)
        
        content = json.dumps(stages_repr, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _compute_verification_key(
        self,
        program: Program,
        examples: List[Tuple[Any, Any]],
    ) -> str:
        """Compute key for verification cache."""
        program_hash = self._compute_syntactic_hash(program)
        examples_hash = self._hash_examples(examples)
        combined = f"{program_hash}:{examples_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _hash_examples(self, examples: List[Tuple[Any, Any]]) -> str:
        """Hash example inputs and outputs."""
        examples_data = []
        for input_grid, output_grid in examples:
            examples_data.append({
                "input": self._grid_to_hashable(input_grid),
                "output": self._grid_to_hashable(output_grid),
            })
        content = json.dumps(examples_data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _grid_to_hashable(self, grid: Any) -> Any:
        """Convert grid to hashable representation."""
        if hasattr(grid, "to_list"):
            return grid.to_list()
        elif isinstance(grid, (list, tuple)):
            return grid
        elif hasattr(grid, "__array__"):
            import numpy as np
            return np.asarray(grid).tolist()
        else:
            return str(grid)
    
    def _serialize_args(self, args: List[Any]) -> List[Any]:
        """Serialize stage arguments for hashing."""
        serialized = []
        for arg in args:
            if isinstance(arg, (int, float, str, bool, type(None))):
                serialized.append(arg)
            elif isinstance(arg, (list, tuple)):
                serialized.append([self._serialize_single_arg(a) for a in arg])
            else:
                serialized.append(str(arg))
        return serialized
    
    def _serialize_single_arg(self, arg: Any) -> Any:
        """Serialize a single argument."""
        if isinstance(arg, (int, float, str, bool, type(None))):
            return arg
        else:
            return str(arg)
    
    def clear_all(self) -> None:
        """Clear all caches."""
        self.program_cache.clear()
        self.fragment_cache.clear()
        self.verification_cache.clear()
    
    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all caches."""
        return {
            "program_cache": self.program_cache.stats(),
            "fragment_cache": self.fragment_cache.stats(),
            "verification_cache": self.verification_cache.stats(),
        }
