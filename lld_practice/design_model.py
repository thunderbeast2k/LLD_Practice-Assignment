"""Format-independent representation of a learner's design.

Every submission format is parsed into a DesignModel; evaluators only ever see this,
so new formats never touch evaluation code and vice versa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def tokens(name: str) -> list[str]:
    """'ParkingSpot' / 'parking_spot' -> ['parking', 'spot']"""
    return [t.lower() for t in _TOKEN_RE.findall(name)]


def norm(name: str) -> str:
    return "".join(tokens(name))


def name_matches(name: str, aliases: Iterable[str]) -> bool:
    """Alias-based, token-aware match. Deliberately tolerant: there is no single
    'correct' class name, so we match concepts rather than spellings."""
    toks = tokens(name)
    joined = "".join(toks)
    for alias in aliases:
        a = norm(alias)
        if not a:
            continue
        if joined == a or a in toks:
            return True
        if len(a) >= 4 and any(t.startswith(a) for t in toks):
            return True
        if len(a) >= 7 and a in joined:
            return True
    return False


@dataclass
class ClassInfo:
    name: str
    kind: str = "class"  # class | interface | enum
    methods: list = field(default_factory=list)
    attributes: list = field(default_factory=list)
    bases: list = field(default_factory=list)
    references: set = field(default_factory=set)


@dataclass
class DesignModel:
    classes: dict
    raw: str = ""
    format: str = "python"
    structured: bool = True  # False when we could only guess class names from prose
    notes: list = field(default_factory=list)

    def find(self, aliases: Iterable[str]) -> list:
        aliases = list(aliases)
        return [c for c in self.classes.values() if name_matches(c.name, aliases)]

    def implementers(self, name: str) -> list:
        return [c for c in self.classes.values() if name in c.bases]

    def methods_matching(self, keywords: Iterable[str]) -> list:
        keywords = list(keywords)
        return [(c, m) for c in self.classes.values() for m in c.methods
                if name_matches(m, keywords)]

    def mentions(self, keywords: Iterable[str]) -> bool:
        """Does the design provide behaviour matching these keywords?"""
        if self.structured:
            return bool(self.methods_matching(keywords))
        words = re.findall(r"[A-Za-z]+", self.raw)
        keywords = list(keywords)
        return any(name_matches(w, keywords) for w in words)

    def out_edges(self, name: str) -> set:
        c = self.classes[name]
        return {r for r in (set(c.bases) | c.references) if r in self.classes and r != name}

    def edges(self) -> dict:
        return {n: self.out_edges(n) for n in self.classes}

    def inheritance_depth(self, name: str) -> int:
        depth, seen, cur = 0, {name}, name
        while True:
            parents = [b for b in self.classes[cur].bases if b in self.classes and b not in seen]
            if not parents:
                return depth
            cur = parents[0]
            seen.add(cur)
            depth += 1
