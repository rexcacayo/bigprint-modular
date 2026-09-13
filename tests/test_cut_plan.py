import unittest

import _context  # noqa: F401

from core import cut_plan as cpl
from core import printer_profiles as pp

ESCUADRA_MIN = (0.0, 0.0, 0.0)
ESCUADRA_MAX = (420.0, 180.0, 260.0)


class TestPlanDeRejilla(unittest.TestCase):
    def setUp(self):
        self.perfil = pp.get_profile("GENERIC_256")  # útil 236³

    def test_escuadra_de_ejemplo(self):
        plan = cpl.plan_grid(ESCUADRA_MIN, ESCUADRA_MAX, self.perfil)
        self.assertEqual(plan.counts, (2, 1, 2))
        self.assertEqual(plan.total_pieces, 4)
        self.assertEqual(len(plan.cuts), 2)

        corte_x = plan.cuts_on("X")[0]
        corte_z = plan.cuts_on("Z")[0]
        self.assertAlmostEqual(corte_x.position, 210.0)
        self.assertAlmostEqual(corte_z.position, 130.0)
        self.assertEqual(plan.cuts_on("Y"), [])

    def test_lo_que_cabe_no_se_corta(self):
        plan = cpl.plan_grid((0, 0, 0), (200, 100, 100), self.perfil)
        self.assertFalse(plan.needs_cutting)
        self.assertEqual(plan.total_pieces, 1)
        self.assertIn("cabe entera", plan.describe())

    def test_tres_divisiones_reparten_por_igual(self):
        plan = cpl.plan_grid((0, 0, 0), (600, 100, 100), self.perfil)
        cortes = plan.cuts_on("X")
        self.assertEqual(len(cortes), 2)  # tres piezas -> dos cortes
        self.assertAlmostEqual(cortes[0].position, 200.0)
        self.assertAlmostEqual(cortes[1].position, 400.0)

    def test_las_piezas_resultantes_caben(self):
        plan = cpl.plan_grid(ESCUADRA_MIN, ESCUADRA_MAX, self.perfil)
        util = self.perfil.usable
        for eje in range(3):
            lado = (ESCUADRA_MAX[eje] - ESCUADRA_MIN[eje]) / plan.counts[eje]
            self.assertLessEqual(lado, max(util) + 1e-6)

    def test_caja_desplazada_del_origen(self):
        plan = cpl.plan_grid((100, 0, 0), (520, 180, 260), self.perfil)
        self.assertAlmostEqual(plan.cuts_on("X")[0].position, 310.0)

    def test_tope_de_seguridad(self):
        with self.assertRaises(ValueError):
            cpl.plan_grid((0, 0, 0), (5000, 5000, 5000), self.perfil)

    def test_tope_configurable(self):
        plan = cpl.plan_grid((0, 0, 0), (1000, 1000, 100), self.perfil, max_pieces=100)
        self.assertGreater(plan.total_pieces, 16)

    def test_descripcion(self):
        plan = cpl.plan_grid(ESCUADRA_MIN, ESCUADRA_MAX, self.perfil)
        texto = plan.describe()
        self.assertIn("1 en X", texto)
        self.assertIn("1 en Z", texto)
        self.assertIn("4 piezas", texto)


class TestCruce(unittest.TestCase):
    def test_atraviesa(self):
        corte = cpl.CutSpec(axis=0, position=210.0)
        self.assertTrue(cpl.crosses(ESCUADRA_MIN, ESCUADRA_MAX, corte))

    def test_no_atraviesa_una_pieza_ya_cortada(self):
        corte = cpl.CutSpec(axis=0, position=210.0)
        # La mitad alta empieza justo en el plano: no hay nada que cortar
        self.assertFalse(cpl.crosses((210.0, 0, 0), (420.0, 180.0, 260.0), corte))
        self.assertFalse(cpl.crosses((0, 0, 0), (210.0, 180.0, 260.0), corte))

    def test_el_margen_evita_cortes_de_espesor_cero(self):
        corte = cpl.CutSpec(axis=0, position=210.0)
        self.assertFalse(cpl.crosses((209.9995, 0, 0), (420.0, 180.0, 260.0), corte))


class TestOrdenDeNumeracion(unittest.TestCase):
    def test_se_numera_por_capas_de_abajo_arriba(self):
        cajas = [
            (0.0, 0.0, 130.0),
            (210.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (210.0, 0.0, 130.0),
        ]
        ordenadas = sorted(cajas, key=cpl.sort_key)
        self.assertEqual(ordenadas[0], (0.0, 0.0, 0.0))
        self.assertEqual(ordenadas[1], (210.0, 0.0, 0.0))
        self.assertEqual(ordenadas[2], (0.0, 0.0, 130.0))
        self.assertEqual(ordenadas[3], (210.0, 0.0, 130.0))


if __name__ == "__main__":
    unittest.main()
