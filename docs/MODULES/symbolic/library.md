# DSL Library Management System

This module implements automatic DSL library growth through fragment mining, rule learning, and library curation.

## Components

### FragmentMiner (`fragment_miner.py`)
Mines reusable program fragments from successful programs using:
- Frequency analysis to find common subsequences
- Anti-unification to generalize program pairs
- Utility scoring to rank fragments by usefulness

**Key Classes:**
- `ProgramFragment`: Represents a reusable program fragment
- `FragmentScore`: Scoring metrics for fragments
- `FragmentMiner`: Main mining engine

### RuleLearner (`rule_learner.py`)
Learns rewrite rules from equivalence examples:
- Pattern extraction from equivalent program pairs
- Precondition induction from positive/negative examples
- Rule validation on held-out tasks

**Key Classes:**
- `Precondition`: Conditions for rule applicability
- `RuleValidationResult`: Validation metrics
- `RuleLearner`: Main learning engine

### LibraryCurator (`curator.py`)
Manages DSL library versioning, testing, and pruning:
- Primitive addition with versioning
- A/B testing for new rules
- Library pruning based on usage and impact
- Rollback mechanisms for failed rules

**Key Classes:**
- `Primitive`: DSL primitive (operator or macro)
- `ABTestResult`: A/B testing results
- `PruneReport`: Pruning operation report
- `LibraryCurator`: Main curation engine

### LibraryPersistence (`persistence.py`)
Handles library state persistence:
- Save/load library state to/from disk
- Version tracking and changelog management
- Library diff computation
- Library merging from multiple sources

**Key Classes:**
- `LibraryState`: Complete library state
- `LibraryDiff`: Difference between versions
- `LibraryPersistence`: Persistence manager

### LibraryManager (`integration.py`)
Integrates library management with the symbolic solver:
- Fragment mining from successful programs
- Rule learning from equivalence examples
- Automatic library updates
- Periodic pruning

**Key Classes:**
- `LibraryManager`: Main integration coordinator

## Usage

### Basic Usage

```python
from arc.symbolic.library import LibraryManager

# Initialize library manager
manager = LibraryManager(config={
    "library": {
        "fragment_mining": {"enabled": True, "min_frequency": 2},
        "rule_learning": {"enabled": True},
        "pruning": {"enabled": True, "interval": 100}
    }
})

# Hook into solver
from arc.symbolic.library import add_library_hooks_to_solver
add_library_hooks_to_solver(solver, manager)

# After successful solve
manager.on_solve_success(
    task_id="task_001",
    successful_programs=[program1, program2],
    candidates=all_candidates,
    egraph=egraph
)

# Get library statistics
stats = manager.get_library_stats()
print(f"Library version: {stats['version']}")
print(f"Total items: {stats['total_items']}")
```

### Fragment Mining

```python
from arc.symbolic.library import FragmentMiner

miner = FragmentMiner(config={"min_frequency": 2})

# Mine fragments from successful programs
fragments = miner.mine_fragments(successful_programs)

for fragment in fragments:
    print(f"Fragment {fragment.id}: {len(fragment.stages)} stages")
    print(f"  Frequency: {fragment.frequency}")
    print(f"  Utility: {fragment.applicability_score}")
```

### Rule Learning

```python
from arc.symbolic.library import RuleLearner

learner = RuleLearner(config={"validation_threshold": 0.8})

# Learn rules from equivalence examples
equivalence_examples = [
    (program_a1, program_b1),
    (program_a2, program_b2),
]

rules = learner.learn_rules(equivalence_examples)

for rule in rules:
    print(f"Learned rule: {rule.name}")
    print(f"  Description: {rule.description}")
```

### Library Curation

```python
from arc.symbolic.library import LibraryCurator

curator = LibraryCurator(config={
    "usage_threshold": 0.01,
    "impact_threshold": 0.05
})

# Add items to library
curator.add_fragment(fragment)
curator.add_rule(rule)

# Record usage
curator.record_usage("fragment_001", count=5)
curator.record_impact("fragment_001", impact=0.8)

# Prune library
report = curator.prune_library()
print(f"Removed {report.fragments_removed} fragments")
```

## Configuration

The library management system is configured through the `symbolic.library` section:

```yaml
symbolic:
  library:
    fragment_mining:
      enabled: true
      min_frequency: 2
      min_utility: 0.1
      max_fragment_length: 5
    
    rule_learning:
      enabled: true
      validation_threshold: 0.8
      min_examples: 3
      max_preconditions: 5
    
    curation:
      usage_threshold: 0.01
      impact_threshold: 0.05
      ab_test_tasks: 20
      max_versions: 10
    
    pruning:
      enabled: true
      interval: 100
    
    library_dir: "models/symbolic/library"
```

## Testing

Run the test suite:

```bash
pytest tests/symbolic/test_library_management.py -v
```

The test suite covers:
- Fragment mining correctness
- Anti-unification algorithm
- Rule learning and validation
- Library curation and pruning
- Persistence and versioning
- Integration with solver

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   LibraryManager                        │
│  (Coordinates all library management activities)        │
└───────────┬─────────────────────────────────────────────┘
            │
    ┌───────┼───────┬───────────┬──────────────┐
    │       │       │           │              │
    ▼       ▼       ▼           ▼              ▼
┌────────┐ ┌────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
│Fragment│ │Rule│ │Library  │ │Library   │ │Symbolic  │
│Miner   │ │Lrnr│ │Curator  │ │Persist   │ │Solver    │
└────────┘ └────┘ └─────────┘ └──────────┘ └──────────┘
```

## Future Enhancements

- Neural-guided fragment selection
- Cross-task fragment transfer learning
- Automatic macro generation from fragments
- Distributed library synchronization
- Advanced A/B testing with statistical significance
- Rule composition and chaining
