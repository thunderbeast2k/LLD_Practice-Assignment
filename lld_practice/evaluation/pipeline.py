"""Runs evaluators in isolation and aggregates them into a Feedback."""
from __future__ import annotations

import logging

from ..design_model import DesignModel
from ..domain import (DIMENSION_LABELS, EvaluationFailed, Feedback, Finding, Severity)
from ..parsing import FormatRegistry
from .base import EvaluationContext, Evaluator

log = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {"coverage": 30, "responsibilities": 25, "abstraction": 25,
                   "relationships": 10, "naming": 10}
SEVERITY_ORDER = {Severity.ISSUE: 0, Severity.SUGGESTION: 1, Severity.STRENGTH: 2}
STANDING_NOTE = ("Scores reward sound structure, not one 'right' answer: concepts are matched by meaning, "
                 "and alternative approaches earn partial credit with an explanation.")


class EvaluationPipeline:
    def __init__(self, formats: FormatRegistry, evaluators: list[Evaluator], ai_enabled: bool | None = None,
                 weights: dict | None = None):
        self.formats, self.evaluators = formats, evaluators
        self.weights = weights or DEFAULT_WEIGHTS
        self.ai_enabled = ai_enabled if ai_enabled is not None else any(e.kind == "ai" for e in evaluators)

    def parse(self, fmt: str, content: str) -> DesignModel:
        """Fast, synchronous validation used at submit time. Raises ValidationError."""
        return self.formats.get(fmt).parse(content)

    def run(self, problem, fmt: str, content: str, rationale: str = "") -> Feedback:
        design = self.parse(fmt, content)
        ctx = EvaluationContext(problem, design, content, rationale)
        scores: dict[str, float] = {}
        findings: list[Finding] = []
        summaries: list[str] = []
        report, warnings = [], []
        for ev in self.evaluators:
            try:
                res = ev.evaluate(ctx)
            except Exception as e:  # one broken evaluator must not sink the attempt
                log.warning("evaluator %s failed: %s", ev.name, e)
                report.append({"name": ev.name, "kind": ev.kind, "ok": False, "error": str(e)[:200]})
                warnings.append(f"{ev.name} could not run ({str(e)[:120]}). Retry later to include it.")
                continue
            report.append({"name": ev.name, "kind": ev.kind, "ok": True, "error": None})
            findings += res.findings
            if res.dimension and res.score is not None:
                scores[res.dimension] = res.score
            if res.summary:
                summaries.append(res.summary)
        if not scores:
            raise EvaluationFailed("No scoring evaluator succeeded; please retry.")
        total_w = sum(self.weights.get(k, 0) for k in scores) or 1
        overall = round(sum(v * self.weights.get(k, 0) for k, v in scores.items()) / total_w)
        findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
        notes = [STANDING_NOTE] + (design.notes or [])
        if not self.ai_enabled:
            notes.append("AI review is not enabled here (set ANTHROPIC_API_KEY); you are seeing rule-based feedback only.")
        return Feedback(overall, {k: round(v) for k, v in scores.items()}, findings,
                        " ".join([self._summary(scores)] + summaries[:1]),
                        warnings, notes, report)

    @staticmethod
    def _summary(scores: dict) -> str:
        best = max(scores, key=scores.get)
        worst = min(scores, key=scores.get)
        if best == worst:
            return f"{DIMENSION_LABELS.get(best, best)} scored {round(scores[best])}/100."
        return (f"Strongest area: {DIMENSION_LABELS.get(best, best)} ({round(scores[best])}). "
                f"Biggest opportunity: {DIMENSION_LABELS.get(worst, worst)} ({round(scores[worst])}).")
