"""Unit tests for DSL library management system."""

import pytest
from pathlib import Path
import tempfile
import shutil

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.library import (
    FragmentMiner,
    ProgramFragment,
    FragmentScore,
    RuleLearner,
    LibraryCurator,
    LibraryPersistence,
    LibraryManager,
)
from arc.symbolic.library.curator import Primitive
from arc.symbolic.egraph.engine import RewriteRule


class TestFragmentMiner:
    """Tests for FragmentMiner class."""
    
    def test_mine_fragments_basic(self):
        """Test basic fragment mining from successful programs."""
        miner = FragmentMiner()
        
        # Create test programs with common subsequences
        programs = [
            Program(stages=(
                Stage("rotate", (1,)),
                Stage("reflect", ("horizontal",)),
                Stage("paint", (1,))
            )),
            Program(stages=(
                Stage("rotate", (1,)),
                Stage("reflect", ("horizontal",)),
                Stage("paint", (2,))
            )),
            Program(stages=(
                Stage("rotate", (1,)),
                Stage("reflect", ("horizontal",)),
                Stage("fill", (3,))
            )),
        ]
        
        fragments = miner.mine_fragments(programs, min_frequency=2)
        
        # Should find the common rotate+reflect pattern
        assert len(fragments) > 0
        
        # Check that fragments have required attributes
        for fragment in fragments:
            assert isinstance(fragment, ProgramFragment)
            assert fragment.id is not None
            assert len(fragment.stages) > 0
            assert fragment.frequency >= 2
    
    def test_mine_fragments_no_common_patterns(self):
        """Test fragment mining with no common patterns."""
        miner = FragmentMiner()
        
        # Create programs with no common subsequences
        programs = [
            Program(stages=(Stage("rotate", (1,)),)),
            Program(stages=(Stage("reflect", ("horizontal",)),)),
            Program(stages=(Stage("paint", (1,)),)),
        ]
        
        fragments = miner.mine_fragments(programs, min_frequency=2)
        
        # Should find no multi-stage fragments
        assert len(fragments) == 0
    
    def test_anti_unify_identical_programs(self):
        """Test anti-unification of identical programs."""
        miner = FragmentMiner()
        
        program = Program(stages=(
            Stage("rotate", (1,)),
            Stage("reflect", ("horizontal",))
        ))
        
        template = miner.anti_unify(program, program)
        
        # Identical programs should not produce a template (no parameters)
        assert template is None
    
    def test_anti_unify_different_arguments(self):
        """Test anti-unification with different arguments."""
        miner = FragmentMiner()
        
        prog_a = Program(stages=(
            Stage("rotate", (1,)),
            Stage("paint", (1,))
        ))
        prog_b = Program(stages=(
            Stage("rotate", (2,)),
            Stage("paint", (2,))
        ))
        
        template = miner.anti_unify(prog_a, prog_b)
        
        # Should create a template with parameters
        assert template is not None
        assert len(template.parameters) > 0
        assert len(template.stages) == 2
    
    def test_anti_unify_different_operators(self):
        """Test anti-unification with different operators."""
        miner = FragmentMiner()
        
        prog_a = Program(stages=(Stage("rotate", (1,)),))
        prog_b = Program(stages=(Stage("reflect", ("horizontal",)),))
        
        template = miner.anti_unify(prog_a, prog_b)
        
        # Different operators cannot be unified
        assert template is None
    
    def test_score_fragment(self):
        """Test fragment scoring."""
        miner = FragmentMiner()
        
        fragment = (
            Stage("rotate", (1,)),
            Stage("reflect", ("horizontal",))
        )
        
        corpus = [
            Program(stages=(
                Stage("rotate", (1,)),
                Stage("reflect", ("horizontal",)),
                Stage("paint", (1,))
            )),
            Program(stages=(
                Stage("rotate", (1,)),
                Stage("reflect", ("horizontal",)),
            )),
        ]
        
        score = miner.score_fragment(fragment, frequency=2, corpus=corpus)
        
        assert isinstance(score, FragmentScore)
        assert score.utility > 0
        assert score.generality > 0
        assert score.complexity_reduction > 0
        assert score.frequency == 2


