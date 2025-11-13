"""Integration of library management into the symbolic solver.

This module provides hooks and utilities to integrate fragment mining,
rule learning, and library curation into the solver workflow.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from arc.symbolic.dsl.types import Program
from arc.symbolic.egraph.engine import EGraph, RewriteRule
from arc.symbolic.library.curator import LibraryCurator
from arc.symbolic.library.fragment_miner import FragmentMiner, ProgramFragment
from arc.symbolic.library.persistence import LibraryPersistence
from arc.symbolic.library.rule_learner import RuleLearner
from arc.symbolic.search.types import CandidateProgram

LOGGER = logging.getLogger("arc.symbolic.library.integration")


class LibraryManager:
    """Manages DSL library integration with the symbolic solver.
    
    This class coordinates:
    - Fragment mining from successful programs
    - Rule learning from equivalence examples
    - Library curation and versioning
    - Persistence of library state
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the library manager.
        
        Args:
            config: Configuration dictionary with library management settings
        """
        self.config = config or {}
        library_cfg = self.config.get("library", {})
        
        # Initialize components
        self.fragment_miner = FragmentMiner(library_cfg.get("fragment_mining", {}))
        self.rule_learner = RuleLearner(library_cfg.get("rule_learning", {}))
        self.curator = LibraryCurator(library_cfg.get("curation", {}))
        self.persistence = LibraryPersistence(library_cfg.get("library_dir"))
        
        # Feature flags
        self.fragment_mining_enabled = library_cfg.get("fragment_mining", {}).get("enabled", True)
        self.rule_learning_enabled = library_cfg.get("rule_learning", {}).get("enabled", True)
        self.auto_prune_enabled = library_cfg.get("pruning", {}).get("enabled", True)
        
        # Pruning configuration
        self.prune_interval = library_cfg.get("pruning", {}).get("interval", 100)
        self.solve_count = 0
        
        # Load existing library state if available
        self._load_library_state()
        
        LOGGER.info("Library manager initialized")
    
    def on_solve_success(
        self,
        task_id: str,
        successful_programs: List[Program],
        candidates: List[CandidateProgram],
        egraph: Optional[EGraph] = None
    ) -> None:
        """Hook called when a task is successfully solved.
        
        This mines fragments and learns rules from successful programs.
        
        Args:
            task_id: ID of the solved task
            successful_programs: Programs that successfully solved the task
            candidates: All candidate programs generated
            egraph: Optional e-graph used during solving
        """
        if not successful_programs:
            return
        
        self.solve_count += 1
        
        # Mine fragments from successful programs
        if self.fragment_mining_enabled:
            try:
                fragments = self.fragment_miner.mine_fragments(successful_programs)
                
                for fragment in fragments:
                    self.curator.add_fragment(
                        fragment,
                        metadata={
                            "task_id": task_id,
                            "source": "fragment_mining"
                        }
                    )
                    # Record usage
                    self.curator.record_usage(fragment.id, fragment.frequency)
                    self.curator.record_impact(fragment.id, fragment.applicability_score)
                
                if fragments:
                    LOGGER.info(
                        f"Mined {len(fragments)} fragments from task {task_id}"
                    )
            except Exception as e:
                LOGGER.error(f"Fragment mining failed for task {task_id}: {e}")
        
        # Learn rules from e-graph if available
        if self.rule_learning_enabled and egraph is not None:
            try:
                # Extract equivalence examples from e-graph
                equivalence_examples = self._extract_equivalences_from_egraph(egraph)
                
                if equivalence_examples:
                    learned_rules = self.rule_learner.learn_rules(equivalence_examples)
                    
                    for rule in learned_rules:
                        self.curator.add_rule(
                            rule,
                            metadata={
                                "task_id": task_id,
                                "source": "rule_learning"
                            }
                        )
                    
                    if learned_rules:
                        LOGGER.info(
                            f"Learned {len(learned_rules)} rules from task {task_id}"
                        )
            except Exception as e:
                LOGGER.error(f"Rule learning failed for task {task_id}: {e}")
        
        # Periodic pruning
        if self.auto_prune_enabled and self.solve_count % self.prune_interval == 0:
            try:
                report = self.curator.prune_library()
                LOGGER.info(
                    f"Pruned library: removed {report.rules_removed} rules, "
                    f"{report.fragments_removed} fragments"
                )
            except Exception as e:
                LOGGER.error(f"Library pruning failed: {e}")
        
        # Save library state periodically
        if self.solve_count % 10 == 0:
            self._save_library_state()
    
    def on_solve_failure(
        self,
        task_id: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Hook called when a task fails to solve.
        
        This can be used to track rule failures and trigger rollbacks.
        
        Args:
            task_id: ID of the failed task
            reason: Reason for failure
            metadata: Optional metadata about the failure
        """
        # For now, just log the failure
        # In a full implementation, this could track which rules were used
        # and correlate failures with specific rules
        LOGGER.debug(f"Task {task_id} failed: {reason}")
    
    def get_active_rules(self) -> List[RewriteRule]:
        """Get all active rewrite rules from the library.
        
        Returns:
            List of active rewrite rules
        """
        return list(self.curator._rules.values())
    
    def get_active_fragments(self) -> List[ProgramFragment]:
        """Get all active fragments from the library.
        
        Returns:
            List of active program fragments
        """
        return list(self.curator._fragments.values())
    
    def get_library_stats(self) -> Dict[str, Any]:
        """Get statistics about the current library state.
        
        Returns:
            Dictionary with library statistics
        """
        stats = self.curator.get_library_stats()
        stats["solve_count"] = self.solve_count
        return stats
    
    def save_library(self) -> None:
        """Explicitly save the current library state."""
        self._save_library_state()
    
    def _load_library_state(self) -> None:
        """Load library state from disk if available."""
        try:
            state = self.persistence.load()
            if state is None:
                LOGGER.info("No existing library state found, starting fresh")
                return
            
            # Restore curator state
            # Note: We can't restore the actual rule functions, only metadata
            # In a full implementation, rules would need to be registered separately
            
            # Restore fragments
            for frag_id, frag_data in state.fragments.items():
                # Reconstruct fragment from serialized data
                # This is simplified - full implementation would need proper deserialization
                pass
            
            # Restore usage and impact data
            self.curator._usage_counts = dict(state.usage_counts)
            self.curator._impact_scores = dict(state.impact_scores)
            self.curator._blacklist = set(state.blacklist)
            self.curator._current_version = state.version
            
            LOGGER.info(f"Loaded library state version {state.version}")
            
        except Exception as e:
            LOGGER.warning(f"Failed to load library state: {e}")
    
    def _save_library_state(self) -> None:
        """Save current library state to disk."""
        try:
            self.persistence.save(
                primitives=self.curator._primitives,
                fragments=self.curator._fragments,
                rules=self.curator._rules,
                usage_counts=self.curator._usage_counts,
                impact_scores=self.curator._impact_scores,
                blacklist=self.curator._blacklist,
                versions=self.curator._versions,
                current_version=self.curator._current_version,
                metadata={
                    "solve_count": self.solve_count
                }
            )
            LOGGER.debug(f"Saved library state version {self.curator._current_version}")
        except Exception as e:
            LOGGER.error(f"Failed to save library state: {e}")
    
    def _extract_equivalences_from_egraph(
        self,
        egraph: EGraph
    ) -> List[tuple[Program, Program]]:
        """Extract equivalence examples from an e-graph.
        
        Args:
            egraph: The e-graph to extract from
        
        Returns:
            List of (program_a, program_b) pairs that are equivalent
        """
        equivalences = []
        
        # Extract programs from e-graph records
        # This is simplified - full implementation would need to traverse e-classes
        programs = [record.program for record in egraph._records.values()]
        
        # For now, just pair consecutive programs as equivalences
        # Real implementation would use e-class membership
        for i in range(len(programs) - 1):
            equivalences.append((programs[i], programs[i + 1]))
        
        return equivalences[:10]  # Limit to avoid too many examples


def add_library_hooks_to_solver(solver: Any, library_manager: LibraryManager) -> None:
    """Add library management hooks to a symbolic solver.
    
    This modifies the solver to call library management hooks at appropriate points.
    
    Args:
        solver: The symbolic solver instance
        library_manager: The library manager to integrate
    """
    # Store reference to library manager
    solver.library_manager = library_manager
    
    # Add library rules to e-graph if enabled
    if hasattr(solver, '_build_egraph'):
        original_build_egraph = solver._build_egraph
        
        def enhanced_build_egraph():
            egraph = original_build_egraph()
            if egraph is not None:
                # Add learned rules to e-graph
                for rule in library_manager.get_active_rules():
                    egraph.add_rule(rule)
            return egraph
        
        solver._build_egraph = enhanced_build_egraph
    
    LOGGER.info("Added library management hooks to solver")
