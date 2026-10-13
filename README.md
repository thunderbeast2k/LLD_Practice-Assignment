# LLD_Practice-Assignment
# LLD Practice Platform

A small, working practice loop for Low-Level Design:

**Choose problem → Think / design → Submit → Get feedback → Review → Try again**

Python 3.10+, **standard library only** (no installs). A simple monolith: JSON API + one-page UI + SQLite.

## Run

```bash
python -m lld_practice                 # http://127.0.0.1:8000  (data in ./lld_practice.db)
python -m lld_practice --port 9000 --db /tmp/demo.db
```

Open the URL, pick a problem, write a design (Python skeleton or text outline), submit, read the feedback,
press **Try again from this design**, and watch the score delta against your previous attempt.
Try the sample designs in `examples/` (a good one, a "god class", and a text-outline version).

### Optional AI review
```bash
export ANTHROPIC_API_KEY=sk-...        # enables the LLM reviewer
export LLD_LLM_MODEL=claude-sonnet-5-5 # optional, model id is configurable
export LLD_LLM_TIMEOUT=30              # optional, seconds
```
Without a key the app works fully on rule-based feedback and says so in the feedback notes.

## Tests
```bash
python -m unittest discover -s tests -t .      # 57 tests, <1s, no network
```
Covers parsing, each evaluator (good design, weak design, valid alternatives), the pipeline's degradation
paths, the LLM client's untrusted-output handling, the attempt state machine, the full journey, storage,
retry/recovery, and the HTTP API (including error codes and path traversal).

## Layout
```
lld_practice/
  domain.py            Attempt state machine, Feedback/Finding, errors
  design_model.py      Format-independent DesignModel (ClassInfo, alias matching)
  parsing.py           SubmissionFormat strategy: PythonFormat, TextFormat, registry
  catalog.py           Problems + rubrics (concepts/behaviours/variation points)
  evaluation/
    base.py            Evaluator interface, context, result
    rules.py           5 deterministic evaluators (own the scores)
    llm.py             LLMClient protocol, Anthropic client, LLMReviewEvaluator (qualitative only)
    pipeline.py        Failure-isolated run + weighted aggregation
  storage.py           AttemptRepository: InMemory + SQLite
  jobs.py              JobRunner: Inline + ThreadRunner
  service.py           PracticeService (the learner journey)
  server.py / static/  stdlib HTTP adapter + UI
docs/RESEARCH.md  docs/DESIGN.md  AI_USAGE.md
```

## Key decisions (details in docs/DESIGN.md)
- **Rules own the score; the LLM only adds commentary.** Scores stay repeatable and explainable; the LLM
  covers trade-offs and the learner's rationale, and its output is parsed defensively.
- **Rubrics describe concepts, not one answer.** Alias matching + partial credit (e.g. enum vs. Strategy) so
  multiple valid designs score well; findings explain the trade-off rather than just "wrong".
- **New formats / evaluators plug in** via `SubmissionFormat` and `Evaluator`; nothing else changes.
- **Failure is a first-class state:** `COMPLETED / PARTIAL / FAILED`, retry without rewriting, restart recovery.

## Limitations
- Rule-based checks are name/structure heuristics: they can't verify that logic is *correct*, only that the
  design has the expected shape. Unusual-but-valid naming may be under-credited (the LLM and rationale help).
- Four problems; rubrics are hand-written.
- No auth (a learner id is generated in the browser and sent as `X-Learner-Id`), no diagram upload.
- Thread-pool jobs live in-process; a queue would replace `ThreadRunner` at scale.
