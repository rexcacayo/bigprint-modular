import math
import unittest

import _context  # noqa: F401

from core import connectors as cn
from core import dowels
from core.geometry import mesh_volume
from core.mesh_analysis import analyze_mesh


class TestMedidas(unittest.TestCase):
    def test_la_varilla_es_mas_fina_que_el_agujero(self):
        spec = cn.dowel(3.0, 20.0)
        impreso = dowels.printed_diameter(spec)
        self.assertLess(impreso, spec.hole_diameter)
        self.assertAlmostEqual(impreso, 3.2 - 0.15)

    def test_longitud_total(self):
        # El agujero es de media longitud en cada pieza
        spec = cn.dowel(3.0, 20.0)
        self.assertAlmostEqual(spec.depth, 10.0)
        self.assertAlmostEqual(dowels.dowel_length(spec), 20.0)

    def test_holgura_configurable(self):
        spec = cn.dowel(3.0, 20.0)
        self.assertGreater(
            dowels.printed_diameter(spec, 0.05), dowels.printed_diameter(spec, 0.3)
        )

    def test_nunca_sale_un_diametro_absurdo(self):
        spec = cn.dowel(1.75, 16.0)
        self.assertGreater(dowels.printed_diameter(spec, fit_gap=10.0), 0.0)


class TestGeometria(unittest.TestCase):
    def test_dimensiones_y_apoyo(self):
        malla = dowels.dowel_mesh(3.0, 20.0)
        caja = malla.bbox()
        self.assertAlmostEqual(caja.size[0], 20.0, places=4)
        self.assertAlmostEqual(caja.size[1], 3.0, places=3)
        # Tumbada en X y apoyada en la cama
        self.assertAlmostEqual(caja.min[2], 0.0, places=5)
        self.assertGreater(caja.size[0], caja.size[2])

    def test_es_un_solido_cerrado(self):
        informe = analyze_mesh(dowels.dowel_mesh(4.0, 24.0))
        self.assertTrue(informe.is_watertight)
        self.assertTrue(informe.is_manifold)
        self.assertTrue(informe.is_solid)

    def test_volumen_proximo_al_cilindro(self):
        malla = dowels.dowel_mesh(3.0, 20.0, segments=64)
        teorico = math.pi * 1.5 ** 2 * 20.0
        volumen = abs(mesh_volume(malla))
        # Algo menos por el chaflán de los extremos, pero no mucho
        self.assertLess(volumen, teorico)
        self.assertGreater(volumen, teorico * 0.9)

    def test_los_extremos_van_achaflanados(self):
        malla = dowels.dowel_mesh(6.0, 20.0)
        radios_extremo = [
            (y ** 2 + (z - 3.0) ** 2) ** 0.5 for x, y, z in malla.vertices if abs(x) < 1e-6
        ]
        self.assertLess(max(radios_extremo), 3.0, "el extremo debe ser más estrecho")

    def test_medidas_invalidas(self):
        with self.assertRaises(ValueError):
            dowels.dowel_mesh(0.0, 20.0)
        with self.assertRaises(ValueError):
            dowels.dowel_mesh(3.0, -1.0)


class TestLote(unittest.TestCase):
    def test_cantidad_y_separacion(self):
        lote = dowels.dowel_batch(4, 3.0, 20.0)
        unidad = dowels.dowel_mesh(3.0, 20.0)
        self.assertEqual(len(lote.vertices), 4 * len(unidad.vertices))
        self.assertAlmostEqual(abs(mesh_volume(lote)), 4 * abs(mesh_volume(unidad)), places=3)

    def test_no_se_solapan(self):
        lote = dowels.dowel_batch(3, 5.0, 20.0)
        caja = lote.bbox()
        self.assertGreater(caja.size[1], 3 * 5.0, "deben quedar separadas")

    def test_el_lote_sigue_cerrado(self):
        informe = analyze_mesh(dowels.dowel_batch(3, 3.0, 20.0))
        self.assertTrue(informe.is_watertight)
        self.assertEqual(informe.shell_count, 3)

    def test_cantidad_invalida(self):
        with self.assertRaises(ValueError):
            dowels.dowel_batch(0, 3.0, 20.0)


class TestNombreYResumen(unittest.TestCase):
    def test_el_nombre_lleva_medida_y_cantidad(self):
        nombre = dowels.batch_filename(cn.dowel(3.0, 20.0), 6)
        self.assertIn("3.05", nombre)
        self.assertIn("L20", nombre)
        self.assertIn("x6", nombre)
        self.assertTrue(nombre.endswith(".stl"))

    def test_resumen_legible(self):
        texto = dowels.describe(cn.dowel(3.0, 20.0), 6)
        self.assertIn("6 varillas", texto)
        self.assertIn("agujero", texto)


if __name__ == "__main__":
    unittest.main()
