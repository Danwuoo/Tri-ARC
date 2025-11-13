"""Library persistence for DSL library state management.

This module implements save/load functionality for DSL library state,
version tracking, and library diff/merge utilities.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.library.curator import LibraryVersion, Primitive
from arc.symbolic.library.fragment_miner import ProgramFragment

LOGGER = logging.getLogger("arc.symbolic.library.persistence")


@dataclass
class LibraryState:
    """Complete state of the DSL library.
    
    Attributes:
        version: Current version string
        primitives: Dictionary of primitives
        fragments: Dictionary of fragments
        rules: Dictionary of rule metadata (actual rules not serialized)
        usage_counts: Usage statistics
        impact_scores: Impact scores
        blacklist: Set of blacklisted items
        versions: Version history
        metadata: Additional metadata
    """
    
    version: str
    primitives: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    fragments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    rules: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    usage_counts: Dict[str, int] = field(default_factory=dict)
    impact_scores: Dict[str, float] = field(default_factory=dict)
    blacklist: Set[str] = field(default_factory=set)
    versions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LibraryDiff:
    """Difference between two library versions.
    
    Attributes:
        from_version: Source version
        to_version: Target version
        added_primitives: Primitives added
        removed_primitives: Primitives removed
        modified_primitives: Primitives modified
        added_fragments: Fragments added
        removed_fragments: Fragments removed
        added_rules: Rules added
        removed_rules: Rules removed
    """
    
    from_version: str
    to_version: str
    added_primitives: Set[str] = field(default_factory=set)
    removed_primitives: Set[str] = field(default_factory=set)
    modified_primitives: Set[str] = field(default_factory=set)
    added_fragments: Set[str] = field(default_factory=set)
    removed_fragments: Set[str] = field(default_factory=set)
    added_rules: Set[str] = field(default_factory=set)
    removed_rules: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert diff to dictionary."""
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "added_primitives": list(self.added_primitives),
            "removed_primitives": list(self.removed_primitives),
            "modified_primitives": list(self.modified_primitives),
            "added_fragments": list(self.added_fragments),
            "removed_fragments": list(self.removed_fragments),
            "added_rules": list(self.added_rules),
            "removed_rules": list(self.removed_rules)
        }