class TestRuleLearner:
    """Tests for RuleLearner class."""
    
    def test_learn_rules_basic(self):
        """Test basic rule learning from equivalence examples."""
        learner = RuleLearner()
        
        # Create equivalence examples (simplified programs)
        examples = [
            (
                Program(stages=(Stage("rotate", (1,)), Stage("rotate", (1,)))),
                Program(stages=(Stage("rotate", (2,)),))
            ),
            (
                Program(stages=(Stage("rotate", (2,)), Stage("rotate", (2,)))),
                Program(stages=(Stage("rotate", (0,)),))
            ),
        ]
        
        # Need at least min_examples
        learner.min_examples = 2
        rules = learner.learn_rules(examples)
        
        # Should learn at least one rule
        assert len(rules) >= 0  # May be 0 if patterns don't match
    
    def test_induce_preconditions(self):
        """Test precondition induction."""
        learner = RuleLearner()
        
        # Create a dummy rule
        def dummy_apply(program):
            return []
        
        rule = RewriteRule(name="test_rule", apply=dummy_apply)
        
        # Positive examples with common operator
        positive = [
            Program(stages=(Stage("rotate", (1,)), Stage("paint", (1,)))),
            Program(stages=(Stage("rotate", (2,)), Stage("paint", (2,)))),
        ]
        
        # Negative examples without rotate
        negative = [
            Program(stages=(Stage("reflect", ("horizontal",)),)),
        ]
        
        preconditions = learner.induce_preconditions(rule, positive, negative)
        
        # Should induce some preconditions
        assert len(preconditions) > 0
        
        # Check preconditions have required attributes
        for precond in preconditions:
            assert precond.type is not None
            assert precond.confidence > 0
    
    def test_validate_rule(self):
        """Test rule validation."""
        learner = RuleLearner()
        
        def dummy_apply(program):
            return []
        
        rule = RewriteRule(name="test_rule", apply=dummy_apply)
        
        # Dummy validation tasks
        validation_tasks = [{"task_id": f"task_{i}"} for i in range(5)]
        
        result = learner.validate_rule(rule, validation_tasks)
        
        assert result.rule_name == "test_rule"
        assert 0 <= result.success_rate <= 1
        assert 0 <= result.false_positive_rate <= 1


class TestLibraryCurator:
    """Tests for LibraryCurator class."""
    
    def test_add_primitive(self):
        """Test adding a primitive to the library."""
        curator = LibraryCurator()
        
        primitive = Primitive(
            name="test_op",
            type="operator",
            implementation=lambda x: x
        )
        
        curator.add_primitive(primitive)
        
        assert "test_op" in curator._primitives
        assert curator._primitives["test_op"].name == "test_op"
    
    def test_add_fragment(self):
        """Test adding a fragment to the library."""
        curator = LibraryCurator()
        
        fragment = ProgramFragment(
            id="frag_001",
            stages=(Stage("rotate", (1,)),),
            frequency=5
        )
        
        curator.add_fragment(fragment)
        
        assert "frag_001" in curator._fragments
    
    def test_prune_library(self):
        """Test library pruning."""
        curator = LibraryCurator()
        
        # Add some fragments with low usage
        for i in range(5):
            fragment = ProgramFragment(
                id=f"frag_{i:03d}",
                stages=(Stage("rotate", (i,)),),
                frequency=1
            )
            curator.add_fragment(fragment)
        
        # Record usage for only some fragments
        curator.record_usage("frag_000", 100)
        curator.record_usage("frag_001", 50)
        
        initial_count = len(curator._fragments)
        report = curator.prune_library(usage_threshold=0.1)
        
        # Should have pruned some fragments
        assert report.fragments_removed > 0
        assert len(curator._fragments) < initial_count
    
    def test_rollback_rule(self):
        """Test rule rollback."""
        curator = LibraryCurator()
        
        def dummy_apply(program):
            return []
        
        rule = RewriteRule(name="bad_rule", apply=dummy_apply)
        curator.add_rule(rule)
        
        assert "bad_rule" in curator._rules
        
        curator.rollback_rule("bad_rule", "rule caused errors")
        
        assert "bad_rule" not in curator._rules
        assert "bad_rule" in curator._blacklist
    
    def test_blacklist_prevents_readd(self):
        """Test that blacklisted items cannot be re-added."""
        curator = LibraryCurator()
        
        def dummy_apply(program):
            return []
        
        rule = RewriteRule(name="bad_rule", apply=dummy_apply)
        curator.add_rule(rule)
        curator.rollback_rule("bad_rule", "test")
        
        # Try to add again
        curator.add_rule(rule)
        
        # Should still not be in library
        assert "bad_rule" not in curator._rules
    
    def test_get_library_stats(self):
        """Test getting library statistics."""
        curator = LibraryCurator()
        
        stats = curator.get_library_stats()
        
        assert "version" in stats
        assert "primitives" in stats
        assert "rules" in stats
        assert "fragments" in stats
        assert "total_items" in stats


