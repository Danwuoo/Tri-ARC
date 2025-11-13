# SMT Gateway

This module provides SMT-based verification for DSL programs using the Z3 solver.

## Components

### ConstraintEncoder (`encoder.py`)
Translates DSL programs and grids into SMT constraints. Supports encoding of:
- Grid representations as Z3 arrays
- Common DSL primitives (rotate, reflect, transpose, replace_colour, etc.)
- Input/output examples as constraints

### BatchVerifier (`verifier.py`)
Verifies multiple candidate programs in parallel with:
- Batch verification with configurable timeouts
- Incremental solving using Z3 push/pop
- Result caching for identical programs
- Thread pool for parallel verification

### WitnessFunctionGenerator (`witness.py`)
Generates witness functions for sketch holes by:
- Backward propagation from expected outputs
- Domain refinement based on grid constraints
- Support for common transformation patterns

### BDD Support (`bdd.py`)
Provides BDD-based encoding and verification:
- Grid encoding as boolean functions
- Connectivity constraint encoding
- Equivalence checking
- Region mask encoding

## Usage

### Basic Verification

```python
from arc.symbolic.smt import ConstraintEncoder, BatchVerifier
from arc.symbolic.dsl.types import Program, Grid

# Create verifier
verifier = BatchVerifier(config={
    "timeout_per_candidate": 2.0,
    "enable_caching": True,
    "max_workers": 4
})

# Verify a batch of programs
candidates = [
    (program1, input_grid1, expected_output1),
    (program2, input_grid2, expected_output2),
]

results = verifier.verify_batch(candidates)

for result in results:
    if result.is_verified:
        print(f"Program {result.program_id} verified!")
    elif result.is_refuted:
        print(f"Program {result.program_id} refuted")
    else:
        print(f"Program {result.program_id} inconclusive: {result.status}")
```

### Witness Function Generation

```python
from arc.symbolic.smt import WitnessFunctionGenerator
from arc.symbolic.ir.sketch import ProgramSketch

# Create generator
generator = WitnessFunctionGenerator()

# Generate witness constraints
witness_constraints = generator.generate_witness(
    sketch=program_sketch,
    input_grid=input_grid,
    expected_output=expected_output
)

# Use constraints to refine hole domains
for hole_id, possible_values in witness_constraints.items():
    print(f"Hole {hole_id} can be: {possible_values}")
```

### BDD-based Verification

```python
from arc.symbolic.smt.bdd import BDDVerifier

# Create BDD verifier
bdd_verifier = BDDVerifier()

# Check grid equivalence
if bdd_verifier.verify_equivalence(grid1, grid2):
    print("Grids are equivalent")

# Verify connectivity
if bdd_verifier.verify_connectivity(grid, color=1, expected_components=3):
    print("Connectivity verified")
```

## Configuration

The SMT gateway can be configured through the symbolic module config:

```yaml
symbolic:
  smt:
    enabled: true
    timeout_per_candidate: 2.0
    enable_caching: true
    max_workers: 4
    timeout_ms: 5000
    enable_optimization: true
    max_grid_size: 900
```

## Integration with Solver

The SMT gateway is integrated into the symbolic solver for:
- Verification of candidate programs before submission to arbitrator
- Generation of SMT tokens for verified programs
- Witness function generation for sketch-guided synthesis
- BDD-based equivalence checking

## Limitations

### Current Limitations
- Complex primitives like `flood_fill` and `paint_region` have simplified encodings
- Region-based operations require known regions (not dynamically detected)
- Large grids (>30x30) may timeout in SMT solving
- Some DSL primitives are not yet fully encoded

### Future Enhancements
- Full encoding of all DSL primitives
- Dynamic region detection in SMT
- Optimization for large grids
- Integration with neural heuristics for constraint generation
- Support for quantified constraints

## Performance

Typical verification times:
- Simple programs (1-3 stages): 0.1-0.5 seconds
- Medium programs (4-6 stages): 0.5-2.0 seconds
- Complex programs (7+ stages): 2.0-5.0 seconds (may timeout)

Cache hit rates typically range from 30-60% depending on the task distribution.

## Dependencies

- `z3-solver>=4.15.0`: Z3 SMT solver
- `numpy`: Grid operations
- `concurrent.futures`: Parallel verification

## Testing

Run unit tests with:
```bash
pytest tests/symbolic/smt/
```

See `tests/symbolic/smt/test_smt_gateway.py` for comprehensive test coverage.
