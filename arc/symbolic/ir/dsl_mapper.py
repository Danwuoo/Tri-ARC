"""Object Graph to DSL mapping functionality."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.ir.object_graph import ObjectGraph, ObjectNode
from arc.symbolic.ir.sketch import Hole, ProgramSketch


class ObjectGraphToDSLMapper:
    """Maps between ObjectGraph and DSL Program representations.
    
    This class generates program sketches from input/output object graphs
    and instantiates sketches to create complete programs.
    """
    
    def __init__(self):
        """Initialize the mapper."""
        pass
    
    def generate_sketch(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> ProgramSketch:
        """Generate a program sketch from input/output object graphs.
        
        Analyzes the transformation from input to output and creates
        a sketch with holes for uncertain transformations.
        
        Args:
            input_graph: The input object graph
            output_graph: The output object graph
            
        Returns:
            ProgramSketch with stages and holes
        """
        stages: List[Union[Stage, Hole]] = []
        metadata = {
            "input_objects": input_graph.num_nodes,
            "output_objects": output_graph.num_nodes,
        }
        
        # Analyze the transformation
        transformation_type = self._analyze_transformation(input_graph, output_graph)
        
        if transformation_type == "identity":
            # No transformation needed
            pass
        
        elif transformation_type == "color_change":
            # Detect color mapping
            color_mapping = self._detect_color_mapping(input_graph, output_graph)
            if color_mapping and len(color_mapping) > 0:
                # Create stages for color changes
                for old_color, new_color in color_mapping.items():
                    stages.append(Stage(
                        operator="paint_grid_colour",
                        arguments=(old_color, new_color)
                    ))
            else:
                # Create a hole for color transformation
                stages.append(Hole(
                    id="color_transform",
                    type="color_operator",
                    domain={"paint_grid_colour", "recolour_by_condition"}
                ))
        
        elif transformation_type == "geometric":
            # Detect geometric transformations
            geometric_ops = self._detect_geometric_ops(input_graph, output_graph)
            if geometric_ops:
                for op in geometric_ops:
                    stages.append(Stage(operator=op, arguments=()))
            else:
                # Create a hole for geometric transformation
                stages.append(Hole(
                    id="geometric_transform",
                    type="geometric_operator",
                    domain={"rotate_90", "rotate_180", "rotate_270", "reflect_horizontal", "reflect_vertical"}
                ))
        
        elif transformation_type == "object_manipulation":
            # Object-level transformations
            stages.append(Hole(
                id="object_operation",
                type="object_operator",
                domain={"detect_objects", "select_object", "paint_region"}
            ))
        
        elif transformation_type == "complex":
            # Complex transformation - create multiple holes
            stages.append(Hole(
                id="stage_1",
                type="any_operator",
                domain=set()  # Will be refined during synthesis
            ))
            stages.append(Hole(
                id="stage_2",
                type="any_operator",
                domain=set()
            ))
        
        else:
            # Unknown transformation - create a generic hole
            stages.append(Hole(
                id="unknown_transform",
                type="any_operator",
                domain=set()
            ))
        
        return ProgramSketch(
            stages=stages,
            constraints=[],
            metadata=metadata
        )
    
    def instantiate_sketch(
        self,
        sketch: ProgramSketch,
        hole_assignments: Dict[str, Any]
    ) -> Program:
        """Fill holes in a sketch to create a complete program.
        
        Args:
            sketch: The program sketch with holes
            hole_assignments: Dictionary mapping hole IDs to their values
            
        Returns:
            Complete Program with all holes filled
            
        Raises:
            ValueError: If sketch has unfilled holes or invalid assignments
        """
        stages: List[Stage] = []
        
        for stage in sketch.stages:
            if isinstance(stage, Stage):
                # Already a complete stage
                stages.append(stage)
            elif isinstance(stage, Hole):
                # Need to fill this hole
                if stage.id not in hole_assignments:
                    raise ValueError(f"No assignment provided for hole '{stage.id}'")
                
                assignment = hole_assignments[stage.id]
                
                # Validate assignment
                if not stage.is_satisfied(assignment):
                    raise ValueError(
                        f"Assignment {assignment} does not satisfy constraints for hole '{stage.id}'"
                    )
                
                # Convert assignment to Stage
                if isinstance(assignment, Stage):
                    stages.append(assignment)
                elif isinstance(assignment, dict):
                    # Assignment is a dict with operator and arguments
                    stages.append(Stage(
                        operator=assignment["operator"],
                        arguments=tuple(assignment.get("arguments", []))
                    ))
                elif isinstance(assignment, str):
                    # Assignment is just an operator name
                    stages.append(Stage(operator=assignment, arguments=()))
                else:
                    raise ValueError(f"Invalid assignment type for hole '{stage.id}': {type(assignment)}")
        
        return Program(stages=tuple(stages))
    
    def _analyze_transformation(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> str:
        """Analyze the type of transformation between input and output.
        
        Args:
            input_graph: Input object graph
            output_graph: Output object graph
            
        Returns:
            Transformation type string
        """
        # Check if graphs are identical
        if self._graphs_equal(input_graph, output_graph):
            return "identity"
        
        # Check if only colors changed
        if self._only_colors_changed(input_graph, output_graph):
            return "color_change"
        
        # Check if it's a geometric transformation
        if self._is_geometric_transform(input_graph, output_graph):
            return "geometric"
        
        # Check if object count changed significantly
        if abs(input_graph.num_nodes - output_graph.num_nodes) > 2:
            return "object_manipulation"
        
        # Default to complex transformation
        return "complex"
    
    def _graphs_equal(
        self,
        graph_a: ObjectGraph,
        graph_b: ObjectGraph
    ) -> bool:
        """Check if two object graphs are equal.
        
        Args:
            graph_a: First graph
            graph_b: Second graph
            
        Returns:
            True if graphs are equal, False otherwise
        """
        if graph_a.num_nodes != graph_b.num_nodes:
            return False
        
        if graph_a.canvas_shape != graph_b.canvas_shape:
            return False
        
        # Simple equality check - could be more sophisticated
        return True
    
    def _only_colors_changed(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> bool:
        """Check if only colors changed between graphs.
        
        Args:
            input_graph: Input graph
            output_graph: Output graph
            
        Returns:
            True if only colors changed, False otherwise
        """
        if input_graph.num_nodes != output_graph.num_nodes:
            return False
        
        if input_graph.canvas_shape != output_graph.canvas_shape:
            return False
        
        # Check if colors are different
        input_colors = {node.color for node in input_graph.nodes}
        output_colors = {node.color for node in output_graph.nodes}
        
        # If colors are the same, it's not a color change
        if input_colors == output_colors:
            return False
        
        # Check if object positions/shapes are the same (simplified check)
        # In a real implementation, we'd compare bounding boxes and regions
        return True
    
    def _is_geometric_transform(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> bool:
        """Check if transformation is geometric (rotation, reflection).
        
        Args:
            input_graph: Input graph
            output_graph: Output graph
            
        Returns:
            True if transformation is geometric, False otherwise
        """
        # Check if canvas shape changed (might indicate rotation)
        if input_graph.canvas_shape != output_graph.canvas_shape:
            # Check if dimensions are swapped (90/270 degree rotation)
            h1, w1 = input_graph.canvas_shape
            h2, w2 = output_graph.canvas_shape
            if h1 == w2 and w1 == h2:
                return True
        
        # Check if object count is the same
        if input_graph.num_nodes == output_graph.num_nodes:
            return True
        
        return False
    
    def _detect_color_mapping(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> Optional[Dict[int, int]]:
        """Detect color mapping between input and output.
        
        Args:
            input_graph: Input graph
            output_graph: Output graph
            
        Returns:
            Dictionary mapping input colors to output colors, or None
        """
        # Collect colors from both graphs
        input_colors = {node.color for node in input_graph.nodes}
        output_colors = {node.color for node in output_graph.nodes}
        
        # Simple heuristic: if color sets are different, there's a mapping
        if input_colors != output_colors:
            # Try to infer mapping (simplified)
            # For now, create a simple 1-to-1 mapping if counts match
            if len(input_colors) == len(output_colors):
                input_list = sorted(input_colors)
                output_list = sorted(output_colors)
                mapping = dict(zip(input_list, output_list))
                return mapping
        
        return None
    
    def _detect_geometric_ops(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> List[str]:
        """Detect geometric operations between input and output.
        
        Args:
            input_graph: Input graph
            output_graph: Output graph
            
        Returns:
            List of geometric operator names
        """
        ops = []
        
        # Check for rotation
        h1, w1 = input_graph.canvas_shape
        h2, w2 = output_graph.canvas_shape
        
        if h1 == w2 and w1 == h2:
            # Possible 90 or 270 degree rotation
            ops.append("rotate_90")  # Placeholder
        elif h1 == h2 and w1 == w2:
            # Possible reflection or 180 degree rotation
            # Would need more analysis to determine which
            pass
        
        return ops
