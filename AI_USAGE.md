# AI usage

AI assistance (Claude) was used for scaffolding, code and drafting. The entries below record the meaningful
decisions: what the AI proposed, what was accepted/rejected, and why.


1. **Evaluation split - who owns the score?**
   *AI suggested* having an LLM grade the whole design and return a 0-100 score.
   *Decision:* rejected as the primary path. Deterministic evaluators own the scores (repeatable, free, testable);
   the LLM only adds trade-off commentary and cannot change numbers. *Why:* LLM scores drift between runs and are
   hard to defend; the assignment asks explicitly which parts should be deterministic.

2. **Handling "many valid solutions".**
   *AI's first sketch* matched exact class names from a reference solution. *Decision:* replaced with concept
   rubrics (aliases, token-aware matching, partial credit for enum/concrete alternatives, placement findings phrased
   as questions). *Why:* exact-name matching would punish correct designs that are named differently.

3. **Failure model.**
   *AI suggested* a retry loop around the LLM call. *Accepted in part:* one HTTP retry only. Added the
   `COMPLETED / PARTIAL / FAILED` states, per-evaluator isolation, score renormalisation, retry-without-rewrite and
   restart recovery. *Rejected:* queues/workers/circuit breakers as out of scope ("don't turn it into a
   distributed-systems project").

4. **Tests found real bugs in AI-written code.**
   Writing failure/edge tests exposed two defects in generated code: tuple assignments
   (`self.a, self.b = ...`) were not captured as attributes, and a single-class design skipped god-class
   detection. Both were fixed and are now covered by tests. *Lesson:* treat generated code as a draft; the tests
   are what make it trustworthy.

5. **Dependencies.**
   *AI proposed* Flask + SQLAlchemy + pytest. *Decision:* stdlib only (`http.server`, `sqlite3`, `ast`,
   `unittest`) so the project runs with zero installs; framework choice isn't the point of an LLD exercise.
