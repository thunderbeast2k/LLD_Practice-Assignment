"""Deterministic evaluators.

These are cheap, repeatable and explainable, so they own the *scores*. They judge
structure that can be checked objectively (are the core concepts there? is a god class
forming? is each variation point abstracted?). Anything needing judgement about
trade-offs is left to the optional LLM reviewer.

Design principle for "many valid solutions": rubric concepts are matched by alias,
alternatives get partial credit with an explanation, and findings are phrased as
questions/trade-offs unless the gap is objectively a gap.
"""
from __future__ import annotations

import re

from ..design_model import name_matches, tokens
from ..domain import Dimension, Finding, Severity
from .base import EvaluationContext, Evaluator, EvaluatorResult

GOD_METHODS, GOD_MEMBERS = 10, 16
VAGUE_TOKENS = {"manager", "helper", "util", "utils", "utility", "handler", "processor",
                "data", "info", "misc", "common", "thing", "stuff"}
VAGUE_METHODS = {"process", "handle", "doit", "do", "execute", "manage", "run_all", "dostuff"}


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


class CoverageEvaluator(Evaluator):
    name, kind, dimension = "coverage-rules", "deterministic", Dimension.COVERAGE.value

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorResult:
        p, d = ctx.problem, ctx.design
        f: list[Finding] = []
        req = [e for e in p.entities if e.required]
        found_req, found_opt = [], []
        for e in p.entities:
            hits = d.find(e.aliases)
            if hits and e.required:
                found_req.append(hits[0].name)
            elif hits:
                found_opt.append(hits[0].name)
            elif e.required:
                f.append(Finding(
                    self.dimension, Severity.ISSUE, f"No class for '{e.name}'",
                    f"The requirements need a concept of '{e.name}'. {e.hint} "
                    "You may model it under another name or as part of another class - if so, "
                    "be sure that class has a clear single responsibility.",
                    f"Add a dedicated class (e.g. {e.aliases[0].title()}) or explain in your rationale "
                    "why it is folded into another class.", ""))
        ent_ratio = len(found_req) / len(req) if req else 1.0
        if found_req or found_opt:
            f.append(Finding(self.dimension, Severity.STRENGTH, "Core concepts modelled",
                             "These requirement concepts are present: "
                             + ", ".join(found_req + found_opt) + ".", evidence=", ".join(found_req + found_opt)))

        found_b, missing_b = 0, []
        for b in p.behaviours:
            if d.mentions(b.keywords):
                found_b += 1
            else:
                missing_b.append(b)
                f.append(Finding(
                    self.dimension, Severity.ISSUE, f"Behaviour not visible: {b.description}",
                    "No method name in your design appears to cover this requirement.",
                    f"Add an operation for it (name ideas: {', '.join(b.keywords[:3])}) on the class that "
                    "owns the data it needs."))
        beh_ratio = found_b / len(p.behaviours) if p.behaviours else 1.0
        if not d.structured:
            f.append(Finding(self.dimension, Severity.SUGGESTION, "Design is unstructured",
                             "Classes were guessed from prose, so coverage is approximate.",
                             "Use `class`/`interface` declarations with `+ method()` lines."))
        return EvaluatorResult(f, self.dimension, _clamp(60 * ent_ratio + 40 * beh_ratio))


