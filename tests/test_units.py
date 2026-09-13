import unittest

import _context  # noqa: F401

from core import units as un


class TestUnitFactor(unittest.TestCase):
    def test_basic_factors(self):
        self.assertEqual(un.unit_factor(un.MILLIMETERS), 1.0)
        self.assertEqual(un.unit_factor(un.CENTIMETERS), 10.0)
        self.assertEqual(un.unit_factor(un.METERS), 1000.0)
        self.assertAlmostEqual(un.unit_factor(un.INCHES), 25.4)

    def test_scene_factor(self):
        # scale_length = 0.001 -> 1 unidad de Blender es 1 mm
        self.assertAlmostEqual(un.unit_factor(un.SCENE, 0.001), 1.0)
        self.assertAlmostEqual(un.unit_factor(un.SCENE, 1.0), 1000.0)

    def test_unknown_unit(self):
        with self.assertRaises(ValueError):
            un.unit_factor("PARSEC")


class TestGuessUnit(unittest.TestCase):
    def test_typical_stl_in_mm(self):
        self.assertEqual(un.guess_unit(256.0), un.MILLIMETERS)
        self.assertEqual(un.guess_unit(20.0), un.MILLIMETERS)

    def test_centimeters(self):
        self.assertEqual(un.guess_unit(19.9), un.CENTIMETERS)
        self.assertEqual(un.guess_unit(2.0), un.CENTIMETERS)

    def test_meters(self):
        self.assertEqual(un.guess_unit(1.99), un.METERS)
        self.assertEqual(un.guess_unit(0.26), un.METERS)

    def test_zero(self):
        self.assertEqual(un.guess_unit(0.0), un.MILLIMETERS)


class TestResolve(unittest.TestCase):
    def test_auto_resolves(self):
        unidad, factor = un.resolve_unit(un.AUTO, 420.0)
        self.assertEqual(unidad, un.MILLIMETERS)
        self.assertEqual(factor, 1.0)

    def test_explicit_wins_over_size(self):
        unidad, factor = un.resolve_unit(un.METERS, 420.0)
        self.assertEqual(unidad, un.METERS)
        self.assertEqual(factor, 1000.0)

    def test_to_mm(self):
        self.assertEqual(un.to_mm((1, 2, 3), 10.0), (10.0, 20.0, 30.0))


if __name__ == "__main__":
    unittest.main()
