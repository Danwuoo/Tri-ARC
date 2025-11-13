# Symbolic Synthesizer API Documentation

## Overview

The Symbolic Synthesizer API provides interfaces for program synthesis, verification, and optimization. This document covers the main entry points and usage patterns.

## Core Classes

### SymbolicSolver

Main entry point for symbolic program synthesis.

```python
from arc.symbolic import SymbolicSolver

solver = SymbolicSolver(config)
result = solver.solve(task)
```

#### Constructor

```python
def __init__(self, config: Dict[str, Any])
```

**Parameters**:
- `config`: Configuration dictionary with solver settings

**Configuration Keys**:
```yaml
symbolic:
  enabled: true
  device: "cuda:0"
  search:
    strategy: "beam"  # "dfs", "iddfs", "beam", "mcts"
    max_depth: 12
    max_expansions: 5000
    beam_width: 100
    soft_timeout_s: 90.0
    hard_timeout_s: 150.0
  egraph:
    enabled: true
    rewrite_limit: 5000
  cegis:
    enabled: true
    max_iterations: 10
```

#### solve()

```python
def solve(self, task: Dict[str, Any]) -> SolverResult
```

**Parameters**:
- `task`: Task dictionary with structure:
  ```python
  {
      "task_id": str,
      "train": List[{"input": Grid, "output": Grid}],
      "test": List[{"input": Grid}]
  }
  ```

**Returns**: `SolverResult` with fields:
- `task_id`: Task identifier
- `status`: "success", "timeout", "failed"
- `candidates`: List of candidate programs
- `best_program`: Best program (if found)
- `telemetry`: Execution metrics
- `summary`: Human-readable summary

**Example**:
```python
task = {
    "task_id": "task_001",
    "train": [
        {"input": np.array([[0, 1], [1, 0]]), 
         "output": np.array([[1, 0], [0, 1]])}
    ],
    "test": [{"input": np.array([[0, 2], [2, 0]])}]
}

result = solver.solve(task)

if result.status == "success":
    print(f"Found program: {result.best_program}")
    print(f"Solve time: {result.telemetry['elapsed_s']:.2f}s")
```

#### synthesize_from_sketch()

```python
def synthesize_from_sketch(
    self,
    sketch: ProgramSketch,
    examples: List[Example],
    budget: SearchBudget
) -> List[Program]
```

**Parameters**:
- `sketch`: Program sketch with holes
- `examples`: Training examples
- `budget`: Search budget constraints

**Returns**: List of candidate programs

**Example**:
```python
from arc.symbolic.ir import ProgramSketch, Hole

sketch = ProgramSketch(
    stages=[
        Stage("rotate", [Hole("angle", {90, 180, 270})]),
        Stage("reflect_h", [])
    ],
    constraints=[]
)

candidates = solver.synthesize_from_sketch(
    sketch,
    task["train"],
    SearchBudget(max_depth=5, soft_timeout_s=30.0)
)
```

### CEGISCoordinator

Counter-Example Guided Inductive Synthesis coordinator.

```python
from arc.symbolic.verification import CEGISCoordinator

cegis = CEGISCoordinator(config)
result = cegis.run_cegis_loop(task, max_iterations=10)
```

#### run_cegis_loop()

```python
def run_cegis_loop(
    self,
    task: Task,
    max_iterations: int = 10,
    initial_examples: Optional[List[Example]] = None
) -> CEGISResult
```

**Parameters**:
- `task`: Task to solve
- `max_iterations`: Maximum CEGIS iterations
- `initial_examples`: Initial training examples (defaults to task.train)

**Returns**: `CEGISResult` with fields:
- `success`: Whether synthesis succeeded
- `program`: Synthesized program (if successful)
- `iterations`: Number of CEGIS iterations
- `counterexamples`: List of counterexamples found
- `verification_time`: Total verification time

**Example**:
```python
result = cegis.run_cegis_loop(task, max_iterations=10)

if result.success:
    print(f"Synthesized in {result.iterations} iterations")
    print(f"Program: {result.program}")
else:
    print(f"Failed after {result.iterations} iterations")
    print(f"Counterexamples: {len(result.counterexamples)}")
```

### SaturationEngine

E-graph saturation engine for program optimization.

```python
from arc.symbolic.egraph import SaturationEngine

engine = SaturationEngine(config)
result = engine.saturate(programs, rules)
```

#### saturate()

```python
def saturate(
    self,
    initial_programs: List[Program],
    rules: List[RewriteRule],
    max_iterations: int = 100,
    saturation_limit: int = 10000
) -> SaturationResult
```

