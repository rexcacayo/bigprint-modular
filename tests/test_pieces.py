import unittest

import _context  # noqa: F401

from core import pieces


class TestNombres(unittest.TestCase):
    def test_nombre_basico(self):
        self.assertEqual(pieces.piece_name("Soporte", 1), "Soporte_pieza_01")
        self.assertEqual(pieces.piece_name("Soporte", 12), "Soporte_pieza_12")

    def test_no_se_encadenan_sufijos(self):
        # Cortar una pieza otra vez no debe dar "..._pieza_01_pieza_01"
        self.assertEqual(pieces.piece_name("Soporte_pieza_01", 2), "Soporte_pieza_02")

    def test_solo_se_quita_el_sufijo_del_final(self):
        self.assertEqual(pieces.base_name("pieza_rara"), "pieza_rara")
        self.assertEqual(pieces.base_name("Soporte_pieza_03"), "Soporte")

    def test_lista_de_nombres(self):
        self.assertEqual(
            pieces.piece_names("Escuadra", 3),
            ["Escuadra_pieza_01", "Escuadra_pieza_02", "Escuadra_pieza_03"],
        )

    def test_indices_invalidos(self):
        with self.assertRaises(ValueError):
            pieces.piece_name("X", 0)
        with self.assertRaises(ValueError):
            pieces.piece_names("X", 0)


class TestVolumenes(unittest.TestCase):
    def test_corte_limpio(self):
        check = pieces.check_volumes(8856.0, [4000.0, 4856.0])
        self.assertTrue(check.ok)
        self.assertAlmostEqual(check.total, 8856.0)
        self.assertAlmostEqual(check.relative_error, 0.0)
        self.assertIn("conservado", check.describe())

    def test_tolera_el_ruido_de_coma_flotante(self):
        check = pieces.check_volumes(8856.0, [4000.0, 4856.02])
        self.assertTrue(check.ok)

    def test_detecta_material_perdido(self):
        check = pieces.check_volumes(8856.0, [4000.0, 4000.0])
        self.assertFalse(check.ok)
        self.assertLess(check.difference, 0)
        self.assertIn("Falta o sobra", check.describe())

    def test_detecta_material_duplicado(self):
        check = pieces.check_volumes(1000.0, [1000.0, 1000.0])
        self.assertFalse(check.ok)
        self.assertGreater(check.difference, 0)

    def test_tolerancia_configurable(self):
        self.assertFalse(pieces.check_volumes(1000.0, [990.0]).ok)
        self.assertTrue(pieces.check_volumes(1000.0, [990.0], tolerance=0.02).ok)

    def test_original_sin_volumen(self):
        self.assertTrue(pieces.check_volumes(0.0, [0.0]).ok)
        self.assertFalse(pieces.check_volumes(0.0, [5.0]).ok)


if __name__ == "__main__":
    unittest.main()
