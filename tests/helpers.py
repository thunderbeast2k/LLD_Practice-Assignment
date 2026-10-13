from pathlib import Path

from lld_practice.evaluation.base import Evaluator, EvaluatorResult
from lld_practice.evaluation.pipeline import EvaluationPipeline
from lld_practice.evaluation.rules import default_rule_evaluators
from lld_practice.jobs import InlineRunner
from lld_practice.parsing import FormatRegistry
from lld_practice.service import PracticeService
from lld_practice.storage import InMemoryRepository

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def example(name: str) -> str:
    return (EXAMPLES / name).read_text()


class Boom(Evaluator):
    name, kind = "boom", "ai"

    def evaluate(self, ctx):
        raise RuntimeError("upstream timeout")


class Flaky(Evaluator):
    """Fails the first `fail_times` calls, then returns a finding."""
    name, kind = "flaky-ai", "ai"

    def __init__(self, fail_times=1):
        self.left = fail_times

    def evaluate(self, ctx):
        if self.left > 0:
            self.left -= 1
            raise RuntimeError("temporarily down")
        return EvaluatorResult([], summary="AI says nice.")


def make_service(extra=(), rules=True, runner=None, repo=None):
    evs = (default_rule_evaluators() if rules else []) + list(extra)
    pipeline = EvaluationPipeline(FormatRegistry(), evs)
    return PracticeService(repo or InMemoryRepository(), pipeline, runner or InlineRunner())