**Parameters**:
- `initial_programs`: Starting programs
- `rules`: Rewrite rules to apply
- `max_iterations`: Maximum saturation iterations
- `saturation_limit`: Maximum e-graph size

**Returns**: `SaturationResult` with fields:
- `iterations`: Number of iterations performed
- `rewrites_applied`: Total rewrites applied
- `unique_programs`: Number of unique programs in e-graph
- `best_cost`: Cost of best program
- `egraph`: Final e-graph
- `history`: Rewrite history

**Example**:
```python
from arc.symbolic.egraph import load_default_rules

rules = load_default_rules()
result = engine.saturate(
    initial_programs=[candidate_program],
    rules=rules,
    max_iterations=50
)

print(f"Applied {result.rewrites_applied} rewrites")
print(f"Found {result.unique_programs} unique programs")

# Extract best program
best = engine.extract_best(result.egraph, cost_fn)
```

#### extract_best()

```python
def extract_best(
    self,
    egraph: EGraph,
    cost_fn: Callable[[Program], float],
    method: str = "ilp"
) -> Program
```

**Parameters**:
- `egraph`: E-graph to extract from
- `cost_fn`: Cost function for programs
- `method`: Extraction method ("ilp", "cp_sat", "astar")

**Returns**: Minimum-cost program

**Example**:
```python
def my_cost_fn(program):
    return len(program.stages) + 0.5 * complexity(program)

best_program = engine.extract_best(
    result.egraph,
    cost_fn=my_cost_fn,
    method="ilp"
)
```

### FragmentMiner

Mines reusable program fragments.

```python
from arc.symbolic.library import FragmentMiner

miner = FragmentMiner(config)
fragments = miner.mine_fragments(successful_programs)
```

#### mine_fragments()

```python
def mine_fragments(
    self,
    successful_programs: List[Program],
    min_frequency: int = 2
) -> List[ProgramFragment]
```

**Parameters**:
- `successful_programs`: Programs to mine from
- `min_frequency`: Minimum occurrence count

**Returns**: List of `ProgramFragment` objects

**Example**:
```python
# After solving multiple tasks
successful_programs = [result.best_program for result in results if result.status == "success"]

fragments = miner.mine_fragments(
    successful_programs,
    min_frequency=3
)

for fragment in fragments:
    print(f"Fragment {fragment.id}: frequency={fragment.frequency}, utility={fragment.utility}")
```

#### anti_unify()

```python
def anti_unify(
    self,
    program_a: Program,
    program_b: Program
) -> Optional[ProgramTemplate]
```

**Parameters**:
- `program_a`: First program
- `program_b`: Second program

**Returns**: Most general common generalization, or None if programs are too different

**Example**:
```python
p1 = Program([Stage("rotate", [90]), Stage("paint_region", [1])])
p2 = Program([Stage("rotate", [180]), Stage("paint_region", [2])])

template = miner.anti_unify(p1, p2)
# Result: Program([Stage("rotate", [?angle]), Stage("paint_region", [?color])])
```

### BatchVerifier

Batch verification using SMT solver.

```python
from arc.symbolic.smt import BatchVerifier

verifier = BatchVerifier(config)
results = verifier.verify_batch(candidates)
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
- `candidates`: List of (program, examples) tuples
- `timeout_per_candidate`: Timeout per verification

**Returns**: List of `VerificationResult` objects

**Example**:
```python
candidates = [
    (program1, task["train"]),
    (program2, task["train"]),
    (program3, task["train"])
]

results = verifier.verify_batch(
    candidates,
    timeout_per_candidate=2.0
)

for i, result in enumerate(results):
    if result.status == "sat":
        print(f"Program {i} verified successfully")
    elif result.status == "unsat":
        print(f"Program {i} is incorrect")
    elif result.status == "timeout":
        print(f"Program {i} verification timed out")
```

## Data Structures

### Program

```python
@dataclass
class Program:
    stages: List[Stage]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dsl_string(self) -> str:
        """Convert to DSL string representation."""
        
    def execute(self, input_grid: Grid) -> Grid:
        """Execute program on input grid."""
