# Symbolic Verifier API Documentation

## Overview

The Symbolic Verifier API provides interfaces for program verification, counterexample generation, and invariant checking. It integrates SMT solving, CEGIS, and program repair.

## Core Classes

### BatchVerifier

Batch verification of candidate programs using SMT solver.

```python
from arc.symbolic.smt import BatchVerifier

verifier = BatchVerifier(config)
results = verifier.verify_batch(candidates)
```

#### Constructor

```python
def __init__(self, config: Dict[str, Any])
```

**Configuration Keys**:
```yaml
smt:
  enabled: true
  timeout_per_candidate: 2.0
  batch_size: 10
  solver: "z3"  # "z3" or "cvc5"
  parallel: true
  cache_results: true
```

#### verify_batch()

```python
def verify_batch(
    self,
    candidates: List[Tuple[Program, List[Example]]],
    timeout_per_candidate: float = 2.0
) -> List[VerificationResult]
```

**Parameters**:
- `candidates`: List of (program, examples) tuples to verify
- `timeout_per_candidate`: Timeout in seconds per candidate

**Returns**: List of `VerificationResult` objects with fields:
- `program_id`: Program identifier
- `status`: "sat" (verified), "unsat" (incorrect), "unknown", "timeout"
- `verification_time`: Time taken in seconds
- `model`: Satisfying model (if sat)
- `unsat_core`: Unsatisfiable core (if unsat)
- `metadata`: Additional information

**Example**:
```python
candidates = [
    (program1, task["train"]),
    (program2, task["train"]),
    (program3, task["train"])
]

results = verifier.verify_batch(candidates, timeout_per_candidate=2.0)

verified_programs = [
    candidates[i][0] 
    for i, result in enumerate(results) 
    if result.status == "sat"
]

print(f"Verified {len(verified_programs)} / {len(candidates)} programs")
```

#### verify_incremental()

```python
def verify_incremental(
    self,
    program: Program,
    examples: List[Example],
    solver_context: Optional[z3.Solver] = None
) -> VerificationResult
```

**Parameters**:
- `program`: Program to verify
- `examples`: Examples to verify against
- `solver_context`: Reusable solver context (for efficiency)

**Returns**: `VerificationResult`

**Example**:
```python
# Create reusable context
context = verifier.create_context()

# Verify multiple programs incrementally
for program in candidates:
    result = verifier.verify_incremental(program, examples, context)
    if result.status == "sat":
        verified.append(program)
```

### ConstraintEncoder

Encodes DSL programs and grids as SMT constraints.

```python
from arc.symbolic.smt import ConstraintEncoder

encoder = ConstraintEncoder(config)
constraints = encoder.encode_program(program, examples)
```

#### encode_program()

```python
def encode_program(
    self,
    program: Program,
    examples: List[Example]
) -> SMTConstraintSet
```

**Parameters**:
- `program`: Program to encode
- `examples`: Examples to encode

**Returns**: `SMTConstraintSet` with fields:
- `variables`: Dictionary of SMT variables
- `constraints`: List of SMT constraints
- `assertions`: List of assertions to check
- `metadata`: Encoding metadata

**Example**:
```python
program = Program([
    Stage("rotate", [90]),
    Stage("reflect_h", [])
])

constraints = encoder.encode_program(program, task["train"])

# Use with Z3
import z3
solver = z3.Solver()
for constraint in constraints.constraints:
    solver.add(constraint)

result = solver.check()
print(f"Verification result: {result}")
```

#### encode_grid()

```python
def encode_grid(
    self,
    grid: Grid,
    name: str
) -> SMTArray
```

**Parameters**:
- `grid`: Grid to encode
- `name`: Variable name for the grid

**Returns**: `SMTArray` representing the grid

**Example**:
```python
input_grid = np.array([[0, 1], [1, 0]])
smt_grid = encoder.encode_grid(input_grid, "input")

# Access Z3 array
z3_array = smt_grid.z3_array
```

### WitnessFunctionGenerator

Generates witness functions for sketch holes.

