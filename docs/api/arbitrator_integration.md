# Arbitrator Integration API Documentation

## Overview

The Arbitrator Integration API defines how the symbolic synthesis module interfaces with the arbitration core. This document covers candidate submission, scoring, and feedback mechanisms.

## Integration Architecture

```
Symbolic Solver
      ↓
  Candidate Programs
      ↓
  Arbitrator API
      ↓
  Arbitration Core
      ↓
  Final Selection
```

## Core Interfaces

### CandidateSubmission

Submit candidate programs to the arbitrator.

```python
from arc.symbolic import SymbolicSolver
from arc.arbitration import Arbitrator

solver = SymbolicSolver(config)
arbitrator = Arbitrator(config)

# Solve task
result = solver.solve(task)

# Submit candidates to arbitrator
for candidate in result.candidates:
    arbitrator.submit_candidate(
        task_id=task["task_id"],
        module="symbolic",
        candidate=candidate,
        confidence=candidate.score,
        metadata=candidate.metadata
    )
```

#### submit_candidate()

```python
def submit_candidate(
    self,
    task_id: str,
    module: str,
    candidate: CandidateProgram,
    confidence: float,
    metadata: Dict[str, Any]
) -> str
```

**Parameters**:
- `task_id`: Task identifier
- `module`: Source module ("symbolic", "ttt", "llm")
- `candidate`: Candidate program
- `confidence`: Confidence score [0, 1]
- `metadata`: Additional metadata

**Returns**: Candidate ID

**Example**:
```python
candidate_id = arbitrator.submit_candidate(
    task_id="task_001",
    module="symbolic",
    candidate=program,
    confidence=0.85,
    metadata={
        "search_depth": 8,
        "egraph_optimized": True,
        "smt_verified": True,
        "synthesis_time": 45.2
    }
)
```

### CandidateProgram

Data structure for candidate programs.

```python
@dataclass
class CandidateProgram:
    node_id: int
    program: Program
    score: float
    cost: float
    solved_examples: int
    total_examples: int
    verification_passed: bool
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for arbitrator."""
        return {
            "program": self.program.to_dsl_string(),
            "score": self.score,
            "cost": self.cost,
            "accuracy": self.solved_examples / self.total_examples,
            "verified": self.verification_passed,
            "metadata": self.metadata
        }
```

### Scoring Integration

The arbitrator uses module-specific scoring functions.

```python
class SymbolicScoringAdapter:
    """Adapter for symbolic module scoring in arbitrator."""
    
    def score_candidate(
        self,
        candidate: CandidateProgram,
        task: Task,
        module_reliability: float
    ) -> float:
        """
        Score symbolic candidate for arbitration.
        
        Returns: Final score [0, 1]
        """
        # Base score from synthesis
        base_score = candidate.score
        
        # Boost for e-graph optimization
        if candidate.metadata.get("egraph_optimized"):
            base_score *= 1.1
        
        # Boost for SMT verification
        if candidate.metadata.get("smt_verified"):
            base_score *= 1.2
        
        # Penalty for high cost
        cost_penalty = candidate.cost * 0.01
        
        # Module reliability factor
        reliability_factor = module_reliability
        
        final_score = (base_score - cost_penalty) * reliability_factor
        
        return min(1.0, max(0.0, final_score))
```

## Metadata Fields

### Required Fields

- `module`: "symbolic"
- `program`: DSL program string
- `confidence`: Confidence score [0, 1]
- `synthesis_time`: Time taken to synthesize (seconds)

### Optional Fields

- `search_depth`: Search depth reached
- `search_strategy`: Strategy used ("beam", "mcts", etc.)
- `egraph_optimized`: Whether e-graph optimization was applied
- `smt_verified`: Whether SMT verification passed
- `cegis_iterations`: Number of CEGIS iterations
- `counterexamples_encountered`: Number of counterexamples
- `library_fragments_used`: Number of library fragments used
- `rewrite_rules_applied`: Number of rewrite rules applied
- `sketch_guided`: Whether sketch-guided synthesis was used
- `witness_functions_used`: Whether witness functions were used

### Example Metadata

```python
metadata = {
    "module": "symbolic",
    "synthesis_time": 45.2,
    "search_depth": 8,
    "search_strategy": "beam",
    "beam_width": 100,
    "egraph_optimized": True,
    "smt_verified": True,
    "cegis_iterations": 3,
    "counterexamples_encountered": 2,
    "library_fragments_used": 5,
    "rewrite_rules_applied": 12,
    "sketch_guided": True,
    "witness_functions_used": True,
    "program_length": 4,
    "program_complexity": 6.5,
    "cost": 8.2
}
```

