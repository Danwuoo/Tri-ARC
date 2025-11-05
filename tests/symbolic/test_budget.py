from __future__ import annotations

import time

from arc.symbolic.search import SearchBudget


def test_budget_limits_expansions_and_nodes():
    budget = SearchBudget(
        max_depth=3,
        max_expansions=2,
        soft_timeout_s=10.0,
        hard_timeout_s=10.0,
        max_nodes=3,
    )
    budget.start()
    assert budget.allow_expansion()
    assert budget.register_node()  # root
    assert budget.register_node()
    assert budget.generated_nodes == 2
    assert budget.register_expansion()
    assert budget.register_expansion()
    assert not budget.allow_expansion()


def test_budget_timeouts():
    budget = SearchBudget(
        max_depth=2,
        max_expansions=5,
        soft_timeout_s=0.1,
        hard_timeout_s=0.2,
        max_nodes=10,
    )
    budget.start()
    time.sleep(0.12)
    assert not budget.within_time(soft=True)
    assert budget.within_time(soft=False)
    time.sleep(0.1)
    assert not budget.within_time(soft=False)