```python
from arc.symbolic.smt import WitnessFunctionGenerator

generator = WitnessFunctionGenerator(config)
witnesses = generator.generate_witness(sketch, examples)
```

#### generate_witness()

```python
def generate_witness(
    self,
    sketch: ProgramSketch,
    examples: List[Example]
) -> Dict[str, Set[Any]]
```

**Parameters**:
- `sketch`: Program sketch with holes
- `examples`: Examples to generate witnesses from

**Returns**: Dictionary mapping hole IDs to sets of valid values

**Example**:
```python
from arc.symbolic.ir import ProgramSketch, Hole

sketch = ProgramSketch(
    stages=[
        Stage("rotate", [Hole("angle", {0, 90, 180, 270})]),
        Stage("paint_region", [Hole("color", {1, 2, 3, 4, 5})])
    ]
)

witnesses = generator.generate_witness(sketch, task["train"])

print(f"Valid angles: {witnesses['angle']}")
print(f"Valid colors: {witnesses['color']}")

# Use witnesses to constrain search
for hole_id, valid_values in witnesses.items():
    sketch.get_hole(hole_id).domain = valid_values
```

#### backward_propagate()

```python
def backward_propagate(
    self,
    output_grid: Grid,
    stage: Stage
) -> Set[Any]
```

**Parameters**:
- `output_grid`: Desired output grid
- `stage`: Stage to propagate through

**Returns**: Set of valid argument values

**Example**:
```python
# What colors could produce this output?
output = np.array([[1, 1], [1, 1]])
stage = Stage("paint_region", [Hole("color")])

valid_colors = generator.backward_propagate(output, stage)
print(f"Valid colors: {valid_colors}")
```

### InvariantChecker

Checks program invariants.

```python
from arc.symbolic.verification import InvariantChecker

checker = InvariantChecker(config)
is_valid = checker.check_all_invariants(program, examples)
```

#### check_color_conservation()

```python
def check_color_conservation(
    self,
    input_grid: Grid,
    output_grid: Grid
) -> bool
```

**Parameters**:
- `input_grid`: Input grid
- `output_grid`: Output grid

**Returns**: True if colors are conserved

**Example**:
```python
input_grid = np.array([[0, 1, 2], [1, 2, 0]])
output_grid = np.array([[2, 0, 1], [0, 1, 2]])

is_conserved = checker.check_color_conservation(input_grid, output_grid)
print(f"Colors conserved: {is_conserved}")
```

#### check_object_count()

```python
def check_object_count(
    self,
    input_grid: Grid,
    output_grid: Grid,
    tolerance: int = 0
) -> bool
```

**Parameters**:
- `input_grid`: Input grid
- `output_grid`: Output grid
- `tolerance`: Allowed difference in object count

**Returns**: True if object counts match within tolerance

**Example**:
```python
is_valid = checker.check_object_count(
    input_grid,
    output_grid,
    tolerance=1
)
```

#### check_topology()

```python
def check_topology(
    self,
    input_grid: Grid,
    output_grid: Grid
) -> bool
```

**Parameters**:
- `input_grid`: Input grid
- `output_grid`: Output grid

**Returns**: True if topological features are preserved

**Example**:
```python
# Check if connectivity is preserved
is_valid = checker.check_topology(input_grid, output_grid)
```

### CounterexampleMinimizer

Minimizes counterexamples using delta debugging.

```python
from arc.symbolic.verification import CounterexampleMinimizer

minimizer = CounterexampleMinimizer(config)
minimal = minimizer.minimize(program, counterexample)
```

#### minimize()

```python
def minimize(
    self,
    program: Program,
    counterexample: Counterexample
) -> Counterexample
```

**Parameters**:
- `program`: Program that fails on counterexample
- `counterexample`: Counterexample to minimize

**Returns**: Minimized counterexample

