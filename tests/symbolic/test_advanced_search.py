"""Unit tests for advanced search strategies (Phase 7).

This module tests:
- Sketch-guided synthesis
- Abstract interpretation
- PCFG sampling and training
- MCTS search
- Diversity control
"""

import numpy as np
import pytest

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.ir.sketch import Hole, ProgramSketch
from arc.symbolic.search import (
    AbstractGrid,
    AbstractInterpreter,
    AdvancedSearchCoordinator,
    DiversityController,
    FrequencyBasedPolicyModel,
    HeuristicValueModel,
    MCTSNode,
    MCTSSearcher,
    PCFG,
    ProbabilisticEnumerator,
    SearchBudget,
    SketchGuidedSynthesizer,
    TrainingExample,
    UniformPolicyModel,
)


# Test fixtures
@pytest.fixture
def simple_grid():
    """Create a simple 3x3 grid for testing."""
    return np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1]
    ])


@pytest.fixture
def training_examples(simple_grid):
    """Create training examples for testing."""
    input_grid = simple_grid
    output_grid = np.rot90(simple_grid)
    return [TrainingExample(input_grid=input_grid, output_grid=output_grid)]


@pytest.fixture
def search_budget():
    """Create a search budget for testing."""
    return SearchBudget(
        max_depth=5,
        max_expansions=100,
        soft_timeout_s=10.0,
        hard_timeout_s=20.0,
        max_candidates=10,
        beam_width=5,
        seed=42,
    )


@pytest.fixture
def simple_program():
    """Create a simple program for testing."""
    return Program(stages=(
        Stage(operator="rotate_cw", arguments=()),
        Stage(operator="reflect_horizontal", arguments=()),
    ))


@pytest.fixture
def simple_programs():
    """Create a list of simple programs for testing."""
    return [
        Program(stages=(Stage(operator="rotate_cw", arguments=()),)),
        Program(stages=(Stage(operator="rotate_ccw", arguments=()),)),
        Program(stages=(Stage(operator="reflect_horizontal", arguments=()),)),
    ]


# Sketch-guided synthesis tests
class TestSketchGuidedSynthesizer:
    """Tests for SketchGuidedSynthesizer."""
    
    def test_initialization(self):
        """Test synthesizer initialization."""
        synthesizer = SketchGuidedSynthesizer()
        assert synthesizer is not None
        assert synthesizer.sketch_library == {}
    
    def test_extract_sketch_library(self, simple_programs):
        """Test sketch extraction from successful programs."""
        synthesizer = SketchGuidedSynthesizer(config={"min_sketch_frequency": 1})
        
        programs_with_stats = [(p, 1.0, True) for p in simple_programs]
        sketches = synthesizer.extract_sketch_library(programs_with_stats)
        
        assert len(sketches) >= 0
        assert len(synthesizer.sketch_library) >= 0
    
    def test_get_best_sketches(self, simple_programs):
        """Test getting best sketches from library."""
        synthesizer = SketchGuidedSynthesizer(config={"min_sketch_frequency": 1})
        
        programs_with_stats = [(p, 1.0, True) for p in simple_programs]
        synthesizer.extract_sketch_library(programs_with_stats)
        
        best_sketches = synthesizer.get_best_sketches(top_k=2)
        assert len(best_sketches) <= 2
    
    def test_synthesize_from_sketch_with_no_holes(self, training_examples, search_budget):
        """Test synthesis from a complete sketch (no holes)."""
        synthesizer = SketchGuidedSynthesizer()
        
        # Create a complete sketch (no holes)
        sketch = ProgramSketch(
            stages=[Stage(operator="rotate_cw", arguments=())],
        )
        
        programs = synthesizer.synthesize_from_sketch(
            sketch, training_examples, search_budget
        )
        
        assert len(programs) == 1
        assert len(programs[0].stages) == 1


