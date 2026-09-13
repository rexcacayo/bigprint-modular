import unittest

import _context  # noqa: F401

from core import printer_profiles as pp


class TestProfiles(unittest.TestCase):
    def test_default_profile_exists(self):
        p = pp.get_profile(pp.DEFAULT_PROFILE_ID)
        self.assertEqual((p.size_x, p.size_y, p.size_z), (256.0, 256.0, 256.0))
        self.assertEqual(p.margin, 10.0)

    def test_usable_volume_subtracts_margin_on_both_sides(self):
        p = pp.get_profile("GENERIC_256")
        self.assertEqual(p.usable, (236.0, 236.0, 236.0))
        self.assertAlmostEqual(p.usable_volume_mm3, 236.0 ** 3)

    def test_all_builtin_profiles_are_valid(self):
        ids = set()
        for p in pp.list_profiles():
            self.assertNotIn(p.id, ids, "ids duplicados en los perfiles")
            ids.add(p.id)
            self.assertTrue(all(v > 0 for v in p.usable))

    def test_unknown_profile(self):
        with self.assertRaises(KeyError):
            pp.get_profile("NO_EXISTE")

    def test_invalid_profiles_rejected(self):
        with self.assertRaises(ValueError):
            pp.PrinterProfile("X", "malo", 0, 100, 100)
        with self.assertRaises(ValueError):
            pp.PrinterProfile("X", "malo", 100, 100, 100, margin=-1)
        with self.assertRaises(ValueError):
            pp.PrinterProfile("X", "malo", 100, 100, 100, margin=50)

    def test_custom_profile(self):
        p = pp.make_custom_profile(300, 300, 400, 5)
        self.assertEqual(p.id, pp.CUSTOM_ID)
        self.assertEqual(p.usable, (290.0, 290.0, 390.0))

    def test_enum_items_include_custom(self):
        items = pp.profile_enum_items()
        self.assertEqual(items[0][0], pp.DEFAULT_PROFILE_ID)
        self.assertEqual(items[-1][0], pp.CUSTOM_ID)
        for item in items:
            self.assertEqual(len(item), 3)


class TestFit(unittest.TestCase):
    def setUp(self):
        self.profile = pp.get_profile("GENERIC_256")  # útil 236³

    def test_small_part_fits(self):
        fit = pp.check_fit((100, 100, 100), self.profile)
        self.assertTrue(fit.fits)
        self.assertEqual(fit.total_pieces, 1)
        self.assertEqual(fit.overflow, (0.0, 0.0, 0.0))

    def test_exact_usable_size_fits(self):
        self.assertTrue(pp.check_fit((236, 236, 236), self.profile).fits)

    def test_margin_matters(self):
        # 250 mm cabe en la cama de 256 pero no dentro del margen de 10
        self.assertFalse(pp.check_fit((250, 100, 100), self.profile).fits)

    def test_rotation_saves_the_day(self):
        dims = (100, 300, 100)  # no cabe en Y, pero sí girando a X
        p = pp.make_custom_profile(320, 200, 200, 0)
        self.assertFalse(pp.check_fit(dims, p, allow_rotation=False).fits)
        fit = pp.check_fit(dims, p, allow_rotation=True)
        self.assertTrue(fit.fits)
        self.assertIsNotNone(fit.orientation)

    def test_rotation_disabled(self):
        p = pp.make_custom_profile(320, 200, 200, 0)
        self.assertFalse(pp.check_fit((100, 300, 100), p, allow_rotation=False).fits)

    def test_overflow_reported(self):
        fit = pp.check_fit((420, 180, 260), self.profile)
        self.assertFalse(fit.fits)
        self.assertAlmostEqual(fit.overflow[0], 420 - 236)
        self.assertAlmostEqual(fit.overflow[1], 0.0)
        self.assertAlmostEqual(fit.overflow[2], 260 - 236)


class TestPieces(unittest.TestCase):
    def test_single_piece(self):
        self.assertEqual(pp.estimate_pieces((100, 100, 100), pp.get_profile("GENERIC_256")), (1, 1, 1))

    def test_example_bracket(self):
        # 420 × 180 × 260 en útil 236³ -> 2 en X, 1 en Y, 2 en Z
        piezas = pp.estimate_pieces((420, 180, 260), pp.get_profile("GENERIC_256"))
        self.assertEqual(piezas, (2, 1, 2))
        self.assertEqual(piezas[0] * piezas[1] * piezas[2], 4)

    def test_rotation_reduces_pieces(self):
        p = pp.make_custom_profile(300, 100, 100, 0)
        # 100 × 100 × 300: girando, una sola pieza
        self.assertEqual(pp.estimate_pieces((100, 100, 300), p, allow_rotation=True), (1, 1, 1))
        self.assertEqual(pp.estimate_pieces((100, 100, 300), p, allow_rotation=False), (1, 1, 3))

    def test_exact_multiple_does_not_add_a_piece(self):
        p = pp.make_custom_profile(120, 120, 120, 10)  # útil 100
        self.assertEqual(pp.estimate_pieces((200, 100, 100), p, allow_rotation=False), (2, 1, 1))


class TestScaleToFit(unittest.TestCase):
    def test_no_scaling_needed(self):
        self.assertEqual(pp.scale_to_fit((100, 100, 100), pp.get_profile("GENERIC_256")), 1.0)

    def test_scale_down(self):
        factor = pp.scale_to_fit((472, 236, 236), pp.get_profile("GENERIC_256"))
        self.assertAlmostEqual(factor, 0.5)


if __name__ == "__main__":
    unittest.main()
