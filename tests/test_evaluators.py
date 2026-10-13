import unittest

from lld_practice.catalog import ProblemCatalog
from lld_practice.design_model import name_matches
from lld_practice.evaluation.base import EvaluationContext
from lld_practice.evaluation.rules import (AbstractionEvaluator, CoverageEvaluator, NamingEvaluator,
                                           RelationshipEvaluator, ResponsibilityEvaluator)
from lld_practice.domain import Severity
from lld_practice.parsing import PythonFormat, TextFormat
from tests.helpers import example

PROBLEM = ProblemCatalog().get("parking-lot")


def ctx(src, fmt=PythonFormat(), rationale=""):
    return EvaluationContext(PROBLEM, fmt.parse(src), src, rationale)


def titles(res, sev):
    return [f.title for f in res.findings if f.severity == sev]


class MatchingTests(unittest.TestCase):
    def test_token_aware_matching(self):
        self.assertTrue(name_matches("ParkingLot", ["lot"]))
        self.assertFalse(name_matches("Slot", ["lot"]))          # no substring false positives
        self.assertFalse(name_matches("unparkVehicle", ["park"]))  # 'unpark' != 'park'
        self.assertTrue(name_matches("parkVehicle", ["park"]))
        self.assertTrue(name_matches("calculate_fee", ["fee"]))


class GoodDesignTests(unittest.TestCase):
    def setUp(self):
        self.c = ctx(example("parking_lot_good.py"))

    def test_scores_high_everywhere(self):
        for ev in (CoverageEvaluator(), ResponsibilityEvaluator(), AbstractionEvaluator(),
                   RelationshipEvaluator(), NamingEvaluator()):
            res = ev.evaluate(self.c)
            self.assertGreaterEqual(res.score, 85, f"{ev.name}: {res.score} {[f.title for f in res.findings]}")
            self.assertEqual(res.dimension, ev.dimension)

    def test_abstraction_strengths_name_the_variants(self):
        res = AbstractionEvaluator().evaluate(self.c)
        strengths = [f for f in res.findings if f.severity == Severity.STRENGTH]
        self.assertTrue(any("HourlyPricing" in f.evidence for f in strengths))


class WeakDesignTests(unittest.TestCase):
    def setUp(self):
        self.c = ctx(example("parking_lot_god_class.py"))

    def test_god_class_flagged(self):
        res = ResponsibilityEvaluator().evaluate(self.c)
        self.assertTrue(any("ParkingLotManager" in t for t in titles(res, Severity.ISSUE)))
        self.assertLessEqual(res.score, 20)

    def test_missing_entities_and_no_extension_points(self):
        cov = CoverageEvaluator().evaluate(self.c)
        self.assertTrue(any("Ticket" in t for t in titles(cov, Severity.ISSUE)))
        self.assertLess(cov.score, 60)
        ab = AbstractionEvaluator().evaluate(self.c)
        self.assertEqual(ab.score, 0)

    def test_naming_flags_vague_names(self):
        res = NamingEvaluator().evaluate(self.c)
        self.assertTrue(any("vague" in t for t in titles(res, Severity.SUGGESTION)))
        self.assertTrue(any("Generic method" in t for t in titles(res, Severity.SUGGESTION)))


class ValidAlternativesTests(unittest.TestCase):
    ENUM_ONLY = '''
from enum import Enum
class VehicleType(Enum):
    CAR = 1
class PricingRule(Enum):
    HOURLY = 1
class ParkingSpot:
    def occupy(self, v: "VehicleType"): ...
    def vacate(self): ...
class Ticket:
    spot: ParkingSpot
class ParkingLot:
    rule: PricingRule
    spots: list[ParkingSpot]
    def park(self, v: VehicleType) -> Ticket: ...
    def unpark(self, t: Ticket): ...
'''

    def test_enum_gets_partial_credit_with_tradeoff_explanation(self):
        res = AbstractionEvaluator().evaluate(ctx(self.ENUM_ONLY))
        self.assertTrue(30 < res.score < 90)
        self.assertTrue(any("enum" in f.title.lower() for f in res.findings))

    def test_rationale_earns_partial_credit_when_design_lacks_class(self):
        src = "class ParkingLot:\n    def park(self): ...\nclass Ticket:\n    pass  # minimal design\n"
        without = AbstractionEvaluator().evaluate(ctx(src)).score
        with_r = AbstractionEvaluator().evaluate(ctx(src, rationale="Pricing is injected as a function, so rules can change")).score
        self.assertGreater(with_r, without)

    def test_text_format_scores_like_python(self):
        res = AbstractionEvaluator().evaluate(ctx(example("parking_lot_text.txt"), TextFormat()))
        self.assertGreaterEqual(res.score, 30)  # pricing + vehicle variation recognised


class RelationshipTests(unittest.TestCase):
    def test_isolated_class_and_cycle(self):
        src = ("class A:\n    b: 'B'\nclass B:\n    a: A\nclass Lonely:\n    def x(self): ...\n")
        res = RelationshipEvaluator().evaluate(ctx(src))
        t = " | ".join(f.title for f in res.findings)
        self.assertIn("'Lonely' is isolated", t)
        self.assertIn("depend on each other", t)

    def test_single_class_design(self):
        res = ResponsibilityEvaluator().evaluate(ctx("class Everything:\n    def park(self): ...  # single class design\n"))
        self.assertLessEqual(res.score, 20)