## Feedback Mechanism

### Receiving Feedback

The arbitrator provides feedback on candidate performance.

```python
class SymbolicSolver:
    def receive_arbitrator_feedback(
        self,
        task_id: str,
        candidate_id: str,
        feedback: Dict[str, Any]
    ) -> None:
        """
        Receive feedback from arbitrator.
        
        Feedback includes:
        - selected: Whether candidate was selected
        - rank: Rank among all candidates
        - execution_result: Result of executing on test cases
        - failure_reason: Reason for failure (if any)
        """
        if feedback["selected"]:
            # Update library with successful program
            self.library_manager.add_success(
                task_id,
                candidate_id,
                feedback
            )
        else:
            # Learn from failure
            self.learn_from_failure(
                task_id,
                candidate_id,
                feedback["failure_reason"]
            )
```

### Feedback Structure

```python
@dataclass
class ArbitratorFeedback:
    task_id: str
    candidate_id: str
    selected: bool
    rank: int
    total_candidates: int
    execution_result: Optional[Dict[str, Any]]
    failure_reason: Optional[str]
    metadata: Dict[str, Any]
```

## Multi-Module Coordination

### Receiving Inputs from Other Modules

```python
class SymbolicSolver:
    def receive_ttt_invariants(
        self,
        task_id: str,
        invariants: List[Invariant]
    ) -> None:
        """Receive invariants from TTT module."""
        self.ttt_coordinator.receive_invariants(task_id, invariants)
        
    def receive_llm_sketch(
        self,
        task_id: str,
        sketch: ProgramSketch
    ) -> None:
        """Receive sketch from LLM module."""
        self.llm_coordinator.receive_sketch(task_id, sketch)
```

### Sending Feedback to Other Modules

```python
class SymbolicSolver:
    def send_failure_feedback(
        self,
        task_id: str,
        failure_type: str,
        metadata: Dict[str, Any]
    ) -> None:
        """Send failure feedback to other modules."""
        # To TTT
        self.ttt_coordinator.send_failure_feedback(
            task_id,
            failure_type,
            metadata
        )
        
        # To LLM
        self.llm_coordinator.send_failure_feedback(
            task_id,
            failure_type,
            metadata
        )
```

## Usage Patterns

### Basic Integration

```python
from arc.symbolic import SymbolicSolver
from arc.arbitration import Arbitrator

# Initialize
solver = SymbolicSolver(config)
arbitrator = Arbitrator(config)

# Solve task
result = solver.solve(task)

# Submit all candidates
for candidate in result.candidates:
    arbitrator.submit_candidate(
        task_id=task["task_id"],
        module="symbolic",
        candidate=candidate,
        confidence=candidate.score,
        metadata=candidate.metadata
    )

# Arbitrator selects best candidates
final_answers = arbitrator.select_answers(task["task_id"], k=2)
```

### With Module Coordination

```python
# Receive inputs from other modules
ttt_invariants = ttt_module.get_invariants(task_id)
llm_sketch = llm_module.get_sketch(task_id)

solver.receive_ttt_invariants(task_id, ttt_invariants)
solver.receive_llm_sketch(task_id, llm_sketch)

# Solve with additional constraints
result = solver.solve(task)

# Submit candidates
for candidate in result.candidates:
    # Add coordination metadata
    candidate.metadata["used_ttt_invariants"] = len(ttt_invariants)
    candidate.metadata["used_llm_sketch"] = llm_sketch is not None
    
    arbitrator.submit_candidate(
        task_id=task_id,
        module="symbolic",
        candidate=candidate,
        confidence=candidate.score,
        metadata=candidate.metadata
    )
```

### With Feedback Loop

```python
# Solve task
result = solver.solve(task)

# Submit candidates
candidate_ids = []
for candidate in result.candidates:
    cid = arbitrator.submit_candidate(
        task_id=task_id,
        module="symbolic",
        candidate=candidate,
        confidence=candidate.score,
        metadata=candidate.metadata
    )
    candidate_ids.append(cid)

# Get feedback
for cid in candidate_ids:
    feedback = arbitrator.get_feedback(task_id, cid)
    solver.receive_arbitrator_feedback(task_id, cid, feedback)
```

## Scoring Factors

### Factors Considered by Arbitrator

