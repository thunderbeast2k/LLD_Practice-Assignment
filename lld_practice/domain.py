"""Core domain model: errors, enums, value objects and the Attempt state machine."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ----------------------------------------------------------------- errors
class LLDError(Exception):
    """Base class for all expected, user-facing errors."""


class NotFoundError(LLDError):
    pass


class ValidationError(LLDError):
    """The submission cannot be evaluated (empty, syntax error, ...)."""


class InvalidTransition(LLDError):
    """Operation not allowed in the attempt's current status."""


class EvaluationFailed(LLDError):
    """Evaluation produced no usable result."""


# ------------------------------------------------------------------ enums
class AttemptStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"   # every evaluator succeeded
    PARTIAL = "PARTIAL"       # feedback available, but some evaluator failed
    FAILED = "FAILED"         # no feedback; learner can retry without re-writing


class Severity(str, Enum):
    ISSUE = "ISSUE"
    SUGGESTION = "SUGGESTION"
    STRENGTH = "STRENGTH"


class Dimension(str, Enum):
    COVERAGE = "coverage"
    RESPONSIBILITIES = "responsibilities"
    ABSTRACTION = "abstraction"
    RELATIONSHIPS = "relationships"
    NAMING = "naming"


DIMENSION_LABELS = {
    "coverage": "Requirements coverage",
    "responsibilities": "Responsibilities",
    "abstraction": "Abstraction & extensibility",
    "relationships": "Relationships",
    "naming": "Naming",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- feedback
@dataclass
class Finding:
    dimension: str
    severity: Severity
    title: str
    detail: str
    suggestion: str = ""
    evidence: str = ""
    source: str = "rules"  # "rules" | "ai"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(**{**d, "severity": Severity(d["severity"])})


@dataclass
class Feedback:
    overall: int
    scores: dict
    findings: list
    summary: str
    warnings: list = field(default_factory=list)   # things that went wrong (-> PARTIAL)
    notes: list = field(default_factory=list)      # informational
    evaluators: list = field(default_factory=list)  # [{name, kind, ok, error}]

    @property
    def partial(self) -> bool:
        return bool(self.warnings)

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "scores": self.scores,
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
            "warnings": self.warnings,
            "notes": self.notes,
            "evaluators": self.evaluators,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Feedback":
        return cls(
            overall=d["overall"], scores=d["scores"],
            findings=[Finding.from_dict(f) for f in d["findings"]],
            summary=d["summary"], warnings=d.get("warnings", []),
            notes=d.get("notes", []), evaluators=d.get("evaluators", []),
        )


# ----------------------------------------------------------------- attempt
@dataclass
class Attempt:
    learner_id: str
    problem_id: str
    number: int = 1
    format: str = "python"
    content: str = ""
    rationale: str = ""
    based_on: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: AttemptStatus = AttemptStatus.DRAFT
    feedback: Optional[Feedback] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    submitted_at: Optional[str] = None

    # -- state machine ---------------------------------------------------
    def _require(self, *allowed: AttemptStatus) -> None:
        if self.status not in allowed:
            names = "/".join(s.value for s in allowed)
            raise InvalidTransition(
                f"Attempt is {self.status.value}; this action needs status {names}."
            )

    def _touch(self) -> None:
        self.updated_at = _now()

    def save_draft(self, content: str, fmt: str, rationale: str = "") -> None:
        self._require(AttemptStatus.DRAFT)
        self.content, self.format, self.rationale = content, fmt, rationale
        self._touch()

    def submit(self) -> None:
        self._require(AttemptStatus.DRAFT)
        if not self.content.strip():
            raise ValidationError("Nothing to submit: the design is empty.")
        self.status = AttemptStatus.SUBMITTED
        self.error = None
        self.submitted_at = _now()
        self._touch()

    def start_evaluation(self) -> None:
        # FAILED / PARTIAL may be re-evaluated (retry) without rewriting anything.
        self._require(AttemptStatus.SUBMITTED, AttemptStatus.FAILED, AttemptStatus.PARTIAL)
        self.status, self.error = AttemptStatus.EVALUATING, None
        self._touch()

    def complete(self, feedback: Feedback) -> None:
        self._require(AttemptStatus.EVALUATING)
        self.feedback = feedback
        self.status = AttemptStatus.PARTIAL if feedback.partial else AttemptStatus.COMPLETED
        self._touch()

    def fail(self, error: str) -> None:
        self._require(AttemptStatus.EVALUATING)
        self.status, self.error = AttemptStatus.FAILED, error
        self._touch()

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id, "learner_id": self.learner_id, "problem_id": self.problem_id,
            "number": self.number, "format": self.format, "content": self.content,
            "rationale": self.rationale, "based_on": self.based_on,
            "status": self.status.value, "error": self.error,
            "feedback": self.feedback.to_dict() if self.feedback else None,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "submitted_at": self.submitted_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Attempt":
        d = dict(d)
        d["status"] = AttemptStatus(d["status"])
        d["feedback"] = Feedback.from_dict(d["feedback"]) if d.get("feedback") else None
        return cls(**d)