class ResponsibilityEvaluator(Evaluator):
    name, kind, dimension = "responsibility-rules", "deterministic", Dimension.RESPONSIBILITIES.value

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorResult:
        p, d = ctx.problem, ctx.design
        f: list[Finding] = []
        domain = [c for c in d.classes.values() if c.kind != "enum"]
        penalty = 0.0
        for c in domain:
            if len(c.methods) > GOD_METHODS or len(c.methods) + len(c.attributes) > GOD_MEMBERS:
                penalty += 20
                f.append(Finding(
                    self.dimension, Severity.ISSUE, f"'{c.name}' may be doing too much",
                    f"{c.name} has {len(c.methods)} methods and {len(c.attributes)} attributes - a sign it has "
                    "several reasons to change (a 'god class').",
                    "Group its methods by the data they use and extract each group into its own class "
                    "(or behind an interface).",
                    f"methods: {', '.join(c.methods[:6])}..."))
        flat = [c for c in domain if c.kind == "class"]
        anemic = [c for c in flat if not c.methods]
        if len(flat) >= 3 and len(anemic) / len(flat) >= 0.6 and d.structured:
            penalty += 25
            f.append(Finding(self.dimension, Severity.ISSUE, "Mostly data-only classes",
                             f"{len(anemic)} of {len(flat)} classes have no behaviour "
                             f"({', '.join(c.name for c in anemic[:5])}); all logic probably lives elsewhere.",
                             "Move behaviour next to the data it operates on (e.g. a Spot decides if a vehicle fits)."))
        misplaced = 0
        for b in p.behaviours:
            hits = d.methods_matching(b.keywords)
            if hits and b.owners and not any(name_matches(c.name, b.owners) for c, _ in hits):
                misplaced += 1
                where = ", ".join(sorted({c.name for c, _ in hits})[:3])
                f.append(Finding(
                    self.dimension, Severity.SUGGESTION, f"Is '{where}' the right home for: {b.description.lower()}?",
                    "This is usually owned by one of: " + ", ".join(b.owners) + ". Other placements can be valid "
                    "if that class holds the data the operation needs.",
                    "Check which class has the information required and would change when the rule changes.", where))
        penalty += 8 * min(misplaced, 3)
        score = _clamp(100 - penalty)
        if len(d.classes) < 2:
            f.append(Finding(self.dimension, Severity.ISSUE, "Everything is in one class",
                             "A single class owns all behaviour, so responsibilities can't be separated.",
                             "Split by reason-to-change: who holds data, who coordinates, who applies rules?"))
            score = min(score, 15)
        if score >= 90 and len(domain) >= 3:
            f.append(Finding(self.dimension, Severity.STRENGTH, "Responsibilities look well distributed",
                             "No oversized classes, and behaviour sits on plausible owners."))
        return EvaluatorResult(f, self.dimension, score)


class AbstractionEvaluator(Evaluator):
    name, kind, dimension = "abstraction-rules", "deterministic", Dimension.ABSTRACTION.value

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorResult:
        p, d = ctx.problem, ctx.design
        f: list[Finding] = []
        if not p.variation_points:
            return EvaluatorResult([], self.dimension, 100)
        total = 0.0
        rationale_words = re.findall(r"[A-Za-z]+", ctx.rationale)
        for vp in p.variation_points:
            cands = d.find(vp.aliases)
            with_impls = [c for c in cands if len(d.implementers(c.name)) >= 2]
            lonely_iface = [c for c in cands if c.kind == "interface" and len(d.implementers(c.name)) < 2]
            enums = [c for c in cands if c.kind == "enum"]
            if with_impls:
                c = with_impls[0]
                impls = ", ".join(i.name for i in d.implementers(c.name))
                total += 1.0
                f.append(Finding(self.dimension, Severity.STRENGTH, f"{vp.title}: extensible via {c.name}",
                                 f"{c.name} has multiple variants ({impls}), so new behaviour can be added without "
                                 "editing existing code.", evidence=impls))
            elif lonely_iface:
                total += 0.7
                c = lonely_iface[0]
                f.append(Finding(self.dimension, Severity.SUGGESTION, f"{vp.title}: '{c.name}' has fewer than 2 implementations",
                                 "The abstraction exists, but with 0-1 implementations it doesn't yet show how variation works.",
                                 "Add a second concrete implementation to demonstrate the extension point."))
            elif enums:
                total += 0.6
                f.append(Finding(self.dimension, Severity.SUGGESTION, f"{vp.title}: modelled as an enum ({enums[0].name})",
                                 "An enum is fine when variants differ only by data. If they differ by behaviour, "
                                 "switch statements will spread as variants grow.",
                                 "Keep the enum if behaviour is identical; otherwise move behaviour behind an interface "
                                 "(Strategy / State)."))
            elif cands:
                total += 0.35
                f.append(Finding(self.dimension, Severity.SUGGESTION, f"{vp.title}: concrete class only ({cands[0].name})",
                                 f"Scenario: {vp.scenario} With a single concrete class, this change means editing it.",
                                 "Extract an interface and implement the current rule as one variant."))
            else:
                justified = bool(rationale_words) and name_matches_any(rationale_words, vp.aliases)
                total += 0.5 if justified else 0
                if justified:
                    f.append(Finding(self.dimension, Severity.SUGGESTION, f"{vp.title}: addressed in rationale only",
                                     "Your rationale discusses this variation point but the design has no matching "
                                     "class/interface, so we can only give partial credit.",
                                     "Show the extension point in the design (an interface, function type or config object)."))
                else:
                    f.append(Finding(self.dimension, Severity.ISSUE, f"{vp.title}: no extension point",
                                     f"Scenario: {vp.scenario} Nothing in the design shows how that would be absorbed.",
                                     "Isolate this rule behind an interface (Strategy), or explain in your rationale why "
                                     "a simpler approach (config, function parameter) is enough."))
        return EvaluatorResult(f, self.dimension, _clamp(100 * total / len(p.variation_points)))


