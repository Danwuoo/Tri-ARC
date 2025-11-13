# Decomposition and Composition Module

This module implements object-centric decomposition and parallel synthesis strategies for breaking down complex grid transformations into simpler, composable parts.

## Overview

The decomposition module provides three main capabilities:

1. **Object-Centric Decomposition**: Breaks down grid transformations into local object transformations
2. **Parallel Synthesis**: Discovers and synthesizes commutative substeps independently
3. **Block-Level Operations**: Provides primitives for concatenating, tiling, and composing grid blocks

## Components

### ObjectCentricDecomposer

Decomposes grid transformations into object-centric local transformations.

**Key Methods:**
- `decompose_task(input_graph, output_graph)`: Decomposes a task into local object transformations
- `synthesize_local_transformation(input_object, output_object)`: Synthesizes a transformation for a single object
- `synthesize_composition_rule(local_transformations)`: Composes local transformations into a complete program

**Example:**
```python
from arc.symbolic.decomposition import ObjectCentricDecomposer
from arc.symbolic.ir import GridToObjectGraphMapper

# Create decomposer
decomposer = ObjectCentricDecomposer()

# Map grids to object graphs
mapper = GridToObjectGraphMapper()
input_graph = mapper.map_grid_to_objects(input_grid)
output_graph = mapper.map_grid_to_objects(output_grid)

# Decompose task
local_transformations = decomposer.decompose_task(input_graph, output_graph)

# Compose into complete program
program = decomposer.synthesize_composition_rule(local_transformations)
```

### ParallelSynthesizer

Synthesizes commutative substeps in parallel and merges results.

**Key Methods:**
- `discover_commutative_substeps(program)`: Discovers groups of commutative substeps
- `synthesize_parallel(substeps, examples)`: Synthesizes substeps in parallel
- `merge_in_egraph(parallel_results, egraph)`: Merges results into an e-graph

**Example:**
```python
from arc.symbolic.decomposition import ParallelSynthesizer

# Create synthesizer
synthesizer = ParallelSynthesizer()

# Discover commutative substeps
groups = synthesizer.discover_commutative_substeps(program)

# Synthesize alternatives
alternatives = synthesizer.synthesize_parallel(groups)

# Merge into e-graph
egraph = synthesizer.merge_in_egraph(alternatives, egraph)
```

### BlockOperations

Library of block-level operations for grid composition.

**Key Methods:**
- `concatenate(blocks, direction, boundary)`: Concatenates grids horizontally or vertically
- `tile(block, rows, cols, boundary)`: Tiles a grid in a pattern
- `align(block, canvas_shape, alignment, fill_color)`: Aligns a block within a canvas
- `add_spacing(block, top, bottom, left, right, fill_color)`: Adds spacing around a block
- `overlay(base, overlay, position, transparent_color)`: Overlays one grid on another

**Example:**
```python
from arc.symbolic.decomposition import BlockOperations, Direction, Alignment

# Concatenate grids horizontally
result = BlockOperations.concatenate([grid1, grid2], Direction.HORIZONTAL)

# Tile a pattern
tiled = BlockOperations.tile(block, rows=3, cols=3)

# Align in center
aligned = BlockOperations.align(block, (10, 10), Alignment.CENTER)

# Overlay with transparency
overlaid = BlockOperations.overlay(base, overlay, (2, 2), transparent_color=0)
```

### LocalTransformation

Data structure representing a local transformation applied to a single object.

**Attributes:**
- `input_object`: The input object node
- `output_object`: The output object node
- `transformation`: The DSL program that transforms input to output
- `confidence`: Confidence score (0.0 to 1.0)
- `metadata`: Additional metadata

**Methods:**
- `to_dict()`: Serializes to dictionary
- `to_json()`: Serializes to JSON string

## Integration

### DecompositionIntegration

Integrates decomposition strategies into the symbolic solver.

**Configuration:**
```yaml
symbolic:
  decomposition:
    enabled: true
    object_centric: true
    parallel_synthesis: true
    matching_threshold: 0.7
    max_local_depth: 5
    synthesis_timeout: 5.0
    max_parallel_depth: 3
    commutativity_threshold: 0.9
```

**Usage in Solver:**
```python
# The solver automatically initializes decomposition if enabled
solver = SymbolicSolver(config)

# Decomposition is applied during the solve process
result = solver.solve(task)
```

## Requirements Mapping

This implementation satisfies the following requirements from the specification:

- **Requirement 9.1**: Object-centric decomposition with local transformation synthesis
- **Requirement 9.2**: Composition rule synthesis for combining local transformations
- **Requirement 9.3**: Discovery and parallel synthesis of commutative substeps
- **Requirement 9.4**: E-graph merging for parallel synthesis results
- **Requirement 9.5**: Block-level operations library with boundary protocols

## Testing

Comprehensive unit tests are provided in `tests/symbolic/test_decomposition.py`:

```bash
# Run decomposition tests
pytest tests/symbolic/test_decomposition.py -v

# Run with coverage
pytest tests/symbolic/test_decomposition.py --cov=arc.symbolic.decomposition
```

Test coverage includes:
- LocalTransformation data structure and serialization
- Object-centric decomposition and matching
- Local transformation synthesis
- Composition rule generation
- Commutative substep discovery
- Parallel synthesis
- Block-level operations (concatenate, tile, align, overlay)
- Integration with solver

## Architecture

```
arc/symbolic/decomposition/
├── __init__.py              # Module exports
├── object_centric.py        # Object-centric decomposition
├── parallel.py              # Parallel synthesis
├── block_ops.py             # Block-level operations
├── integration.py           # Solver integration
└── README.md                # This file
```

## Future Enhancements

Potential improvements for future iterations:

1. **Advanced Matching**: More sophisticated object matching algorithms (graph isomorphism, learned embeddings)
2. **Neural Guidance**: Use neural models to guide decomposition and composition
3. **Learned Commutativity**: Learn commutative operator pairs from data
4. **Hierarchical Decomposition**: Multi-level decomposition for complex tasks
5. **Constraint Propagation**: Propagate constraints between local transformations
6. **Adaptive Strategies**: Dynamically select decomposition strategy based on task features

## References

- Requirements: `.kiro/specs/symbolic-synthesis-enhancement/requirements.md` (Requirement 9)
- Design: `.kiro/specs/symbolic-synthesis-enhancement/design.md` (Section 8)
- Tasks: `.kiro/specs/symbolic-synthesis-enhancement/tasks.md` (Phase 8)
