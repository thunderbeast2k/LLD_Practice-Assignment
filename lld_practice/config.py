"""Composition root: wires concrete implementations together."""
from __future__ import annotations

import os

from .evaluation.llm import AnthropicClient, LLMReviewEvaluator
from .evaluation.pipeline import EvaluationPipeline
from .evaluation.rules import default_rule_evaluators
from .jobs import JobRunner, ThreadRunner
from .parsing import FormatRegistry
from .service import PracticeService
from .storage import AttemptRepository, SQLiteRepository


def build_service(db_path: str = "lld_practice.db", runner: JobRunner | None = None,
                  repo: AttemptRepository | None = None, env=os.environ) -> PracticeService:
    evaluators = default_rule_evaluators()
    key = env.get("ANTHROPIC_API_KEY")
    if key:  # AI review is strictly optional
        client = AnthropicClient(key, model=env.get("LLD_LLM_MODEL", "claude-sonnet-5-5"),
                                 timeout=float(env.get("LLD_LLM_TIMEOUT", "30")))
        evaluators.append(LLMReviewEvaluator(client))
    pipeline = EvaluationPipeline(FormatRegistry(), evaluators)
    service = PracticeService(repo or SQLiteRepository(db_path), pipeline, runner or ThreadRunner())
    service.recover_interrupted()
    return service