**Example**:
```python
# Original counterexample: 10x10 grid
counterexample = Counterexample(
    input_grid=large_grid,
    expected_output=expected,
    actual_output=actual
)

# Minimize to smallest failing case
minimal = minimizer.minimize(program, counterexample)

print(f"Original size: {counterexample.input_grid.shape}")
print(f"Minimal size: {minimal.input_grid.shape}")
```

#### shrink_grid()

```python
def shrink_grid(
    self,
    grid: Grid,
    preserve_failure: Callable[[Grid], bool]
) -> Grid
```

**Parameters**:
- `grid`: Grid to shrink
- `preserve_failure`: Function that returns True if grid still causes failure

**Returns**: Shrunk grid

**Example**:
```python
def still_fails(grid):
    output = program.execute(grid)
    return not np.array_equal(output, expected_output)

shrunk = minimizer.shrink_grid(large_grid, still_fails)
```

### ConstraintBasedRepairer

Repairs programs using constraint solving.

```python
from arc.symbolic.verification import ConstraintBasedRepairer

repairer = ConstraintBasedRepairer(config)
repaired = repairer.repair_program(program, failed_examples, passed_examples)
```

#### repair_program()

```python
def repair_program(
    self,
    program: Program,
    failed_examples: List[Example],
    passed_examples: List[Example]
) -> List[Program]
```

**Parameters**:
- `program`: Program to repair
- `failed_examples`: Examples where program fails
- `passed_examples`: Examples where program succeeds

**Returns**: List of repaired program variants

**Example**:
```python
# Program works on 2/3 examples
passed = task["train"][:2]
failed = task["train"][2:]

repaired_variants = repairer.repair_program(program, failed, passed)

# Verify repaired programs
for variant in repaired_variants:
    result = verifier.verify_batch([(variant, task["train"])])
    if result[0].status == "sat":
        print(f"Repair successful: {variant.to_dsl_string()}")
```

#### compute_minimal_edit()

```python
def compute_minimal_edit(
    self,
    program: Program,
    target_behavior: Dict[Example, Grid]
) -> Optional[ProgramEdit]
```

**Parameters**:
- `program`: Program to edit
- `target_behavior`: Desired behavior on examples

**Returns**: Minimal edit to achieve target behavior, or None

**Example**:
```python
target = {
    example1: expected_output1,
    example2: expected_output2
}

edit = repairer.compute_minimal_edit(program, target)

if edit:
    repaired = repairer.apply_edit(program, edit)
```

## Data Structures

### VerificationResult

```python
@dataclass
class VerificationResult:
    program_id: str
    status: str  # "sat", "unsat", "unknown", "timeout"
    verification_time: float
    model: Optional[Dict[str, Any]]
    unsat_core: Optional[List[str]]
    metadata: Dict[str, Any]
```

### SMTConstraintSet

```python
@dataclass
class SMTConstraintSet:
    variables: Dict[str, SMTVariable]
    constraints: List[SMTConstraint]
    assertions: List[SMTAssertion]
    metadata: Dict[str, Any]
```

### Counterexample

```python
@dataclass
class Counterexample:
    input_grid: Grid
    expected_output: Grid
    actual_output: Grid
    minimal: bool
    metadata: Dict[str, Any]
```

### ProgramEdit

```python
@dataclass
class ProgramEdit:
    edit_type: str  # "insert", "delete", "replace", "reorder"
    location: int  # Stage index
    content: Optional[Stage]
    cost: float
```

## Usage Patterns

### Basic Verification

```python
from arc.symbolic.smt import BatchVerifier

verifier = BatchVerifier(config)

# Verify single program
result = verifier.verify_batch(
    [(program, task["train"])],
    timeout_per_candidate=2.0
)[0]

if result.status == "sat":
    print("Program verified!")
elif result.status == "unsat":
    print("Program is incorrect")
    print(f"Unsat core: {result.unsat_core}")
```

### Witness-Guided Synthesis