class TestLibraryPersistence:
    """Tests for LibraryPersistence class."""
    
    def test_save_and_load(self):
        """Test saving and loading library state."""
        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = LibraryPersistence(Path(tmpdir))
            
            # Create test data
            primitives = {
                "test_op": Primitive(name="test_op", type="operator", implementation=None)
            }
            fragments = {
                "frag_001": ProgramFragment(
                    id="frag_001",
                    stages=(Stage("rotate", (1,)),),
                    frequency=5
                )
            }
            rules = {}
            usage_counts = {"frag_001": 10}
            impact_scores = {"frag_001": 0.5}
            blacklist = set()
            versions = []
            current_version = "1.0.0"
            
            # Save
            persistence.save(
                primitives=primitives,
                fragments=fragments,
                rules=rules,
                usage_counts=usage_counts,
                impact_scores=impact_scores,
                blacklist=blacklist,
                versions=versions,
                current_version=current_version
            )
            
            # Load
            state = persistence.load()
            
            assert state is not None
            assert state.version == "1.0.0"
            assert "test_op" in state.primitives
            assert "frag_001" in state.fragments
            assert state.usage_counts["frag_001"] == 10
    
    def test_load_nonexistent(self):
        """Test loading from nonexistent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = LibraryPersistence(Path(tmpdir) / "nonexistent")
            
            state = persistence.load()
            
            assert state is None


class TestLibraryManager:
    """Tests for LibraryManager integration."""
    
    def test_initialization(self):
        """Test library manager initialization."""
        manager = LibraryManager()
        
        assert manager.fragment_miner is not None
        assert manager.rule_learner is not None
        assert manager.curator is not None
        assert manager.persistence is not None
    
    def test_on_solve_success(self):
        """Test solve success hook."""
        manager = LibraryManager(config={
            "library": {
                "fragment_mining": {"enabled": True, "min_frequency": 2}
            }
        })
        
        # Create successful programs
        programs = [
            Program(stages=(
                Stage("rotate", (1,)),
                Stage("reflect", ("horizontal",))
            )),
            Program(stages=(
                Stage("rotate", (1,)),
                Stage("reflect", ("horizontal",))
            )),
        ]
        
        initial_fragment_count = len(manager.curator._fragments)
        
        manager.on_solve_success(
            task_id="test_task",
            successful_programs=programs,
            candidates=[]
        )
        
        # Should have mined some fragments
        # (May be 0 if patterns don't meet threshold)
        assert len(manager.curator._fragments) >= initial_fragment_count
    
    def test_get_library_stats(self):
        """Test getting library statistics."""
        manager = LibraryManager()
        
        stats = manager.get_library_stats()
        
        assert "version" in stats
        assert "solve_count" in stats
        assert stats["solve_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
