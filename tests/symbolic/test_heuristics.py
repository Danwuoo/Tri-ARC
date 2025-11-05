from __future__ import annotations

from arc.symbolic.heuristics import HeuristicContext
from arc.symbolic.heuristics.rule_based import RuleBasedHeuristic
from arc.symbolic.search import SearchNode, TrainingExample


def make_node(depth: int, score: float = 0.0, cost: float = 0.0) -> SearchNode:
    return SearchNode(
        node_id=depth,
        stages=tuple(),
        depth=depth,
        score=score,
        cost=cost,
        metadata={
            "coverage": 0.5,
            "consistency": 0.4,
            "progress": 0.3,
            "novelty": 0.2,
            "stagnation": 0.1,
        },
    )


def test_rule_based_heuristic_scores_within_unit_interval():
    context = HeuristicContext(
        task_id="demo",
        examples=[TrainingExample(input_grid=[[1]], output_grid=[[1]])],
        metadata={},
        max_depth=4,
        device="cpu",
        seed=1234,
    )
    heuristic = RuleBasedHeuristic()
    heuristic.initialise(context)
    node = make_node(depth=1, cost=0.2)
    result = heuristic.score(node)
    assert 0.0 <= result.score <= 1.0
    assert "coverage" in result.reasoning