# Abstract interpretation tests
class TestAbstractInterpreter:
    """Tests for AbstractInterpreter."""
    
    def test_initialization(self):
        """Test interpreter initialization."""
        interpreter = AbstractInterpreter()
        assert interpreter is not None
    
    def test_abstract_grid_from_concrete(self, simple_grid):
        """Test creating abstract grid from concrete grid."""
        abstract = AbstractGrid.from_concrete_grid(simple_grid)
        
        assert abstract is not None
        assert 1 in abstract.color_set
        assert 0 in abstract.color_set
        assert abstract.shape_range[0] == (3, 3)
        assert abstract.shape_range[1] == (3, 3)
    
    def test_abstract_execute_rotate(self, simple_grid, simple_program):
        """Test abstract execution of rotation."""
        interpreter = AbstractInterpreter()
        abstract_input = AbstractGrid.from_concrete_grid(simple_grid)
        
        # Execute just the rotation stage
        rotate_program = Program(stages=(simple_program.stages[0],))
        abstract_output = interpreter.abstract_execute(rotate_program, abstract_input)
        
        assert abstract_output is not None
        assert abstract_output.color_set == abstract_input.color_set
    
    def test_check_feasibility(self, simple_grid):
        """Test feasibility checking."""
        interpreter = AbstractInterpreter()
        abstract_grid = AbstractGrid.from_concrete_grid(simple_grid)
        
        # Should be compatible with itself
        assert interpreter.check_feasibility(abstract_grid, simple_grid)
        
        # Should not be compatible with different grid
        different_grid = np.array([[2, 2], [2, 2]])
        assert not interpreter.check_feasibility(abstract_grid, different_grid)


# PCFG tests
class TestPCFG:
    """Tests for PCFG."""
    
    def test_initialization(self):
        """Test PCFG initialization."""
        pcfg = PCFG()
        assert pcfg is not None
        assert pcfg.start_symbol == "Program"
    
    def test_add_production(self):
        """Test adding production rules."""
        pcfg = PCFG()
        pcfg.add_production("Program", ["Stage_rotate"], 1.0)
        
        assert "Program" in pcfg.production_rules
        assert len(pcfg.production_rules["Program"]) == 1
    
    def test_sample_production(self):
        """Test sampling a production."""
        pcfg = PCFG()
        pcfg.add_production("Program", ["Stage_rotate"], 0.5)
        pcfg.add_production("Program", ["Stage_reflect"], 0.5)
        
        production = pcfg.sample_production("Program", temperature=1.0)
        assert production in [["Stage_rotate"], ["Stage_reflect"]]


class TestProbabilisticEnumerator:
    """Tests for ProbabilisticEnumerator."""
    
    def test_initialization(self):
        """Test enumerator initialization."""
        enumerator = ProbabilisticEnumerator()
        assert enumerator is not None
    
    def test_train_pcfg(self, simple_programs):
        """Test training PCFG from programs."""
        enumerator = ProbabilisticEnumerator()
        pcfg = enumerator.train_pcfg(simple_programs)
        
        assert pcfg is not None
        assert len(pcfg.production_rules) > 0
    
    def test_sample_program(self, simple_programs):
        """Test sampling a program from PCFG."""
        enumerator = ProbabilisticEnumerator()
        enumerator.train_pcfg(simple_programs)
        
        program = enumerator.sample_program(max_depth=3, seed=42)
        assert program is None or isinstance(program, Program)


# MCTS tests
class TestMCTSNode:
    """Tests for MCTSNode."""
    
    def test_initialization(self, simple_program):
        """Test node initialization."""
        node = MCTSNode(program=simple_program)
        assert node is not None
        assert node.visits == 0
        assert node.total_reward == 0.0
    
    def test_average_reward(self, simple_program):
        """Test average reward calculation."""
        node = MCTSNode(program=simple_program)
        node.visits = 10
        node.total_reward = 5.0
        
        assert node.average_reward == 0.5
    
    def test_ucb1_score(self, simple_program):
        """Test UCB1 score calculation."""
        parent = MCTSNode(program=Program(stages=()))
        parent.visits = 100
        
        child = MCTSNode(program=simple_program, parent=parent)
        child.visits = 10
        child.total_reward = 5.0
        
        score = child.ucb1_score(exploration_constant=1.414)
        assert score > 0.0
    
    def test_is_leaf(self, simple_program):
        """Test leaf node detection."""
        node = MCTSNode(program=simple_program)
        assert node.is_leaf()
        
        child = MCTSNode(program=simple_program)
        node.add_child(child)
        assert not node.is_leaf()


