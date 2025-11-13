# Advanced Search Strategies (Phase 7)

This document describes the advanced search strategies implemented for the symbolic synthesis module.

## Overview

Phase 7 implements advanced search strategies to improve program synthesis efficiency and effectiveness. The implementation includes:

1. **Sketch-Guided Synthesis**: Uses program templates with holes to guide search
2. **Abstract Interpretation**: Prunes infeasible candidates early using abstract domains
3. **PCFG-Based Search**: Uses learned probabilities to prioritize likely programs
4. **MCTS Search**: Balances exploration and exploitation using Monte Carlo Tree Search
5. **Diversity Control**: Ensures candidate programs are sufficiently different
6. **Neural Model Interfaces**: Provides interfaces for policy and value models

## Components

### 1. Sketch-Guided Synthesis (`sketch_guided.py`)

**Classes:**
- `SketchGuidedSynthesizer`: Main synthesizer class
- `SketchLibraryEntry`: Entry in the sketch library

**Key Features:**
- Extract sketches from successful programs
- Maintain a library of reusable sketches
- Apply Version Space Algebra (VSA) for hole domain reduction
- Synthesize programs by filling sketch holes

**Usage:**
```python
from arc.symbolic.search import SketchGuidedSynthesizer

synthesizer = SketchGuidedSynthesizer(config={
    "min_sketch_frequency": 2,
    "max_sketch_library_size": 100,
    "vsa_enabled": True,
})

# Extract sketches from successful programs
programs_with_stats = [(program, cost, success) for ...]
sketches = synthesizer.extract_sketch_library(programs_with_stats)

# Synthesize from a sketch
programs = synthesizer.synthesize_from_sketch(
    sketch, examples, budget, interpreter
)
```

### 2. Abstract Interpretation (`abstract_interpreter.py`)

**Classes:**
- `AbstractGrid`: Abstract representation of a grid
- `AbstractInterpreter`: Executes programs in abstract domain

**Key Features:**
- Track abstract properties (colors, components, symmetries)
- Execute programs abstractly for early pruning
- Check feasibility without full concrete execution

**Usage:**
```python
from arc.symbolic.search import AbstractGrid, AbstractInterpreter

interpreter = AbstractInterpreter()

# Create abstract grid from concrete grid
abstract_input = AbstractGrid.from_concrete_grid(concrete_grid)

# Execute program abstractly
abstract_output = interpreter.abstract_execute(program, abstract_input)

# Check feasibility
is_feasible = interpreter.check_feasibility(abstract_output, expected_output)
```

### 3. PCFG-Based Search (`pcfg.py`)

**Classes:**
- `PCFG`: Probabilistic Context-Free Grammar
- `ProbabilisticEnumerator`: Enumerator using PCFG

**Key Features:**
- Learn production probabilities from successful programs
- Sample programs based on learned probabilities
- Beam search guided by PCFG probabilities

**Usage:**
```python
from arc.symbolic.search import ProbabilisticEnumerator

enumerator = ProbabilisticEnumerator(config={
    "smoothing_factor": 0.1,
    "min_production_count": 1,
})

# Train PCFG from successful programs
pcfg = enumerator.train_pcfg(successful_programs)

# Sample a program
program = enumerator.sample_program(pcfg, max_depth=10, temperature=1.0)

# Beam search with PCFG
programs = enumerator.beam_search_with_pcfg(
    pcfg, examples, beam_width=10, max_depth=10, interpreter
)
```

### 4. MCTS Search (`mcts.py`)

**Classes:**
- `MCTSNode`: Node in the MCTS tree
- `MCTSSearcher`: MCTS search implementation
- `PolicyModel`: Protocol for policy models
- `ValueModel`: Protocol for value models

**Key Features:**
- UCB1-based node selection
- Policy and value model guidance
- Backpropagation of rewards
- Extraction of best programs

**Usage:**
```python
from arc.symbolic.search import MCTSSearcher

searcher = MCTSSearcher(config={
    "exploration_constant": 1.414,
    "max_depth": 10,
    "simulation_depth": 5,
})

# Perform MCTS search
programs = searcher.search(
    examples, budget, policy_model, value_model, interpreter, seed=42
)
```

### 5. Diversity Control (`diversity.py`)

**Classes:**
- `DiversityController`: Manages program diversity

**Key Features:**
- Compute semantic distance between programs
- Compute edit distance (Levenshtein)
- Deduplicate candidates based on similarity
- Select diverse subsets

