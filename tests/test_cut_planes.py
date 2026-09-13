import math
import unittest

import _context  # noqa: F401

from core import cut_planes as cp
from core import printer_profiles as pp
from core.sample_shapes import l_bracket

ESCUADRA_MIN = (0.0, 0.0, 0.0)
ESCUADRA_MAX = (420.0, 180.0, 260.0)


class TestEjes(unittest.TestCase):
    def test_por_nombre_y_por_indice(self):
        self.assertEqual(cp.axis_index("X"), 0)
        self.assertEqual(cp.axis_index("z"), 2)
        self.assertEqual(cp.axis_index(1), 1)
        self.assertEqual(cp.axis_name(2), "Z")

    def test_ejes_invalidos(self):
        with self.assertRaises(ValueError):
            cp.axis_index("W")
        with self.assertRaises(ValueError):
            cp.axis_index(7)


class TestSugerenciaDeEje(unittest.TestCase):
    def setUp(self):
        self.perfil = pp.get_profile("GENERIC_256")  # útil 236³

    def test_elige_el_mayor_desborde_no_el_lado_mas_largo(self):
        # 300 × 100 × 280: X se pasa 64, Z se pasa 44 -> X
        self.assertEqual(cp.suggest_axis((300, 100, 280), self.perfil), 0)
        # 240 × 100 × 400: Z se pasa mucho más aunque X también se pase
        self.assertEqual(cp.suggest_axis((240, 100, 400), self.perfil), 2)

    def test_si_cabe_entera_devuelve_el_lado_mas_largo(self):
        self.assertEqual(cp.suggest_axis((200, 100, 150), self.perfil), 0)

    def test_escuadra_de_ejemplo(self):
        # 420 × 180 × 260: X se pasa 184, Z se pasa 24
        self.assertEqual(cp.suggest_axis((420, 180, 260), self.perfil), 0)


class TestPosicion(unittest.TestCase):
    def test_centro(self):
        self.assertEqual(cp.center_position(ESCUADRA_MIN, ESCUADRA_MAX, "X"), 210.0)
        self.assertEqual(cp.center_position(ESCUADRA_MIN, ESCUADRA_MAX, "Z"), 130.0)

    def test_validez(self):
        self.assertTrue(cp.is_valid_position(ESCUADRA_MIN, ESCUADRA_MAX, "X", 210.0))
        self.assertFalse(cp.is_valid_position(ESCUADRA_MIN, ESCUADRA_MAX, "X", 0.0))
        self.assertFalse(cp.is_valid_position(ESCUADRA_MIN, ESCUADRA_MAX, "X", 420.0))
        self.assertFalse(cp.is_valid_position(ESCUADRA_MIN, ESCUADRA_MAX, "X", -5.0))
        self.assertFalse(cp.is_valid_position(ESCUADRA_MIN, ESCUADRA_MAX, "X", 500.0))


class TestPartirCaja(unittest.TestCase):
    def test_dos_mitades(self):
        baja, alta = cp.split_bbox(ESCUADRA_MIN, ESCUADRA_MAX, "X", 210.0)
        self.assertEqual(baja, ((0, 0, 0), (210.0, 180.0, 260.0)))
        self.assertEqual(alta, ((210.0, 0, 0), (420.0, 180.0, 260.0)))

    def test_corte_descentrado(self):
        baja, alta = cp.split_bbox(ESCUADRA_MIN, ESCUADRA_MAX, "X", 100.0)
        self.assertEqual(baja[1][0], 100.0)
        self.assertEqual(alta[0][0], 100.0)

    def test_fuera_de_la_pieza(self):
        with self.assertRaises(ValueError):
            cp.split_bbox(ESCUADRA_MIN, ESCUADRA_MAX, "X", 999.0)


