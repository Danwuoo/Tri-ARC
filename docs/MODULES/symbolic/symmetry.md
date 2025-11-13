# Symmetry Detection and Normalization

This module provides symmetry detection and normalization capabilities for the symbolic synthesis system. It helps reduce search space by identifying and exploiting symmetries in grids, programs, and object graphs.

## Components

### ColorNormalizer

Normalizes color labels in grids to canonical form, treating color-permuted grids as equivalent.

**Strategies:**
- `frequency`: Orders colors by frequency (most common first)
- `appearance`: Orders colors by first appearance in the grid
- `sorted`: Simple sorted order

**Usage:**
```python
from arc.symbolic.symmetry import ColorNormalizer

normalizer = ColorNormalizer(strategy="frequency")
normalized_examples, mapping = normalizer.canonical_relabel(examples)
```

### SymmetryDetector

Detects symmetries in grids and object graphs.

**Detected Symmetries:**
- Horizontal reflection
- Vertical reflection
- 90-degree rotation
- 180-degree rotation
- Dihedral groups

**Usage:**
```python
from arc.symbolic.symmetry import SymmetryDetector

detector = SymmetryDetector()
symmetry_group = detector.detect_grid_symmetry(grid)
print(f"Symmetry type: {symmetry_group.type}, order: {symmetry_group.order}")

# Compute quotient representatives to deduplicate symmetric programs
representatives = detector.compute_quotient_representatives(programs, symmetry_group)
```

### StepNormalizer

Normalizes sequences of commutative program stages to canonical form.

**Features:**
- Detects commutative operation pairs
- Reorders commutative stages to canonical form
- Supports custom commutative groups

**Usage:**
```python
from arc.symbolic.symmetry import StepNormalizer

normalizer = StepNormalizer()
normalized_stages = normalizer.normalize_sequence(program.stages)

# Add custom commutative operations
normalizer.add_commutative_pair("op_a", "op_b")
```

## Integration with Solver

The symmetry components are integrated into the `SymbolicSolver` and can be enabled via configuration:

```yaml
symbolic:
  symmetry:
    enabled: true
    color_normalization: true
    color_normalization_strategy: "frequency"  # or "appearance", "sorted"
    symmetry_detection: true
    step_normalization: true
```

### What Happens When Enabled

1. **Color Normalization** (preprocessing):
   - Applied to training examples before search
   - Reduces search space by treating color permutations as equivalent

2. **Step Normalization** (during verification):
   - Applied to candidate programs before verification
   - Ensures commutative operations are in canonical order

3. **Symmetry Detection** (post-processing):
   - Detects symmetries in input grids
   - Deduplicates candidates using quotient representatives
   - Reduces redundant solutions

## Data Structures

### ColorMapping

Represents a color mapping for normalization:
```python
@dataclass(frozen=True)
class ColorMapping:
    forward: Dict[int, int]      # Original -> Canonical
    backward: Dict[int, int]     # Canonical -> Original
    canonical_order: Tuple[int, ...]
```

### SymmetryGroup

Represents a symmetry group:
```python
@dataclass(frozen=True)
class SymmetryGroup:
    generators: Tuple[str, ...]  # Transformation names
    order: int                   # Group order (size)
    type: str                    # Group type (e.g., "dihedral_4")
```

### Isomorphism

Represents an isomorphism between object graphs:
```python
@dataclass(frozen=True)
class Isomorphism:
    node_mapping: Dict[int, int]
    edge_mapping: Dict[Tuple[int, int], Tuple[int, int]]
    confidence: float
```

## Performance Considerations

- **Color Normalization**: O(n) where n is the number of pixels
- **Symmetry Detection**: O(n) for grid symmetries
- **Object Graph Isomorphism**: O(n!) worst case (uses backtracking)
- **Step Normalization**: O(m log m) where m is the number of stages

## Testing

Comprehensive tests are available in `tests/symbolic/test_symmetry.py`:

```bash
pytest tests/symbolic/test_symmetry.py -v
```

## Future Enhancements

- More sophisticated graph isomorphism algorithms (e.g., VF2)
- Neural-guided symmetry detection
- Automatic discovery of commutative operation pairs
- Symmetry-aware cost models
- Group-theoretic optimizations

## References

- Requirements: 5.1, 5.2, 5.3, 5.4 in the design document
- Design: See `docs/MODULES/symbolic_enhancements.md`
