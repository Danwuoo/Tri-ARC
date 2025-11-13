"""Intermediate Representation (IR) layer for symbolic synthesis.

This module provides bidirectional mappings between:
- Grids ↔ Object Graphs
- Object Graphs ↔ DSL Programs
"""

from arc.symbolic.ir.dsl_mapper import ObjectGraphToDSLMapper
from arc.symbolic.ir.grid_mapper import GridToObjectGraphMapper
from arc.symbolic.ir.object_graph import ObjectNode, ObjectGraph
from arc.symbolic.ir.sketch import Hole, ProgramSketch

__all__ = [
    "ObjectNode",
    "ObjectGraph",
    "GridToObjectGraphMapper",
    "ObjectGraphToDSLMapper",
    "Hole",
    "ProgramSketch",
]
