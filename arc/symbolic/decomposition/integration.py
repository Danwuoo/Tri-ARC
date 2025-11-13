"""Integration of decomposition strategies into the symbolic solver.

This module provides integration points for object-centric decomposition
and parallel synthesis within the main symbolic solver workflow.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from arc.symbolic.decomposition.object_centric import (
    LocalTransformation,
    ObjectCentricDecomposer,
)
from arc.symbolic.decomposition.parallel import ParallelSynthesizer
from arc.symbolic.dsl.types import Grid, Program
from arc.symbolic.ir.object_graph import ObjectGraph

LOGGER = logging.getLogger("arc.symbolic.decomposition")


class DecompositionIntegration:
    """Integrates decomposition strategies into the symbolic solver.
    
    This class provides:
    - Object-centric decomposition option for complex tasks
    - Parallel synthesis for commutative substeps
    - E-graph merging for parallel results
    
    Requirements: 9.1, 9.2, 9.3, 9.4
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize decomposition integration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        decomp_cfg = self.config.get("decomposition", {})
        
        self.enabled = bool(decomp_cfg.get("enabled", False))
        self.object_centric_enabled = bool(decomp_cfg.get("object_centric", False))
        self.parallel_synthesis_enabled = bool(decomp_cfg.get("parallel_synthesis", False))
        
        if self.enabled:
            self.object_decomposer = ObjectCentricDecomposer(decomp_cfg)
            self.parallel_synthesizer = ParallelSynthesizer(decomp_cfg)
            LOGGER.info(
                "Decomposition integration initialized (object_centric=%s, parallel=%s)",
                self.object_centric_enabled,
                self.parallel_synthesis_enabled
            )
        else:
            self.object_decomposer = None
            self.parallel_synthesizer = None
    
    def try_object_centric_decomposition(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> Optional[List[LocalTransformation]]:
        """Attempt object-centric decomposition of a task.
        
        Args:
            input_graph: Input object graph
            output_graph: Output object graph
            
        Returns:
            List of local transformations if successful, None otherwise
            
        Requirements: 9.1, 9.2
        """
        if not self.enabled or not self.object_centric_enabled:
            return None
        
        if not self.object_decomposer:
            return None
        
        try:
            local_transformations = self.object_decomposer.decompose_task(
                input_graph,
                output_graph
            )
            
            if local_transformations:
                LOGGER.info(
                    "Object-centric decomposition found %d local transformations",
                    len(local_transformations)
                )
                return local_transformations
            
        except Exception as e:
            LOGGER.debug("Object-centric decomposition failed: %s", e)
        
        return None
    
    def compose_local_transformations(
        self,
        local_transformations: List[LocalTransformation]
    ) -> Optional[Program]:
        """Compose local transformations into a complete program.
        
        Args:
            local_transformations: List of local transformations
            
        Returns:
            Composed program if successful, None otherwise
            
        Requirements: 9.2
        """
        if not self.enabled or not self.object_centric_enabled:
            return None
        
        if not self.object_decomposer or not local_transformations:
            return None
        
        try:
            composed_program = self.object_decomposer.synthesize_composition_rule(
                local_transformations
            )
            
            if composed_program and composed_program.stages:
                LOGGER.info(
                    "Composed %d local transformations into program with %d stages",
                    len(local_transformations),
                    len(composed_program.stages)
                )
                return composed_program
            
        except Exception as e:
            LOGGER.debug("Composition failed: %s", e)
        
        return None
    
    def try_parallel_synthesis(
        self,
        program: Program,
        examples: Optional[List[Any]] = None
    ) -> Optional[List[Program]]:
        """Attempt parallel synthesis of commutative substeps.
        
        Args:
            program: Program to analyze for parallel synthesis
            examples: Optional examples for validation
            
        Returns:
            List of alternative programs if successful, None otherwise
            
        Requirements: 9.3
        """
        if not self.enabled or not self.parallel_synthesis_enabled:
            return None
        
        if not self.parallel_synthesizer:
            return None
        
        try:
            # Discover commutative substeps
            commutative_groups = self.parallel_synthesizer.discover_commutative_substeps(
                program
            )
            
            if not commutative_groups:
                return None
            
            LOGGER.info(
                "Found %d commutative groups in program",
                len(commutative_groups)
            )
            
            # Synthesize alternatives
            alternative_programs = self.parallel_synthesizer.synthesize_parallel(
                commutative_groups,
                examples
            )
            
            if alternative_programs:
                LOGGER.info(
                    "Parallel synthesis generated %d alternative programs",
                    len(alternative_programs)
                )
                return alternative_programs
            
        except Exception as e:
            LOGGER.debug("Parallel synthesis failed: %s", e)
        
        return None
    
    def merge_parallel_results(
        self,
        parallel_results: List[Program],
        egraph: Any
    ) -> Any:
        """Merge parallel synthesis results into an e-graph.
        
        Args:
            parallel_results: List of programs from parallel synthesis
            egraph: E-graph to merge into
            
        Returns:
            Updated e-graph
            
        Requirements: 9.4
        """
        if not self.enabled or not self.parallel_synthesis_enabled:
            return egraph
        
        if not self.parallel_synthesizer or not parallel_results:
            return egraph
        
        try:
            updated_egraph = self.parallel_synthesizer.merge_in_egraph(
                parallel_results,
                egraph
            )
            
            LOGGER.info(
                "Merged %d parallel results into e-graph",
                len(parallel_results)
            )
            
            return updated_egraph
            
        except Exception as e:
            LOGGER.debug("E-graph merging failed: %s", e)
            return egraph
    
    def enhance_search_with_decomposition(
        self,
        input_graph: Optional[ObjectGraph],
        output_graph: Optional[ObjectGraph],
        current_candidates: List[Program],
        egraph: Optional[Any] = None
    ) -> List[Program]:
        """Enhance search with decomposition strategies.
        
        This method applies both object-centric decomposition and parallel
        synthesis to augment the current set of candidate programs.
        
        Args:
            input_graph: Input object graph (if available)
            output_graph: Output object graph (if available)
            current_candidates: Current candidate programs
            egraph: Optional e-graph for merging results
            
        Returns:
            Enhanced list of candidate programs
            
        Requirements: 9.1, 9.2, 9.3, 9.4
        """
        enhanced_candidates = list(current_candidates)
        
        # Try object-centric decomposition
        if input_graph and output_graph:
            local_transformations = self.try_object_centric_decomposition(
                input_graph,
                output_graph
            )
            
            if local_transformations:
                composed_program = self.compose_local_transformations(
                    local_transformations
                )
                if composed_program:
                    enhanced_candidates.append(composed_program)
        
        # Try parallel synthesis on existing candidates
        all_parallel_results = []
        for candidate in current_candidates:
            parallel_results = self.try_parallel_synthesis(candidate)
            if parallel_results:
                all_parallel_results.extend(parallel_results)
        
        # Merge parallel results into e-graph if available
        if all_parallel_results and egraph:
            self.merge_parallel_results(all_parallel_results, egraph)
        else:
            enhanced_candidates.extend(all_parallel_results)
        
        return enhanced_candidates