```

### Stage

```python
@dataclass
class Stage:
    operator: str
    arguments: List[Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### SolverResult

```python
@dataclass
class SolverResult:
    task_id: str
    status: str  # "success", "timeout", "failed"
    candidates: List[CandidateProgram]
    best_program: Optional[Program]
    telemetry: Dict[str, Any]
    summary: str
```

### SearchBudget

```python
@dataclass
class SearchBudget:
    max_depth: int
    max_expansions: int
    max_nodes: Optional[int]
    soft_timeout_s: float
    hard_timeout_s: float
    beam_width: Optional[int] = None
```

## Usage Patterns

### Basic Synthesis

```python
from arc.symbolic import SymbolicSolver

# Initialize solver
solver = SymbolicSolver(config)

# Solve task
result = solver.solve(task)

# Check result
if result.status == "success":
    program = result.best_program
    print(f"Found solution: {program.to_dsl_string()}")
    
    # Execute on test input
    test_output = program.execute(task["test"][0]["input"])
```

### Sketch-Guided Synthesis

```python
from arc.symbolic.ir import ObjectGraphToDSLMapper

# Generate sketch from examples
mapper = ObjectGraphToDSLMapper()
input_graph = mapper.map_grid_to_objects(task["train"][0]["input"])
output_graph = mapper.map_grid_to_objects(task["train"][0]["output"])
sketch = mapper.generate_sketch(input_graph, output_graph)

# Synthesize from sketch
candidates = solver.synthesize_from_sketch(
    sketch,
    task["train"],
    SearchBudget(max_depth=8, soft_timeout_s=60.0)
)

# Verify candidates
from arc.symbolic.smt import BatchVerifier
verifier = BatchVerifier(config)
verified = verifier.verify_batch([(c, task["train"]) for c in candidates])
```

### E-graph Optimization

```python
from arc.symbolic.egraph import SaturationEngine, load_default_rules

# Create engine
engine = SaturationEngine(config)

# Load rules
rules = load_default_rules()

# Saturate
result = engine.saturate(
    initial_programs=[candidate],
    rules=rules,
    max_iterations=50
)

# Extract optimized program
optimized = engine.extract_best(result.egraph, cost_fn)
```

### Library Management

```python
from arc.symbolic.library import FragmentMiner, LibraryCurator

# Mine fragments from successful programs
miner = FragmentMiner(config)
fragments = miner.mine_fragments(successful_programs, min_frequency=2)

# Add to library
curator = LibraryCurator(config)
for fragment in fragments:
    curator.add_fragment(fragment)

# Periodic pruning
curator.prune_library(usage_threshold=0.01, impact_threshold=0.05)
```

### CEGIS Loop

```python
from arc.symbolic.verification import CEGISCoordinator

# Initialize CEGIS
cegis = CEGISCoordinator(config)

# Run synthesis loop
result = cegis.run_cegis_loop(task, max_iterations=10)

if result.success:
    print(f"Synthesized program in {result.iterations} iterations")
    print(f"Program: {result.program.to_dsl_string()}")
    print(f"Counterexamples encountered: {len(result.counterexamples)}")
```

## Error Handling

### Common Exceptions

```python
from arc.symbolic.exceptions import (
    SynthesisError,
    VerificationError,
    TimeoutError,
    InvalidProgramError
)

try:
    result = solver.solve(task)
except TimeoutError as e:
    print(f"Synthesis timed out: {e}")
except SynthesisError as e:
    print(f"Synthesis failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Graceful Degradation

```python
# Configure fallback behavior
config = {
    "symbolic": {
        "fallback_on_timeout": True,
        "return_partial_results": True,
        "max_retries": 3
    }
}

solver = SymbolicSolver(config)
result = solver.solve(task)

# Check if partial result
if result.status == "partial":
    print(f"Partial solution with {len(result.candidates)} candidates")
```

## Performance Tips

1. **Use Beam Search for Large Search Spaces**:
   ```python
   config["symbolic"]["search"]["strategy"] = "beam"
   config["symbolic"]["search"]["beam_width"] = 100
   ```

2. **Enable E-graph for Optimization**:
   ```python
   config["symbolic"]["egraph"]["enabled"] = True
   config["symbolic"]["egraph"]["rewrite_limit"] = 5000
   ```

3. **Adjust Timeouts Based on Task Complexity**:
   ```python
   if task_complexity > 0.7:
       config["symbolic"]["search"]["soft_timeout_s"] = 120.0
   ```

4. **Use Caching for Repeated Synthesis**:
   ```python
   config["symbolic"]["cache"]["enabled"] = True
   config["symbolic"]["cache"]["max_size"] = 10000
   ```

5. **Batch Verification for Multiple Candidates**:
   ```python
   # More efficient than individual verification
   results = verifier.verify_batch(candidates, timeout_per_candidate=2.0)
   ```

## References

- Implementation: `arc/symbolic/solver.py`
- Tests: `tests/symbolic/test_solver.py`
- Examples: `arc/symbolic/engineering/integration_example.py`
- Related: symbolic_verifier.md, arbitrator_integration.md