def name_matches_any(words, aliases) -> bool:
    return any(name_matches(w, aliases) for w in words)


class RelationshipEvaluator(Evaluator):
    name, kind, dimension = "relationship-rules", "deterministic", Dimension.RELATIONSHIPS.value

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorResult:
        d = ctx.design
        f: list[Finding] = []
        names = list(d.classes)
        if len(names) < 2:
            return EvaluatorResult(
                [Finding(self.dimension, Severity.ISSUE, "No relationships to evaluate",
                         "A design with one class has no collaborations.")], self.dimension, 20)
        edges = d.edges()
        incoming = {n: 0 for n in names}
        for src, outs in edges.items():
            for o in outs:
                incoming[o] += 1
        orphans = [n for n in names if not edges[n] and not incoming[n]]
        if d.structured and not any(edges.values()):
            f.append(Finding(self.dimension, Severity.ISSUE, "Classes are not connected",
                             "No class references, inherits from, or is used by another.",
                             "Show composition (fields typed as other classes), inheritance and method parameters."))
            return EvaluatorResult(f, self.dimension, 20)
        penalty = 0.0
        if d.structured:
            for n in orphans[:4]:
                penalty += 15
                f.append(Finding(self.dimension, Severity.ISSUE, f"'{n}' is isolated",
                                 "It neither uses nor is used by any other class, so it can't take part in the flow.",
                                 "Connect it (field, parameter or return type) or drop it if unnecessary."))
        for a in names:
            for b in edges[a]:
                mutual = a < b and a in edges[b] and b not in d.classes[a].bases and a not in d.classes[b].bases
                if mutual:
                    penalty += 5
                    f.append(Finding(self.dimension, Severity.SUGGESTION, f"'{a}' and '{b}' depend on each other",
                                     "Bidirectional dependencies make both classes hard to change or test alone.",
                                     "Keep the reference in one direction, or pass the needed data as a parameter."))
        deep = [n for n in names if d.inheritance_depth(n) > 3]
        for n in deep[:2]:
            penalty += 10
            f.append(Finding(self.dimension, Severity.SUGGESTION, f"Deep inheritance chain at '{n}'",
                             "More than 3 levels of inheritance are brittle.",
                             "Prefer composition: inject behaviour via an interface."))
        score = _clamp(100 - penalty)
        if score >= 95:
            f.append(Finding(self.dimension, Severity.STRENGTH, "Clear collaboration structure",
                             "Every class takes part in the design and dependencies run in one direction."))
        return EvaluatorResult(f, self.dimension, score)


class NamingEvaluator(Evaluator):
    name, kind, dimension = "naming-rules", "deterministic", Dimension.NAMING.value

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorResult:
        d = ctx.design
        f: list[Finding] = []
        penalty = 0.0
        for c in d.classes.values():
            vague = [t for t in tokens(c.name) if t in VAGUE_TOKENS]
            if len(c.name) < 3 or not c.name[0].isupper():
                penalty += 10
                f.append(Finding(self.dimension, Severity.ISSUE, f"'{c.name}' is not a clear class name",
                                 "Class names should be descriptive nouns in CamelCase.",
                                 "Rename to the domain concept it represents."))
            elif vague:
                penalty += 8
                f.append(Finding(self.dimension, Severity.SUGGESTION, f"'{c.name}' uses a vague word ('{vague[0]}')",
                                 "Names like Manager/Helper/Util often hide unclear responsibility. "
                                 "It's fine if the class truly only coordinates, but the name should say what it coordinates.",
                                 "Name it after the responsibility, e.g. 'SpotAllocator' rather than 'SpotManager'."))
        generic = sorted({m for c in d.classes.values() for m in c.methods if m.lower() in VAGUE_METHODS})
        if generic:
            penalty += 5 * min(len(generic), 3)
            f.append(Finding(self.dimension, Severity.SUGGESTION, "Generic method names",
                             f"Methods named {', '.join(generic)} don't say what they do.",
                             "Use intention-revealing verbs such as 'issueTicket' or 'calculateFee'.", ", ".join(generic)))
        score = _clamp(100 - penalty)
        if score == 100:
            f.append(Finding(self.dimension, Severity.STRENGTH, "Intention-revealing names",
                             "Class and method names read like the domain."))
        return EvaluatorResult(f, self.dimension, score)


def default_rule_evaluators() -> list:
    return [CoverageEvaluator(), ResponsibilityEvaluator(), AbstractionEvaluator(),
            RelationshipEvaluator(), NamingEvaluator()]