```python
from arc.symbolic.smt import WitnessFunctionGenerator
from arc.symbolic.ir import ProgramSketch

# Generate sketch
sketch = generate_sketch(task)

# Generate witnesses
generator = WitnessFunctionGenerator(config)
witnesses = generator.generate_witness(sketch, task["train"])

# Constrain holes with witnesses
for hole_id, valid_values in witnesses.items():
    hole = sketch.get_hole(hole_id)
    hole.domain = hole.domain.intersection(valid_values)

# Synthesize with constrained sketch
candidates = synthesizer.synthesize_from_sketch(sketch, task["train"])
```

### Invariant-Based Filtering

```python
from arc.symbolic.verification import InvariantChecker

checker = InvariantChecker(config)

# Filter candidates by invariants
valid_candidates = []
for candidate in candidates:
    if checker.check_all_invariants(candidate, task["train"]):
        valid_candidates.append(candidate)

print(f"Filtered {len(candidates)} -> {len(valid_candidates)} candidates")
```

### Program Repair

```python
from arc.symbolic.verification import ConstraintBasedRepairer

repairer = ConstraintBasedRepairer(config)

# Identify failed examples
failed = [ex for ex in task["train"] if not program.execute(ex.input) == ex.output]
passed = [ex for ex in task["train"] if program.execute(ex.input) == ex.output]

# Repair program
if failed and passed:
    repaired_variants = repairer.repair_program(program, failed, passed)
    
    # Verify repairs
    for variant in repaired_variants:
        result = verifier.verify_batch([(variant, task["train"])])[0]
        if result.status == "sat":
            print(f"Successfully repaired program")
            break
```

### Counterexample Minimization

```python
from arc.symbolic.verification import CounterexampleMinimizer

minimizer = CounterexampleMinimizer(config)

# Program fails on large grid
large_counterexample = Counterexample(
    input_grid=np.random.randint(0, 10, (30, 30)),
    expected_output=expected,
    actual_output=program.execute(large_grid)
)

# Minimize
minimal = minimizer.minimize(program, large_counterexample)

print(f"Reduced from {large_counterexample.input_grid.shape} to {minimal.input_grid.shape}")

# Use minimal counterexample for debugging
debug_program(program, minimal)
```

## Integration with CEGIS

```python
from arc.symbolic.verification import CEGISCoordinator

cegis = CEGISCoordinator(config)

# CEGIS automatically uses verifier and counterexample generation
result = cegis.run_cegis_loop(task, max_iterations=10)

if result.success:
    print(f"Synthesized in {result.iterations} iterations")
    print(f"Encountered {len(result.counterexamples)} counterexamples")
    
    # Counterexamples are automatically minimized
    for ce in result.counterexamples:
        print(f"  Counterexample: {ce.input_grid.shape}, minimal={ce.minimal}")
```

## Performance Optimization

### Parallel Verification

```python
config["smt"]["parallel"] = True
config["smt"]["num_workers"] = 4

verifier = BatchVerifier(config)

# Automatically parallelizes verification
results = verifier.verify_batch(large_candidate_list)
```

### Result Caching

```python
config["smt"]["cache_results"] = True
config["smt"]["cache_size"] = 10000

# Repeated verifications are cached
result1 = verifier.verify_batch([(program, examples)])
result2 = verifier.verify_batch([(program, examples)])  # Cache hit
```

### Incremental Solving

```python
# Reuse solver context for efficiency
context = verifier.create_context()

for program in candidates:
    result = verifier.verify_incremental(program, examples, context)
    if result.status == "sat":
        verified.append(program)
```

## Error Handling

```python
from arc.symbolic.exceptions import VerificationError, SMTTimeoutError

try:
    result = verifier.verify_batch(candidates)
except SMTTimeoutError as e:
    print(f"Verification timed out: {e}")
    # Use partial results
    partial_results = e.partial_results
except VerificationError as e:
    print(f"Verification error: {e}")
```

## References

- Implementation: `arc/symbolic/smt/`, `arc/symbolic/verification/`
- Tests: `tests/symbolic/test_smt.py`, `tests/symbolic/test_verification.py`
- Examples: `arc/symbolic/smt/README.md`
- Related: symbolic_synthesizer.md, ../symbolic/rewrite_rules.md
