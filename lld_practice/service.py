"""Application service: the learner journey (choose -> design -> submit -> feedback -> review -> retry)."""
from __future__ import annotations

import logging
from typing import Optional

from .catalog import ProblemCatalog
from .domain import (Attempt, AttemptStatus, EvaluationFailed, InvalidTransition, ValidationError)
from .evaluation.pipeline import EvaluationPipeline
from .jobs import JobRunner
from .storage import AttemptRepository

log = logging.getLogger(__name__)
SCORED = (AttemptStatus.COMPLETED, AttemptStatus.PARTIAL)


class PracticeService:
    def __init__(self, repo: AttemptRepository, pipeline: EvaluationPipeline, runner: JobRunner,
                 catalog: Optional[ProblemCatalog] = None):
        self.repo, self.pipeline, self.runner = repo, pipeline, runner
        self.catalog = catalog or ProblemCatalog()

    # ---- discovery -----------------------------------------------------
    def list_problems(self) -> list:
        return [p.public(detail=False) for p in self.catalog.list()]

    def get_problem(self, problem_id: str) -> dict:
        return self.catalog.get(problem_id).public()

    def list_formats(self) -> list:
        return self.pipeline.formats.describe()

    # ---- attempt lifecycle --------------------------------------------
    def start_attempt(self, learner_id: str, problem_id: str, based_on: Optional[str] = None) -> Attempt:
        self.catalog.get(problem_id)
        if not learner_id:
            raise ValidationError("learner_id is required.")
        previous = self.repo.list(learner_id, problem_id)
        attempt = Attempt(learner_id, problem_id, number=len(previous) + 1)
        if based_on:  # "try again": start from the previous design, not a blank page
            src = self.repo.get(based_on)
            if src.learner_id != learner_id or src.problem_id != problem_id:
                raise ValidationError("Can only base a new attempt on your own earlier attempt of this problem.")
            attempt.content, attempt.format, attempt.rationale, attempt.based_on = (
                src.content, src.format, src.rationale, src.id)
        self.repo.save(attempt)
        return attempt

    def save_draft(self, attempt_id: str, content: str, fmt: str, rationale: str = "") -> Attempt:
        attempt = self.repo.get(attempt_id)
        self.pipeline.formats.get(fmt)  # reject unknown formats early
        attempt.save_draft(content or "", fmt, rationale or "")
        self.repo.save(attempt)
        return attempt

    def submit(self, attempt_id: str) -> Attempt:
        attempt = self.repo.get(attempt_id)
        # Validate synchronously: unparseable work gets instant feedback and stays an editable draft.
        self.pipeline.parse(attempt.format, attempt.content)
        attempt.submit()
        self.repo.save(attempt)
        self.runner.submit(self._evaluate, attempt.id)
        return self.repo.get(attempt.id)

    def retry(self, attempt_id: str) -> Attempt:
        attempt = self.repo.get(attempt_id)
        if attempt.status not in (AttemptStatus.FAILED, AttemptStatus.PARTIAL):
            raise _invalid(attempt)
        self.runner.submit(self._evaluate, attempt.id)
        return self.repo.get(attempt.id)

    def _evaluate(self, attempt_id: str) -> None:
        attempt = self.repo.get(attempt_id)
        attempt.start_evaluation()  # rejects double-runs (EVALUATING/COMPLETED)
        self.repo.save(attempt)
        try:
            feedback = self.pipeline.run(self.catalog.get(attempt.problem_id), attempt.format,
                                         attempt.content, attempt.rationale)
            attempt.complete(feedback)
        except (ValidationError, EvaluationFailed) as e:
            attempt.fail(str(e))
        except Exception as e:  # never leave an attempt stuck in EVALUATING
            log.exception("evaluation crashed")
            attempt.fail(f"Unexpected evaluation error: {type(e).__name__}")
        self.repo.save(attempt)

    def recover_interrupted(self) -> int:
        """Call at startup: attempts left EVALUATING by a crash/restart become FAILED (retryable)."""
        stuck = self.repo.list_by_status(AttemptStatus.EVALUATING)
        for a in stuck:
            a.fail("Evaluation was interrupted (server restart). Press retry.")
            self.repo.save(a)
        return len(stuck)

    # ---- review & history ---------------------------------------------
    def get_attempt(self, attempt_id: str) -> dict:
        a = self.repo.get(attempt_id)
        d = a.to_dict()
        d["problem_title"] = self.catalog.get(a.problem_id).title
        prev = self._previous_scored(a)
        d["previous"] = ({"id": prev.id, "number": prev.number, "overall": prev.feedback.overall,
                          "scores": prev.feedback.scores} if prev else None)
        return d

    def _previous_scored(self, a: Attempt) -> Optional[Attempt]:
        earlier = [x for x in self.repo.list(a.learner_id, a.problem_id)
                   if x.number < a.number and x.status in SCORED and x.feedback]
        return earlier[-1] if earlier else None

    def history(self, learner_id: str, problem_id: Optional[str] = None) -> list:
        rows, last_scored = [], {}
        for a in self.repo.list(learner_id, problem_id):
            fb = a.feedback if a.status in SCORED else None
            prev = last_scored.get(a.problem_id)
            rows.append({
                "id": a.id, "problem_id": a.problem_id, "problem_title": self.catalog.get(a.problem_id).title,
                "number": a.number, "status": a.status.value, "format": a.format,
                "created_at": a.created_at, "overall": fb.overall if fb else None,
                "scores": fb.scores if fb else None,
                "delta": (fb.overall - prev) if (fb and prev is not None) else None,
                "error": a.error,
            })
            if fb:
                last_scored[a.problem_id] = fb.overall
        return list(reversed(rows))  # newest first


def _invalid(attempt: Attempt):
    return InvalidTransition(f"Attempt is {attempt.status.value}; only FAILED or PARTIAL attempts can be retried.")