class LibraryPersistence:
    """Manages persistence of DSL library state.
    
    This class handles:
    - Saving/loading library state to/from disk
    - Version tracking and changelog management
    - Library diff computation
    - Library merging from multiple sources
    """
    
    def __init__(self, library_dir: Optional[Path] = None):
        """Initialize library persistence.
        
        Args:
            library_dir: Directory to store library files (default: models/symbolic/library)
        """
        if library_dir is None:
            library_dir = Path("models/symbolic/library")
        
        self.library_dir = Path(library_dir)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.library_dir / "library_state.json"
        self.changelog_file = self.library_dir / "changelog.json"
        self.versions_dir = self.library_dir / "versions"
        self.versions_dir.mkdir(exist_ok=True)
    
    def save(
        self,
        primitives: Dict[str, Primitive],
        fragments: Dict[str, ProgramFragment],
        rules: Dict[str, Any],
        usage_counts: Dict[str, int],
        impact_scores: Dict[str, float],
        blacklist: Set[str],
        versions: List[LibraryVersion],
        current_version: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Save complete library state to disk.
        
        Args:
            primitives: Dictionary of primitives
            fragments: Dictionary of fragments
            rules: Dictionary of rules (metadata only)
            usage_counts: Usage statistics
            impact_scores: Impact scores
            blacklist: Set of blacklisted items
            versions: Version history
            current_version: Current version string
            metadata: Optional additional metadata
        """
        # Serialize primitives
        primitives_data = {}
        for name, prim in primitives.items():
            primitives_data[name] = {
                "name": prim.name,
                "type": prim.type,
                "version": prim.version,
                "metadata": prim.metadata
            }
        
        # Serialize fragments
        fragments_data = {}
        for frag_id, fragment in fragments.items():
            fragments_data[frag_id] = {
                "id": fragment.id,
                "stages": self._serialize_stages(fragment.stages),
                "parameters": list(fragment.parameters),
                "frequency": fragment.frequency,
                "complexity_reduction": fragment.complexity_reduction,
                "applicability_score": fragment.applicability_score,
                "metadata": fragment.metadata
            }
        
        # Serialize rules (metadata only, not the actual functions)
        rules_data = {}
        for rule_name, rule in rules.items():
            rules_data[rule_name] = {
                "name": rule.name if hasattr(rule, 'name') else rule_name,
                "description": rule.description if hasattr(rule, 'description') else "",
                "enabled": rule.enabled if hasattr(rule, 'enabled') else True
            }
        
        # Serialize versions
        versions_data = []
        for version in versions:
            versions_data.append({
                "version": version.version,
                "timestamp": version.timestamp,
                "primitives": list(version.primitives),
                "rules": list(version.rules),
                "fragments": list(version.fragments),
                "changelog": version.changelog
            })
        
        # Create state object
        state = LibraryState(
            version=current_version,
            primitives=primitives_data,
            fragments=fragments_data,
            rules=rules_data,
            usage_counts=usage_counts,
            impact_scores=impact_scores,
            blacklist=blacklist,
            versions=versions_data,
            metadata=metadata or {}
        )
        
        # Convert to dict and handle sets
        state_dict = asdict(state)
        state_dict['blacklist'] = list(state_dict['blacklist'])  # Convert set to list
        
        # Save to file
        with open(self.state_file, 'w') as f:
            json.dump(state_dict, f, indent=2)
        
        # Save version snapshot
        version_file = self.versions_dir / f"library_{current_version}.json"
        with open(version_file, 'w') as f:
            json.dump(state_dict, f, indent=2)
        
        LOGGER.info(f"Saved library state version {current_version} to {self.state_file}")
    
    def load(self) -> Optional[LibraryState]:
        """Load library state from disk.
        
        Returns:
            LibraryState if file exists, None otherwise
        """
        if not self.state_file.exists():
            LOGGER.warning(f"Library state file not found: {self.state_file}")
            return None
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            state = LibraryState(
                version=data["version"],
                primitives=data.get("primitives", {}),
                fragments=data.get("fragments", {}),
                rules=data.get("rules", {}),
                usage_counts=data.get("usage_counts", {}),
                impact_scores=data.get("impact_scores", {}),
                blacklist=set(data.get("blacklist", [])),
                versions=data.get("versions", []),
                metadata=data.get("metadata", {})
            )
            
            LOGGER.info(f"Loaded library state version {state.version}")
            return state
            
        except Exception as e:
            LOGGER.error(f"Failed to load library state: {e}")
            return None
    
    def load_version(self, version: str) -> Optional[LibraryState]:
        """Load a specific version of the library.
        
        Args:
            version: Version string to load
        
        Returns:
            LibraryState for that version if it exists, None otherwise
        """
        version_file = self.versions_dir / f"library_{version}.json"
        
        if not version_file.exists():
            LOGGER.warning(f"Version {version} not found")
            return None
        
        try:
            with open(version_file, 'r') as f:
                data = json.load(f)
            
            state = LibraryState(
                version=data["version"],
                primitives=data.get("primitives", {}),
                fragments=data.get("fragments", {}),
                rules=data.get("rules", {}),
                usage_counts=data.get("usage_counts", {}),
                impact_scores=data.get("impact_scores", {}),
                blacklist=set(data.get("blacklist", [])),
                versions=data.get("versions", []),
                metadata=data.get("metadata", {})
            )
            
            LOGGER.info(f"Loaded library version {version}")
            return state
            
        except Exception as e:
            LOGGER.error(f"Failed to load version {version}: {e}")
            return None
    
    def compute_diff(
        self,
        from_state: LibraryState,
        to_state: LibraryState
    ) -> LibraryDiff:
        """Compute difference between two library states.
        
        Args:
            from_state: Source state
            to_state: Target state
        
        Returns:
            LibraryDiff describing the changes
        """
        diff = LibraryDiff(
            from_version=from_state.version,
            to_version=to_state.version
        )
        
        # Compute primitive changes
        from_prims = set(from_state.primitives.keys())
        to_prims = set(to_state.primitives.keys())
        
        diff.added_primitives = to_prims - from_prims
        diff.removed_primitives = from_prims - to_prims
        
        # Check for modifications
        common_prims = from_prims & to_prims
        for prim_name in common_prims:
            if from_state.primitives[prim_name] != to_state.primitives[prim_name]:
                diff.modified_primitives.add(prim_name)
        
        # Compute fragment changes
        from_frags = set(from_state.fragments.keys())
        to_frags = set(to_state.fragments.keys())
        
        diff.added_fragments = to_frags - from_frags
        diff.removed_fragments = from_frags - to_frags
        
        # Compute rule changes
        from_rules = set(from_state.rules.keys())
        to_rules = set(to_state.rules.keys())
        
        diff.added_rules = to_rules - from_rules
        diff.removed_rules = from_rules - to_rules
        
        return diff
    
    def merge_libraries(
        self,
        base_state: LibraryState,
        incoming_state: LibraryState,
        strategy: str = "union"
    ) -> LibraryState:
        """Merge two library states.
        
        Args:
            base_state: Base library state
            incoming_state: Incoming library state to merge
            strategy: Merge strategy ("union", "base_priority", "incoming_priority")
        
        Returns:
            Merged LibraryState
        """
        merged = LibraryState(
            version=self._merge_versions(base_state.version, incoming_state.version),
            metadata={"merged_from": [base_state.version, incoming_state.version]}
        )
        
        if strategy == "union":
            # Union: include all items from both
            merged.primitives = {**base_state.primitives, **incoming_state.primitives}
            merged.fragments = {**base_state.fragments, **incoming_state.fragments}
            merged.rules = {**base_state.rules, **incoming_state.rules}
            
            # Merge usage counts (sum)
            all_keys = set(base_state.usage_counts.keys()) | set(incoming_state.usage_counts.keys())
            merged.usage_counts = {
                key: base_state.usage_counts.get(key, 0) + incoming_state.usage_counts.get(key, 0)
                for key in all_keys
            }
            
            # Merge impact scores (average)
            all_keys = set(base_state.impact_scores.keys()) | set(incoming_state.impact_scores.keys())
            merged.impact_scores = {}
            for key in all_keys:
                base_score = base_state.impact_scores.get(key, 0.0)
                incoming_score = incoming_state.impact_scores.get(key, 0.0)
                count = (1 if key in base_state.impact_scores else 0) + \
                        (1 if key in incoming_state.impact_scores else 0)
                merged.impact_scores[key] = (base_score + incoming_score) / count
            
            # Union of blacklists
            merged.blacklist = base_state.blacklist | incoming_state.blacklist
            
        elif strategy == "base_priority":
            # Base priority: prefer base, add new from incoming
            merged.primitives = dict(base_state.primitives)
            for key, value in incoming_state.primitives.items():
                if key not in merged.primitives:
                    merged.primitives[key] = value
            
            merged.fragments = dict(base_state.fragments)
            for key, value in incoming_state.fragments.items():
                if key not in merged.fragments:
                    merged.fragments[key] = value
            
            merged.rules = dict(base_state.rules)
            for key, value in incoming_state.rules.items():
                if key not in merged.rules:
                    merged.rules[key] = value
            
            merged.usage_counts = dict(base_state.usage_counts)
            merged.impact_scores = dict(base_state.impact_scores)
            merged.blacklist = set(base_state.blacklist)
            
        elif strategy == "incoming_priority":
            # Incoming priority: prefer incoming, keep base as fallback
            merged.primitives = {**base_state.primitives, **incoming_state.primitives}
            merged.fragments = {**base_state.fragments, **incoming_state.fragments}
            merged.rules = {**base_state.rules, **incoming_state.rules}
            merged.usage_counts = {**base_state.usage_counts, **incoming_state.usage_counts}
            merged.impact_scores = {**base_state.impact_scores, **incoming_state.impact_scores}
            merged.blacklist = base_state.blacklist | incoming_state.blacklist
        
        # Merge version histories
        merged.versions = base_state.versions + incoming_state.versions
        
        LOGGER.info(
            f"Merged libraries {base_state.version} and {incoming_state.version} "
            f"using strategy '{strategy}'"
        )
        
        return merged
    
    def export_changelog(self, versions: List[LibraryVersion]) -> None:
        """Export version changelog to file.
        
        Args:
            versions: List of library versions
        """
        changelog_data = []
        for version in versions:
            changelog_data.append({
                "version": version.version,
                "timestamp": version.timestamp,
                "changelog": version.changelog,
                "primitives_count": len(version.primitives),
                "rules_count": len(version.rules),
                "fragments_count": len(version.fragments)
            })
        
        with open(self.changelog_file, 'w') as f:
            json.dump(changelog_data, f, indent=2)
        
        LOGGER.info(f"Exported changelog with {len(versions)} versions")
    
    def _serialize_stages(self, stages: tuple) -> List[Dict[str, Any]]:
        """Serialize a tuple of stages to JSON-compatible format."""
        result = []
        for stage in stages:
            result.append({
                "operator": stage.operator,
                "arguments": list(stage.arguments)
            })
        return result
    
    def _deserialize_stages(self, stages_data: List[Dict[str, Any]]) -> tuple:
        """Deserialize stages from JSON format."""
        stages = []
        for stage_data in stages_data:
            stages.append(Stage(
                operator=stage_data["operator"],
                arguments=tuple(stage_data["arguments"])
            ))
        return tuple(stages)
    
    def _merge_versions(self, version_a: str, version_b: str) -> str:
        """Merge two version strings."""
        # Parse versions
        parts_a = list(map(int, version_a.split('.')))
        parts_b = list(map(int, version_b.split('.')))
        
        # Take max of each component
        merged = [max(a, b) for a, b in zip(parts_a, parts_b)]
        
        # Increment patch version
        merged[2] += 1
        
        return '.'.join(map(str, merged))
