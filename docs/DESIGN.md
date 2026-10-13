# Design note

## MVP and user flow
`Problem list → Problem brief (requirements, assumptions, "think first" prompts) → Attempt editor
(format + design + rationale) → Submit → status (SUBMITTED → EVALUATING → COMPLETED/PARTIAL/FAILED) →
Feedback → Try again (new attempt prefilled) → History with score deltas.`

## Answers to the design questions

**What must a learner provide?** A *structured* design (classes/interfaces, their methods and fields, and the
relationships between them) plus a short *rationale*. Prose alone can't be checked; code bodies are irrelevant
for LLD, so skeletons with `pass` are enough. The Python format is parsed with `ast`; the text outline is a
forgiving line grammar. Both produce the same `DesignModel`.

**What makes feedback useful when many designs are valid?** (1) Rubrics describe *concepts* (entities,
behaviours, variation points) matched by alias, not class names or one reference diagram. (2) Alternatives get
partial credit with a trade-off explanation (e.g. an enum for pricing: fine if behaviour is identical, risky if
it differs). (3) Placement findings are phrased as questions ("is X the right home for Y?") and say other
placements can be valid. (4) Every finding has detail + suggestion + evidence; strengths are reported too.
(5) The rationale can earn partial credit and is what the LLM reviews.

**Deterministic vs. LLM?** Deterministic (own the numbers): coverage, god/anemic classes, variation-point
abstraction, connectivity/cycles/inheritance depth, naming. They are repeatable, free, explainable and testable.
LLM (commentary only): trade-offs, quality of reasoning, alternative approaches, tone. Its JSON is parsed
strictly, capped, the submission is fenced as data (prompt-injection hygiene), and it cannot alter scores.

**Extensibility.** Two seams, both small interfaces:
- `SubmissionFormat.parse(content) -> DesignModel` (+ `FormatRegistry.register`). A Mermaid/PlantUML/Java format
  is one class; evaluators don't change.
- `Evaluator.evaluate(ctx) -> EvaluatorResult` appended to the pipeline. An embedding-similarity or
  test-harness evaluator is one class; formats don't change.
Also swappable behind interfaces: `AttemptRepository` (SQLite/in-memory), `JobRunner` (inline/thread pool),
`LLMClient` (Anthropic/fake). `config.build_service` is the only place concrete classes are chosen.

**Slow or failing evaluation.** Submit validates synchronously (empty, too long, syntax errors → 422, attempt
stays an editable DRAFT) and then enqueues evaluation on a `JobRunner`; the UI polls status.
- Each evaluator runs in isolation. An LLM failure/malformed output → **PARTIAL**: rule-based feedback is still
  delivered with a warning. Overall score is renormalised over the dimensions that did run.
- If nothing can score → **FAILED** with a message; the design is never lost; `retry` re-runs without rewriting.
- Unexpected exceptions also end in FAILED (never stuck in EVALUATING); `recover_interrupted()` at startup turns
  attempts orphaned by a restart into retryable FAILED. LLM HTTP calls have a timeout and one retry.
- Invalid transitions (double submit, edit after submit, retry a completed attempt) → 409.

## Domain model (important classes)
- `Attempt` - aggregate with the state machine (`DRAFT→SUBMITTED→EVALUATING→COMPLETED|PARTIAL|FAILED`,
  retry from FAILED/PARTIAL). Transition rules live on the entity, not scattered in services.
- `Feedback`, `Finding` - value objects (scores per dimension, severity-tagged findings, warnings, notes).
- `Problem`, `Entity`, `Behaviour`, `VariationPoint` - catalogue + rubric as immutable data.
- `DesignModel`, `ClassInfo` - parsed design; alias/token matching, implementers, edges, inheritance depth.
- `SubmissionFormat` (Strategy) → `PythonFormat`, `TextFormat`; `FormatRegistry`.
- `Evaluator` (Strategy) → `CoverageEvaluator`, `ResponsibilityEvaluator`, `AbstractionEvaluator`,
  `RelationshipEvaluator`, `NamingEvaluator`, `LLMReviewEvaluator`.
- `EvaluationPipeline` - runs evaluators, isolates failures, aggregates (weights: coverage 30, responsibilities 25,
  abstraction 25, relationships 10, naming 10).
- `PracticeService` - orchestrates the learner journey; `AttemptRepository`, `JobRunner` - infrastructure ports.

## Key trade-offs
- **Heuristic rubrics vs. full semantic understanding**: cheap and explainable, but they judge shape, not
  correctness. The LLM and rationale cover some of the gap; the limitation is stated in feedback notes.
- **Structured input vs. free-form diagrams**: less expressive, far more reliably evaluable. A diagram format can
  be added later through `SubmissionFormat`.
- **Rules own the score**: slightly less "smart" but trustworthy and stable between runs.
- **Monolith + thread pool + SQLite**: enough for the prototype; to scale, swap `JobRunner` for a queue and
  `AttemptRepository` for Postgres - both are behind interfaces already. No HLD work beyond that.