class TestPrevisualizacion(unittest.TestCase):
    def setUp(self):
        self.perfil = pp.get_profile("GENERIC_256")

    def test_corte_al_centro_de_la_escuadra(self):
        vista = cp.preview_split(ESCUADRA_MIN, ESCUADRA_MAX, "X", 210.0, self.perfil)
        self.assertEqual(vista.dims_low, (210.0, 180.0, 260.0))
        self.assertEqual(vista.dims_high, (210.0, 180.0, 260.0))
        # 260 en Z sigue pasándose de 236: un solo corte no basta
        self.assertFalse(vista.both_fit)
        self.assertEqual(vista.axis_name, "X")

    def test_un_corte_basta_cuando_solo_sobra_un_eje(self):
        vista = cp.preview_split((0, 0, 0), (400, 100, 100), "X", 200.0, self.perfil)
        self.assertTrue(vista.both_fit)

    def test_corte_desequilibrado_deja_una_mitad_fuera(self):
        vista = cp.preview_split((0, 0, 0), (400, 100, 100), "X", 50.0, self.perfil)
        self.assertTrue(vista.fits_low)
        self.assertFalse(vista.fits_high)  # 350 mm no caben en 236

    def test_la_rotacion_cuenta(self):
        perfil = pp.make_custom_profile(300, 100, 100, 0)
        vista = cp.preview_split((0, 0, 0), (100, 100, 400), "Z", 200.0, perfil, True)
        self.assertTrue(vista.both_fit)
        sin_giro = cp.preview_split((0, 0, 0), (100, 100, 400), "Z", 200.0, perfil, False)
        self.assertFalse(sin_giro.both_fit)


class TestTransformacionDelPlano(unittest.TestCase):
    def test_normal_en_z(self):
        loc, rot, esc = cp.plane_transform(ESCUADRA_MIN, ESCUADRA_MAX, "Z", 130.0, overshoot=1.0)
        self.assertEqual(loc, (210.0, 90.0, 130.0))
        self.assertEqual(rot, (0.0, 0.0, 0.0))
        self.assertEqual(esc, (210.0, 90.0, 1.0))  # semiejes de X e Y

    def test_normal_en_x(self):
        loc, rot, esc = cp.plane_transform(ESCUADRA_MIN, ESCUADRA_MAX, "X", 210.0, overshoot=1.0)
        self.assertEqual(loc, (210.0, 90.0, 130.0))
        self.assertAlmostEqual(rot[1], math.pi / 2)
        self.assertEqual(esc, (130.0, 90.0, 1.0))  # semiejes de Z e Y

    def test_normal_en_y(self):
        loc, rot, esc = cp.plane_transform(ESCUADRA_MIN, ESCUADRA_MAX, "Y", 90.0, overshoot=1.0)
        self.assertAlmostEqual(rot[0], math.pi / 2)
        self.assertEqual(esc, (210.0, 130.0, 1.0))  # semiejes de X y Z

    def test_el_plano_sobresale_de_la_pieza(self):
        _, _, esc = cp.plane_transform(ESCUADRA_MIN, ESCUADRA_MAX, "Z", 130.0, overshoot=1.2)
        self.assertAlmostEqual(esc[0], 210.0 * 1.2)
        self.assertAlmostEqual(esc[1], 90.0 * 1.2)

    def test_la_posicion_manda_en_su_eje(self):
        loc, _, _ = cp.plane_transform(ESCUADRA_MIN, ESCUADRA_MAX, "X", 50.0)
        self.assertEqual(loc[0], 50.0)
        self.assertEqual(loc[1], 90.0)  # los otros dos quedan centrados

    def test_pieza_plana_no_genera_escala_cero(self):
        _, _, esc = cp.plane_transform((0, 0, 0), (100, 100, 0), "X", 50.0)
        self.assertGreater(esc[0], 0.0)


class TestCoherenciaConElEjemplo(unittest.TestCase):
    def test_la_caja_del_ejemplo_coincide(self):
        caja = l_bracket().bbox()
        self.assertEqual(caja.min, ESCUADRA_MIN)
        self.assertEqual(caja.max, ESCUADRA_MAX)


if __name__ == "__main__":
    unittest.main()
