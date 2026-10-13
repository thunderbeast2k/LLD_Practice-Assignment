"""Submission formats. Each format = one SubmissionFormat (parser + editor template).

To add a format (e.g. Mermaid/PlantUML class diagram, Java, JSON), implement
`SubmissionFormat.parse` -> DesignModel and register it; nothing else changes.
"""
from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod

from .design_model import ClassInfo, DesignModel, tokens
from .domain import ValidationError

MIN_CHARS, MAX_CHARS = 30, 60_000


class SubmissionFormat(ABC):
    id: str
    label: str
    description: str
    template: str

    def parse(self, content: str) -> DesignModel:
        content = content or ""
        if len(content.strip()) < MIN_CHARS:
            raise ValidationError(
                f"The design is too short to evaluate (need at least {MIN_CHARS} characters).")
        if len(content) > MAX_CHARS:
            raise ValidationError(f"The design is too long (limit {MAX_CHARS} characters).")
        return self._parse(content)

    @abstractmethod
    def _parse(self, content: str) -> DesignModel: ...

    def describe(self) -> dict:
        return {"id": self.id, "label": self.label,
                "description": self.description, "template": self.template}


# ------------------------------------------------------------------ python
_ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}
_ABSTRACT_BASES = {"ABC", "Protocol"}


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


class PythonFormat(SubmissionFormat):
    id = "python"
    label = "Python skeleton"
    description = ("Class/interface skeletons in Python. Method bodies can be `pass`; "
                   "what matters is the classes, their responsibilities and relationships.")
    template = '''from abc import ABC, abstractmethod
from enum import Enum


# Sketch the classes, interfaces and enums. Bodies can be `pass`.
class Example(ABC):
    @abstractmethod
    def do_something(self) -> None: ...
'''

    def _parse(self, content: str) -> DesignModel:
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            raise ValidationError(f"Python syntax error on line {e.lineno}: {e.msg}") from e
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        if not nodes:
            raise ValidationError("No classes found. Define at least one class or interface.")
        declared = {n.name for n in nodes}
        classes: dict[str, ClassInfo] = {}
        for node in nodes:
            bases = [b for b in (_base_name(x) for x in node.bases) if b]
            methods, attrs, abstract = [], [], False
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("__") and item.name.endswith("__"):
                        pass
                    else:
                        methods.append(item.name)
                    for deco in item.decorator_list:
                        if _base_name(deco) in {"abstractmethod", "abstractproperty"}:
                            abstract = True
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    attrs.append(item.target.id)
                elif isinstance(item, ast.Assign):
                    attrs += [t.id for t in item.targets if isinstance(t, ast.Name)]
            for sub in ast.walk(node):  # self.x = ... anywhere in the class
                targets = []
                if isinstance(sub, ast.Assign):
                    targets = sub.targets
                elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
                    targets = [sub.target]
                flat = []
                for t in targets:  # unpack `self.a, self.b = ...`
                    flat += list(t.elts) if isinstance(t, (ast.Tuple, ast.List)) else [t]
                for t in flat:
                    if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                            and t.value.id == "self" and t.attr not in attrs):
                        attrs.append(t.attr)
            refs = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            # forward references written as strings in annotations
            for sub in ast.walk(node):
                ann = getattr(sub, "annotation", None) or getattr(sub, "returns", None)
                if ann is not None:
                    for c in ast.walk(ann):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            refs.update(re.findall(r"[A-Za-z_]\w*", c.value))
            if any(b in _ENUM_BASES for b in bases):
                kind = "enum"
            elif abstract or any(b in _ABSTRACT_BASES for b in bases):
                kind = "interface"
            else:
                kind = "class"
            bases = [b for b in bases if b in declared]
            refs = {r for r in refs if r in declared and r != node.name}
            classes[node.name] = ClassInfo(node.name, kind, methods, attrs, bases, refs)
        return DesignModel(classes, content, self.id)


# -------------------------------------------------------------------- text
_DECL = re.compile(
    r"^\s*(?:(abstract)\s+)?(class|interface|enum)\s+([A-Za-z_]\w*)\s*(.*)$", re.I)
