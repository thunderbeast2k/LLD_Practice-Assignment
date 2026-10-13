import unittest

from lld_practice.domain import ValidationError
from lld_practice.parsing import FormatRegistry, PythonFormat, TextFormat
from tests.helpers import example


class PythonParsingTests(unittest.TestCase):
    def setUp(self):
        self.model = PythonFormat().parse(example("parking_lot_good.py"))

    def test_kinds_and_inheritance(self):
        c = self.model.classes
        self.assertEqual(c["PricingStrategy"].kind, "interface")
        self.assertEqual(c["VehicleType"].kind, "enum")
        self.assertEqual(c["ParkingLot"].kind, "class")
        self.assertIn("PricingStrategy", c["HourlyPricing"].bases)
        self.assertEqual(len(self.model.implementers("PricingStrategy")), 2)

    def test_methods_attributes_references(self):
        lot = self.model.classes["ParkingLot"]
        self.assertIn("park", lot.methods)
        self.assertNotIn("__init__", lot.methods)
        self.assertIn("pricing", lot.attributes)
        self.assertIn("PricingStrategy", lot.references)  # via annotation
        self.assertIn("Floor", lot.references)

    def test_syntax_error_is_reported_with_line(self):
        with self.assertRaisesRegex(ValidationError, "line 2"):
            PythonFormat().parse("class A:\n    def (self): pass  # broken syntax here\n")

    def test_no_classes(self):
        with self.assertRaisesRegex(ValidationError, "No classes"):
            PythonFormat().parse("def f():\n    return 1  # only a function, nothing else\n")

    def test_too_short_and_too_long(self):
        with self.assertRaisesRegex(ValidationError, "too short"):
            PythonFormat().parse("class A: pass")
        with self.assertRaisesRegex(ValidationError, "too long"):
            PythonFormat().parse("# " + "x" * 70_000)


class TextParsingTests(unittest.TestCase):
    def setUp(self):
        self.model = TextFormat().parse(example("parking_lot_text.txt"))

    def test_declarations(self):
        c = self.model.classes
        self.assertEqual(c["PricingStrategy"].kind, "interface")
        self.assertEqual(c["Vehicle"].kind, "interface")  # `abstract class`
        self.assertEqual(c["Car"].bases, ["Vehicle"])
        self.assertEqual(c["HourlyPricing"].bases, ["PricingStrategy"])

    def test_members_and_references(self):
        lot = self.model.classes["ParkingLot"]
        self.assertEqual(lot.methods, ["park", "unpark", "isFull"])
        self.assertEqual(lot.attributes, ["spots", "pricing"])
        self.assertEqual(lot.references, {"ParkingSpot", "PricingStrategy", "Ticket"})

    def test_unstructured_prose_falls_back_with_note(self):
        m = TextFormat().parse("I would have a ParkingLot that holds ParkingSpot objects and issues a Ticket.")
        self.assertFalse(m.structured)
        self.assertIn("ParkingLot", m.classes)
        self.assertTrue(m.notes)

    def test_gibberish_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "Couldn't find any classes"):
            TextFormat().parse("this is some text without any class names at all, sorry")


class RegistryTests(unittest.TestCase):
    def test_unknown_format(self):
        with self.assertRaisesRegex(ValidationError, "Unknown submission format"):
            FormatRegistry().get("uml")

    def test_new_format_can_be_registered(self):
        class Json(PythonFormat):
            id = "json"
        reg = FormatRegistry()
        reg.register(Json())
        self.assertEqual(reg.get("json").id, "json")