1. **Module Reliability**: Historical success rate of symbolic module
2. **Candidate Confidence**: Confidence score from synthesis
3. **Verification Status**: Whether SMT verification passed
4. **Program Complexity**: Simpler programs preferred
5. **Synthesis Time**: Faster synthesis slightly preferred
6. **Optimization Level**: E-graph optimization boosts score
7. **CEGIS Iterations**: Fewer iterations preferred
8. **Library Usage**: Using proven fragments boosts score

### Scoring Formula

```python
def compute_arbitrator_score(candidate, module_reliability):
    """
    Compute final arbitrator score.
    """
    # Base confidence
    score = candidate.confidence
    
    # Module reliability (0.7 - 0.95 typically)
    score *= module_reliability
    
    # Verification bonus (+20%)
    if candidate.metadata.get("smt_verified"):
        score *= 1.2
    
    # E-graph optimization bonus (+10%)
    if candidate.metadata.get("egraph_optimized"):
        score *= 1.1
    
    # Complexity penalty
    complexity = candidate.metadata.get("program_complexity", 0)
    score *= (1.0 - 0.01 * complexity)
    
    # CEGIS efficiency bonus
    cegis_iters = candidate.metadata.get("cegis_iterations", 0)
    if cegis_iters > 0:
        score *= (1.0 + 0.05 * (10 - cegis_iters))
    
    # Library usage bonus
    fragments_used = candidate.metadata.get("library_fragments_used", 0)
    score *= (1.0 + 0.02 * fragments_used)
    
    return min(1.0, max(0.0, score))
```

## Configuration

```yaml
arbitration:
  symbolic:
    enabled: true
    base_reliability: 0.85
    max_candidates: 10
    min_confidence: 0.5
    
    scoring:
      verification_bonus: 1.2
      egraph_bonus: 1.1
      complexity_penalty: 0.01
      cegis_efficiency_bonus: 0.05
      library_usage_bonus: 0.02
      
    feedback:
      enabled: true
      update_library: true
      learn_from_failures: true
```

## Best Practices

1. **Submit Top Candidates Only**: Limit to top 10 candidates by confidence
2. **Include Rich Metadata**: More metadata helps arbitrator make better decisions
3. **Verify Before Submission**: Run SMT verification when possible
4. **Optimize Programs**: Apply e-graph optimization before submission
5. **Use Feedback**: Learn from arbitrator feedback to improve future synthesis
6. **Coordinate with Other Modules**: Use invariants and sketches from TTT/LLM
7. **Monitor Reliability**: Track symbolic module's success rate over time

## Example: Complete Integration

```python
from arc.symbolic import SymbolicSolver
from arc.arbitration import Arbitrator
from arc.symbolic.coordination import TTTCoordinator, LLMCoordinator

# Initialize components
solver = SymbolicSolver(config)
arbitrator = Arbitrator(config)
ttt_coordinator = TTTCoordinator(config)
llm_coordinator = LLMCoordinator(config)

# Solve task with coordination
def solve_with_arbitration(task):
    task_id = task["task_id"]
    
    # Receive inputs from other modules
    invariants = ttt_coordinator.get_invariants(task_id)
    sketch = llm_coordinator.get_sketch(task_id)
    
    if invariants:
        solver.receive_ttt_invariants(task_id, invariants)
    if sketch:
        solver.receive_llm_sketch(task_id, sketch)
    
    # Synthesize candidates
    result = solver.solve(task)
    
    # Submit to arbitrator
    candidate_ids = []
    for candidate in result.candidates[:10]:  # Top 10
        # Verify if not already verified
        if not candidate.metadata.get("smt_verified"):
            from arc.symbolic.smt import BatchVerifier
            verifier = BatchVerifier(config)
            vresult = verifier.verify_batch([(candidate.program, task["train"])])[0]
            candidate.metadata["smt_verified"] = (vresult.status == "sat")
        
        # Submit
        cid = arbitrator.submit_candidate(
            task_id=task_id,
            module="symbolic",
            candidate=candidate,
            confidence=candidate.score,
            metadata=candidate.metadata
        )
        candidate_ids.append(cid)
    
    # Get final selection
    final_answers = arbitrator.select_answers(task_id, k=2)
    
    # Receive feedback
    for cid in candidate_ids:
        feedback = arbitrator.get_feedback(task_id, cid)
        solver.receive_arbitrator_feedback(task_id, cid, feedback)
    
    return final_answers

# Use it
answers = solve_with_arbitration(task)
```

## References

- Implementation: `arc/symbolic/solver.py`, `arc/arbitration/`
- Tests: `tests/arbitration/test_symbolic_integration.py`
- Related: symbolic_synthesizer.md, ARBITRATOR_RULES.md
