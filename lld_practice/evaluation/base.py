"""Evaluator contract. Add a new evaluation approach by implementing `Evaluator`."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..catalog import Problem
from ..design_model import DesignModel


@dataclass
class EvaluationContext:
    problem: Problem
    design: DesignModel
    content: str
    rationale: str = ""


@dataclass
class EvaluatorResult:
    findings: list = field(default_factory=list)
    dimension: Optional[str] = None   # set when the evaluator owns a scored dimension
    score: Optional[float] = None     # 0..100
    summary: str = ""


class EvaluatorUnavailable(Exception):
    """Evaluator could not run (network, timeout, bad output). Not a learner error."""


class Evaluator(ABC):
    name: str = "evaluator"
    kind: str = "deterministic"  # "deterministic" | "ai"

    @abstractmethod
    def evaluate(self, ctx: EvaluationContext) -> EvaluatorResult: ...