_EXTENDS = re.compile(r"\bextends\s+([\w\s,]+?)(?=\bimplements\b|$)", re.I)
_IMPLEMENTS = re.compile(r"\bimplements\s+([\w\s,]+)$", re.I)
_PAREN_BASES = re.compile(r"[(:]\s*([\w\s,]+)\)?\s*$")
_CAMEL = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b|\b[A-Z][a-z]{2,}\b")


class TextFormat(SubmissionFormat):
    id = "text"
    label = "Text outline"
    description = ("A lightweight outline: `class|interface|enum Name [extends A] [implements B, C]` "
                   "followed by indented `+ method(args)` and `- attribute: Type` lines.")
    template = '''interface PricingStrategy
  + calculate(ticket): Money

class ParkingLot
  - floors: List<Floor>
  - pricing: PricingStrategy
  + park(vehicle): Ticket

class FlatRatePricing implements PricingStrategy
  + calculate(ticket): Money

// Free-form notes are fine too: lines that are not indented are ignored.
'''

    @staticmethod
    def _names(s: str) -> list[str]:
        return [n for n in re.findall(r"[A-Za-z_]\w*", s)]

    def _parse(self, content: str) -> DesignModel:
        classes: dict[str, ClassInfo] = {}
        member_lines: dict[str, list[str]] = {}
        cur = None
        for line in content.splitlines():
            if not line.strip() or line.strip().startswith(("//", "#!")):
                continue
            m = _DECL.match(line)
            if m:
                abstract, kind, name, rest = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
                bases: list[str] = []
                for rx in (_EXTENDS, _IMPLEMENTS):
                    found = rx.search(rest)
                    if found:
                        bases += self._names(found.group(1))
                if not bases and (pb := _PAREN_BASES.search(rest)):
                    bases += self._names(pb.group(1))
                if abstract and kind == "class":
                    kind = "interface"
                cur = ClassInfo(name, kind, bases=bases)
                classes[name] = cur
                member_lines[name] = []
                continue
            is_member = line[:1] in (" ", "\t") or line.lstrip()[:1] in "+-*~"
            if cur is not None and is_member:
                member_lines[cur.name].append(line.strip().lstrip("+-*~# ").strip())
            elif not is_member:
                cur = None  # free-form prose ends the current class block
        structured = bool(classes)
        notes: list[str] = []
        if not structured:  # fall back to guessing from prose
            guessed = sorted({w for w in _CAMEL.findall(content)})
            if len(guessed) < 2:
                raise ValidationError(
                    "Couldn't find any classes. Use `class Name` / `interface Name` lines "
                    "followed by indented `+ method()` lines (see the template).")
            classes = {g: ClassInfo(g) for g in guessed}
            member_lines = {g: [] for g in guessed}
            notes.append("No `class`/`interface` declarations found; class names were guessed "
                         "from free text, so structural feedback is limited.")
        declared = set(classes)
        for name, lines in member_lines.items():
            c = classes[name]
            for ln in lines:
                if not ln:
                    continue
                refs = {w for w in re.findall(r"[A-Za-z_]\w*", ln) if w in declared and w != name}
                c.references |= refs
                if "(" in ln:
                    head = ln.split("(")[0].strip().split()
                    if head:
                        c.methods.append(head[-1])
                else:
                    c.attributes.append(re.split(r"[:=\s]", ln, 1)[0] or ln)
        return DesignModel(classes, content, self.id, structured, notes)


# ---------------------------------------------------------------- registry
class FormatRegistry:
    def __init__(self, formats=None):
        self._formats: dict[str, SubmissionFormat] = {}
        for f in formats or [PythonFormat(), TextFormat()]:
            self.register(f)

    def register(self, fmt: SubmissionFormat) -> None:
        self._formats[fmt.id] = fmt

    def get(self, fmt_id: str) -> SubmissionFormat:
        try:
            return self._formats[fmt_id]
        except KeyError:
            raise ValidationError(
                f"Unknown submission format '{fmt_id}'. Available: {', '.join(self._formats)}")

    def describe(self) -> list[dict]:
        return [f.describe() for f in self._formats.values()]