**Usage:**
```python
from arc.symbolic.search import DiversityController

controller = DiversityController(config={
    "semantic_threshold": 0.1,
    "syntactic_threshold": 3,
})

# Deduplicate candidates
diverse_programs = controller.deduplicate_candidates(
    candidates, examples, interpreter, threshold=0.1
)

# Select diverse subset
subset = controller.select_diverse_subset(
    candidates, k=10, examples, interpreter
)
```

### 6. Neural Model Interfaces (`neural_models.py`)

**Classes:**
- `PolicyModel`: Base policy model interface
- `ValueModel`: Base value model interface
- `UniformPolicyModel`: Uniform probability baseline
- `HeuristicValueModel`: Heuristic-based value estimation
- `FrequencyBasedPolicyModel`: Frequency-based policy learning

**Key Features:**
- Protocol definitions for neural guidance
- Stub implementations for testing
- Frequency-based learning from successful programs

**Usage:**
```python
from arc.symbolic.search import (
    UniformPolicyModel,
    HeuristicValueModel,
    FrequencyBasedPolicyModel,
)

# Use uniform policy
policy_model = UniformPolicyModel()
policy = policy_model.predict_policy(program, examples)

# Use heuristic value model
value_model = HeuristicValueModel()
value = value_model.predict_value(program, examples)

# Train frequency-based policy
freq_policy = FrequencyBasedPolicyModel()
freq_policy.train(training_data)
```

### 7. Integration (`advanced_search_integration.py`)

**Classes:**
- `AdvancedSearchCoordinator`: Unified interface for all strategies

**Key Features:**
- Coordinate multiple search strategies
- Feature flags for enabling/disabling components
- Training from successful programs
- Pruning with abstract interpretation

**Usage:**
```python
from arc.symbolic.search import AdvancedSearchCoordinator

coordinator = AdvancedSearchCoordinator(config={
    "enable_sketch_guided": True,
    "enable_abstract_interpretation": True,
    "enable_pcfg": True,
    "enable_mcts": True,
    "enable_diversity_control": True,
    "search_strategy": "mcts",  # or "sketch_guided", "pcfg"
})

# Perform search
programs = coordinator.search(examples, budget, interpreter)

# Train from successful programs
coordinator.train_from_successful_programs(successful_programs)
```

## Configuration

Advanced search strategies can be configured through the solver configuration:

```yaml
symbolic:
  search:
    advanced:
      enable_sketch_guided: true
      enable_abstract_interpretation: true
      enable_pcfg: true
      enable_mcts: true
      enable_diversity_control: true
      search_strategy: "beam"  # or "sketch_guided", "pcfg", "mcts"
      
      sketch_guided:
        min_sketch_frequency: 2
        max_sketch_library_size: 100
        vsa_enabled: true
      
      abstract_interpretation:
        enable_color_tracking: true
        enable_component_tracking: true
        enable_symmetry_tracking: true
      
      pcfg:
        smoothing_factor: 0.1
        min_production_count: 1
      
      mcts:
        exploration_constant: 1.414
        max_depth: 10
        simulation_depth: 5
      
      diversity:
        semantic_threshold: 0.1
        syntactic_threshold: 3
```

## Testing

Comprehensive unit tests are provided in `tests/symbolic/test_advanced_search.py`:

```bash
# Run all advanced search tests
pytest tests/symbolic/test_advanced_search.py -v

# Run specific test class
pytest tests/symbolic/test_advanced_search.py::TestSketchGuidedSynthesizer -v
```

All tests pass successfully (32 tests).

## Requirements Satisfied

This implementation satisfies the following requirements from the design document:

- **Requirement 6.1, 6.2**: Sketch-guided synthesis with VSA
- **Requirement 7.1, 7.2, 7.3**: Abstract interpretation for early pruning
- **Requirement 8.1, 8.2**: PCFG-based probabilistic search
- **Requirement 8.2**: MCTS with policy and value models
- **Requirement 8.3, 8.5**: Diversity control for candidate deduplication
- **Requirement 8.4**: Neural model interfaces for future integration

## Future Enhancements

Potential future improvements:

1. **Neural Policy/Value Models**: Replace stub implementations with trained neural networks
2. **Parallel MCTS**: Distribute MCTS search across multiple threads
3. **Adaptive Strategy Selection**: Automatically select best strategy based on task features
4. **Sketch Refinement**: Iteratively refine sketches based on synthesis results
5. **Hybrid Search**: Combine multiple strategies in a single search session

## References

- Design Document: `.kiro/specs/symbolic-synthesis-enhancement/design.md`
- Requirements: `.kiro/specs/symbolic-synthesis-enhancement/requirements.md`
- Tasks: `.kiro/specs/symbolic-synthesis-enhancement/tasks.md`
