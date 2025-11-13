from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from arc.symbolic.dsl.types import Stage


@dataclass
class Invariant:
    type: str
    constraint: Any
    confidence: float
    source: str

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Invariant: ...
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, json_str: str) -> Invariant: ...
    def validate(self) -> bool: ...


@dataclass
class Relation:
    relation_type: str
    objects: List[int]
    parameters: Dict[str, Any]
    confidence: float

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Relation: ...
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, json_str: str) -> Relation: ...
    def validate(self) -> bool: ...


@dataclass
class DSLMacro:
    name: str
    parameters: List[str]
    body: Sequence[Stage]
    documentation: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DSLMacro: ...
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, json_str: str) -> DSLMacro: ...
    def validate(self) -> bool: ...
    def expand(self, argument_values: Dict[str, Any]) -> List[Stage]: ...
