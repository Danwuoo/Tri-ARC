"""E-graph engine for program equivalence and optimization."""

from .analyzer import BoundingBox, ConnectivityInfo, EClassAnalyzer, EClassSummary, SymmetryFlags
from .compression import CompressionResult, FragmentCandidate, mine_fragments
from .engine import EGraph, ProgramRecord, RewriteApplication, RewriteRule, SaturationStats
from .extractor import BeamExtractor, GreedyExtractor, MultiObjectiveExtractor, OptimalExtractor
from .rule_miner import RuleMiner, RuleValidator
from .rules import builtin_rules

__all__ = [
    # Engine
    "EGraph",
    "ProgramRecord",
    "RewriteApplication",
    "RewriteRule",
    "SaturationStats",
    # Rules
    "builtin_rules",
    # Compression
    "mine_fragments",
    "FragmentCandidate",
    "CompressionResult",
    # Analyzer
    "EClassAnalyzer",
    "EClassSummary",
    "BoundingBox",
    "ConnectivityInfo",
    "SymmetryFlags",
    # Extractor
    "OptimalExtractor",
    "GreedyExtractor",
    "BeamExtractor",
    "MultiObjectiveExtractor",
    # Rule Mining
    "RuleMiner",
    "RuleValidator",
]
