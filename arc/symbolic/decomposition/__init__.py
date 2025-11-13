"""Decomposition and composition strategies for symbolic synthesis.

This module provides object-centric decomposition and parallel synthesis
capabilities for breaking down complex transformations into simpler,
composable parts.
"""

from arc.symbolic.decomposition.block_ops import (
    Alignment,
    BlockOperations,
    BoundaryProtocol,
    Direction,
)
from arc.symbolic.decomposition.integration import DecompositionIntegration
from arc.symbolic.decomposition.object_centric import (
    LocalTransformation,
    ObjectCentricDecomposer,
)
from arc.symbolic.decomposition.parallel import ParallelSynthesizer

__all__ = [
    "Alignment",
    "BlockOperations",
    "BoundaryProtocol",
    "DecompositionIntegration",
    "Direction",
    "LocalTransformation",
    "ObjectCentricDecomposer",
    "ParallelSynthesizer",
]
