# CEGIS and Verification Infrastructure

This module implements Counter-Example Guided Inductive Synthesis (CEGIS) and related verification infrastructure for the symbolic program synthesis module.

## Overview

The verification infrastructure provides:

1. **CEGIS Loop**: Iterative synthesis with counterexample-guided refinement
2. **Counterexample Minimization**: Delta debugging to produce minimal failing examples
3. **Invariant Checking**: Hard constraints on program behavior
4. **Program Repair**: Constraint-based repair for partially failing programs
5. **Multi-Solution Arbitration**: Ranking and selection among multiple candidates

## Components

### CEGISCoordinator

The main coordinator for the CEGIS loop. It orchestrates:
- Candidate program generation from examples and counterexamples
- Program verification against all examples
- Counterexample generation and minimization
- Iterative refinement until success or max iterations

**Usage:**

```python
from arc.symbolic.verification import CEGISCoordinator, Example
from arc.symbolic.dsl.types import Grid

# Create examples
examples = [
    Example(
        input_grid=Grid.from_list([[0, 1], [1, 0]]),
        output_grid=Grid.from_list([[1, 0], [0, 1]]),
    )
]

# Initialize coordinator
config = {"cegis": {"max_iterations": 10}}
coordinator = CEGISCoordinator(
    config,
    synthesizer=my_synthesizer,
    verifier=my_verifier,
)

# Run CEGIS loop
result = coordinator.run_cegis_loop(examples)

if result.success:
    print(f"Synthesized program: {result.program}")
else:
    print(f"Failed after {result.iterations} iterations")
```

### CounterexampleMinimizer

Minimizes counterexamples using delta debugging techniques. This produces smaller, more focused counterexamples that lead to better refinement.

**Features:**
- Row and column removal
- Color simplification
- Preserves failure property during minimization

**Usage:**

```python
from arc.symbolic.verification import CounterexampleMinimizer, Counterexample

config = {"counterexample_minimizer": {"max_iterations": 10}}
minimizer = CounterexampleMinimizer(config, verifier=my_verifier)

# Minimize a counterexample
minimized = minimizer.minimize(program, counterexample)
print(f"Original shape: {counterexample.input_grid.shape}")
print(f"Minimized shape: {minimized.input_grid.shape}")
```

### InvariantChecker

Checks various invariants on grid transformations. Invariants can be used as hard constraints to prune invalid candidates early.

**Supported Invariants:**
- **Color Conservation**: Output colors are subset of input colors
- **Object Count**: Number of connected components preserved (with tolerance)
- **Topology**: Structural features preserved

**Usage:**

```python
from arc.symbolic.verification import InvariantChecker
from arc.symbolic.dsl.types import Grid

config = {"invariants": {"enabled": ["color_conservation", "object_count"]}}
checker = InvariantChecker(config)

input_grid = Grid.from_list([[0, 1, 2], [1, 2, 0]])
output_grid = Grid.from_list([[1, 2], [0, 1]])

# Check all enabled invariants
results = checker.check_all_invariants(input_grid, output_grid)
print(results)  # {"color_conservation": True, "object_count": True}
```

### ConstraintBasedRepairer

Repairs programs that fail on some examples using constraint-based search. Attempts to find minimal edits that make the program pass all examples.

**Repair Strategies:**
- Single-stage replacement
- Stage insertion
- Stage deletion
- Stage reordering

**Usage:**

```python
from arc.symbolic.verification import ConstraintBasedRepairer

config = {"repair": {"max_repairs": 5, "allow_insert": True}}
repairer = ConstraintBasedRepairer(config, verifier=my_verifier)

# Attempt repair
repaired_programs = repairer.repair_program(
    program,
    failed_examples,
    passed_examples,
)

for repaired in repaired_programs:
    print(f"Repaired program: {repaired}")
```

### MultiSolutionArbitrator

Arbitrates among multiple candidate solutions, ranking them by quality and diversity.

**Scoring Criteria:**
- Correctness (passes all examples)
- Simplicity (shorter programs preferred)
- Diversity (different from other solutions)

**Usage:**

