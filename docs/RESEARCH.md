# Research note

*Method: a brief web scan (October 2026) of tools and content aimed at LLD practice, then reasoning about gaps.
Tool descriptions come from each product's own pages and may change.*

## The learner problem
LLD practice is easy to start and hard to evaluate. A learner can sketch a Parking Lot and still not know whether
responsibilities are well placed, whether the design survives a new requirement, or whether it is merely *different*
from a reference answer. Typical failure modes: (1) no feedback at all, (2) feedback only as a "model solution" to
compare with, (3) one-and-done solving with no sense of progress. There is also rarely a single correct design in LLD,
so useful feedback has to judge reasoning and structure, not match an answer key. The valuable unit is the *loop*:
attempt, feedback, revision, tracked over time.

## Existing approaches researched
| Tool / approach | What it offers (per its own pages) | Gap relevant to this assignment |
|---|---|---|
| **Hello Interview - Guided Practice** | Step-by-step practice for System Design, Low-Level Design and AI-enabled coding, with instant AI feedback | Closest to our goal. Feedback is a black box to the learner: no visible split between deterministic checks and AI judgement, and no stated way to extend formats or evaluators |
| **LowLevelDesign Mastery** | Visual-first LLD platform: interactive playground, class-diagram blueprints, multi-language code, AI reviews, flashcards and cheat sheets | Content-heavy (theory + playground). Emphasis on running code and visual explanations rather than explainable, per-dimension structural feedback and attempt-over-attempt improvement |
| **Testlify - AI interviews (LLD)** | Recruiter-side AI-scored video interviews covering OOD principles, class/interface design and patterns | Built for *assessing candidates*, not for repeated learner practice; scores are per spoken answer, not tied to the learner's actual class structure |
| **Course/article content (e.g. DesignGurus-style guides)** | Explains what LLD interviews expect: requirements clarification, class design, patterns, edge cases, and common problems (Parking Lot, Library, etc.) | Passive reading; nothing evaluates the learner's own design. Useful, though, for choosing problems and the rubric (concepts, patterns, extensibility) |
| **Coding judges / linters / diagram tools (general knowledge)** | Deterministic pass/fail, code-smell detection, free-form diagramming | Tests and linters can't judge responsibilities or extensibility of a *design*; diagrams are hard to evaluate automatically |

## Key gaps
1. **Explainable evaluation of structure**: responsibilities, abstractions, relationships - not only "does the code run".
2. **Many valid answers**: feedback must be framed around concepts and trade-offs rather than a reference diagram.
3. **Trust**: a visible hybrid - deterministic checks for repeatable scores, an LLM for judgement - clearly labelled.
4. **Improvement over time**: attempt history and score deltas turn solving into practice, not a one-off.
5. **Graceful degradation**: AI evaluation is slow and can fail; the learner should never lose work or hit a dead end.

## Product direction (the MVP)
A focused practice loop for four classic problems. The learner provides a **structured design** (class/interface
skeleton in Python, or a lightweight text outline) plus a short **rationale** (assumptions, patterns, trade-offs).
Structure makes deterministic checks possible; the rationale gives the reviewer something to judge reasoning on.

- **Feedback = per-dimension scores + findings** (issue / suggestion / strength), each with *why* and *what to try*.
- **Deterministic**: concept coverage, behaviour presence, god/anemic classes, variation-point abstraction,
  connectivity, naming. **LLM**: trade-offs, reasoning, valid alternatives - it never changes scores.
- **Review & retry**: history with deltas; "Try again from this design" starts from the previous attempt.
- **Out of scope on purpose**: LMS features, auth, a diagram canvas, executing learner code, scale-out infrastructure.