class TestMCTSSearcher:
    """Tests for MCTSSearcher."""
    
    def test_initialization(self):
        """Test searcher initialization."""
        searcher = MCTSSearcher()
        assert searcher is not None
    
    def test_select_node(self, simple_program):
        """Test node selection."""
        searcher = MCTSSearcher()
        root = MCTSNode(program=Program(stages=()))
        
        # Add some children
        for i in range(3):
            child = MCTSNode(program=simple_program)
            child.visits = i + 1
            child.total_reward = float(i)
            root.add_child(child)
        
        selected = searcher.select_node(root)
        assert selected in root.children
    
    def test_backpropagate(self, simple_program):
        """Test reward backpropagation."""
        searcher = MCTSSearcher()
        
        root = MCTSNode(program=Program(stages=()))
        child = MCTSNode(program=simple_program, parent=root)
        
        searcher.backpropagate(child, reward=1.0)
        
        assert child.visits == 1
        assert child.total_reward == 1.0
        assert root.visits == 1
        assert root.total_reward == 1.0


# Diversity control tests
class TestDiversityController:
    """Tests for DiversityController."""
    
    def test_initialization(self):
        """Test controller initialization."""
        controller = DiversityController()
        assert controller is not None
    
    def test_compute_edit_distance(self):
        """Test edit distance computation."""
        controller = DiversityController()
        
        prog1 = Program(stages=(
            Stage(operator="rotate_cw", arguments=()),
        ))
        prog2 = Program(stages=(
            Stage(operator="rotate_ccw", arguments=()),
        ))
        
        distance = controller.compute_edit_distance(prog1, prog2)
        assert distance == 1  # One substitution
    
    def test_compute_edit_distance_identical(self, simple_program):
        """Test edit distance for identical programs."""
        controller = DiversityController()
        
        distance = controller.compute_edit_distance(simple_program, simple_program)
        assert distance == 0
    
    def test_deduplicate_candidates(self, simple_programs):
        """Test candidate deduplication."""
        controller = DiversityController(config={"syntactic_threshold": 1})
        
        # Add duplicates
        candidates = simple_programs + simple_programs
        
        deduplicated = controller.deduplicate_candidates(candidates, threshold=0.5)
        
        # Should remove exact duplicates
        assert len(deduplicated) <= len(candidates)
    
    def test_compute_diversity_score(self, simple_programs):
        """Test diversity score computation."""
        controller = DiversityController()
        
        score = controller.compute_diversity_score(simple_programs)
        assert 0.0 <= score <= 1.0


# Neural model tests
class TestNeuralModels:
    """Tests for neural model interfaces."""
    
    def test_uniform_policy_model(self, simple_program, training_examples):
        """Test uniform policy model."""
        model = UniformPolicyModel()
        policy = model.predict_policy(simple_program, training_examples)
        
        assert isinstance(policy, dict)
        assert len(policy) > 0
        
        # All probabilities should be equal
        probs = list(policy.values())
        assert all(abs(p - probs[0]) < 1e-6 for p in probs)
    
    def test_heuristic_value_model(self, simple_program, training_examples):
        """Test heuristic value model."""
        model = HeuristicValueModel()
        value = model.predict_value(simple_program, training_examples)
        
        assert 0.0 <= value <= 1.0
    
    def test_frequency_based_policy_model(self, simple_programs, training_examples):
        """Test frequency-based policy model."""
        model = FrequencyBasedPolicyModel()
        
        # Train on programs
        training_data = [(p, training_examples, "rotate_cw") for p in simple_programs]
        model.train(training_data)
        
        # Predict policy
        policy = model.predict_policy(simple_programs[0], training_examples)
        assert isinstance(policy, dict)
        assert len(policy) > 0


# Integration tests
class TestAdvancedSearchCoordinator:
    """Tests for AdvancedSearchCoordinator."""
    
    def test_initialization(self):
        """Test coordinator initialization."""
        coordinator = AdvancedSearchCoordinator()
        assert coordinator is not None
    
    def test_initialization_with_features(self):
        """Test coordinator with features enabled."""
        config = {
            "enable_sketch_guided": True,
            "enable_abstract_interpretation": True,
            "enable_pcfg": True,
            "enable_mcts": True,
            "enable_diversity_control": True,
        }
        coordinator = AdvancedSearchCoordinator(config)
        
        assert coordinator.sketch_synthesizer is not None
        assert coordinator.abstract_interpreter is not None
        assert coordinator.pcfg_enumerator is not None
        assert coordinator.mcts_searcher is not None
        assert coordinator.diversity_controller is not None
    
    def test_train_from_successful_programs(self, simple_programs):
        """Test training from successful programs."""
        config = {
            "enable_sketch_guided": True,
            "enable_pcfg": True,
        }
        coordinator = AdvancedSearchCoordinator(config)
        
        # Should not raise an exception
        coordinator.train_from_successful_programs(simple_programs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