```python
from arc.symbolic.verification import MultiSolutionArbitrator

config = {"multi_solution_arbitrator": {"diversity_weight": 0.2}}
arbitrator = MultiSolutionArbitrator(config, verifier=my_verifier)

# Rank solutions
ranked = arbitrator.arbitrate_solutions(solutions, examples)

for program, score in ranked:
    print(f"Program: {program}, Score: {score}")
```

## Integration with SymbolicSolver

The CEGIS and verification infrastructure is integrated into the `SymbolicSolver` as an optional enhancement. To enable:

```yaml
symbolic:
  cegis:
    enabled: true
    max_iterations: 10
    minimize_counterexamples: true
  
  invariants:
    enabled:
      - color_conservation
      - object_count
      - topology
    object_count_tolerance: 1
  
  repair:
    max_repairs: 5
    max_edit_distance: 3
    allow_insert: true
    allow_delete: true
    allow_replace: true
```

When enabled, the solver will:
1. Check invariants on failed examples
2. Attempt program repair for partially failing programs
3. Arbitrate among original and repaired solutions
4. Select the best solution based on quality and diversity

## Data Structures

### Counterexample

Represents a counterexample that causes a program to fail.

```python
@dataclass
class Counterexample:
    input_grid: Grid
    expected_output: Grid
    actual_output: Grid
    minimal: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### CEGISResult

Result of a CEGIS synthesis loop.

```python
@dataclass
class CEGISResult:
    success: bool
    program: Optional[Program] = None
    iterations: int = 0
    counterexamples: List[Counterexample] = field(default_factory=list)
    verification_time: float = 0.0
    synthesis_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### ProgramEdit

Represents an edit operation on a program.

```python
@dataclass
class ProgramEdit:
    edit_type: str  # "insert", "delete", "replace", "reorder"
    location: int
    content: Optional[Stage] = None
    cost: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
```

## Configuration

### CEGIS Configuration

```yaml
cegis:
  enabled: true
  max_iterations: 10
  minimize_counterexamples: true
  timeout_per_iteration: 30.0
```

### Counterexample Minimizer Configuration

```yaml
counterexample_minimizer:
  max_iterations: 10
  min_grid_size: 1
```

### Invariant Checker Configuration

```yaml
invariants:
  enabled:
    - color_conservation
    - object_count
    - topology
  object_count_tolerance: 1
  color_tolerance: 0
```

### Program Repairer Configuration

```yaml
repair:
  max_repairs: 5
  max_edit_distance: 3
  allow_insert: true
  allow_delete: true
  allow_replace: true
  allow_reorder: false
```

### Multi-Solution Arbitrator Configuration

```yaml
multi_solution_arbitrator:
  diversity_weight: 0.2
  simplicity_weight: 0.3
  correctness_weight: 0.5
```

## Testing

Run the test suite:

```bash
pytest tests/symbolic/test_cegis_verification.py -v
```

The test suite covers:
- Counterexample creation and serialization
- CEGIS loop convergence and max iterations
- Counterexample minimization (row/column removal)
- Invariant checking (color conservation, object count, topology)
- Program repair (insert, delete, replace edits)
- Multi-solution arbitration

## Performance Considerations

- **Counterexample Minimization**: Can be expensive for large grids. Set `max_iterations` appropriately.
- **Program Repair**: Generates multiple repair candidates. Limit with `max_repairs`.
- **Invariant Checking**: Lightweight checks, safe to enable by default.
- **CEGIS Loop**: Set `max_iterations` based on available time budget.

## Future Enhancements

Potential improvements for future versions:

1. **SMT-based Repair**: Use SMT solvers for more sophisticated repair
2. **Neural Guidance**: Use neural models to guide repair and CEGIS
3. **Parallel Repair**: Generate repair candidates in parallel
4. **Adaptive Minimization**: Adjust minimization strategy based on grid properties
5. **Custom Invariants**: Support user-defined invariants
6. **Incremental Verification**: Cache verification results across iterations

## References

- Solar-Lezama, A. (2008). "Program Synthesis by Sketching"
- Alur, R., et al. (2013). "Syntax-guided synthesis"
- Zeller, A., & Hildebrandt, R. (2002). "Simplifying and Isolating Failure-Inducing Input"
