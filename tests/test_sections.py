import unittest

import _context  # noqa: F401

from core import connectors as cn
from core import sections as sec
from core.geometry import MeshData
from core.sample_shapes import box, l_bracket


def cortar_caja_en_z(altura=50.0, lado=100.0):
    """Caja de 100 mm con una tapa artificial en Z = altura.

    Simula lo que deja el corte: la cara nueva sobre el plano, triangulada.
    """
    malla = box(lado, lado, altura)
    return malla


class TestCarasSobreElPlano(unittest.TestCase):
    def test_encuentra_la_tapa(self):
        malla = box(100, 100, 50)
        caras = sec.faces_on_plane(malla, axis=2, position=50.0)
        self.assertEqual(len(caras), 2, "la tapa de una caja son dos triángulos")

    def test_no_confunde_con_las_paredes(self):
        malla = box(100, 100, 50)
        self.assertEqual(sec.faces_on_plane(malla, axis=2, position=25.0), [])

    def test_tolerancia(self):
        malla = box(100, 100, 50)
        self.assertEqual(len(sec.faces_on_plane(malla, 2, 50.0005, tolerance=1e-2)), 2)
        self.assertEqual(sec.faces_on_plane(malla, 2, 50.5, tolerance=1e-3), [])


class TestExtraccionDeSeccion(unittest.TestCase):
    def test_seccion_cuadrada(self):
        malla = box(100, 80, 50)
        seccion = sec.extract_section(malla, axis=2, position=50.0)
        self.assertEqual(len(seccion.loops), 1)
        self.assertEqual(len(seccion.loops[0]), 4, "el contorno son cuatro esquinas")
        self.assertAlmostEqual(seccion.area(), 8000.0)

    def test_la_seccion_esta_donde_toca(self):
        malla = box(100, 80, 50)
        seccion = sec.extract_section(malla, axis=2, position=50.0)
        (min_u, min_v), (max_u, max_v) = seccion.bounds()
        self.assertAlmostEqual(max_u - min_u, 100.0)
        self.assertAlmostEqual(max_v - min_v, 80.0)

    def test_seccion_en_x(self):
        malla = box(100, 80, 50)
        seccion = sec.extract_section(malla, axis=0, position=100.0)
        self.assertAlmostEqual(seccion.area(), 80.0 * 50.0)

    def test_sin_plano_no_hay_seccion(self):
        malla = box(100, 80, 50)
        self.assertTrue(sec.extract_section(malla, 2, 25.0).is_empty)

    def test_la_escuadra_da_una_seccion_en_l(self):
        # La cara Y = 0 de la escuadra es el perfil en L completo
        seccion = sec.extract_section(l_bracket(), axis=1, position=0.0)
        self.assertFalse(seccion.is_empty)
        # 420*60 + 200*120 = 49200 mm²
        self.assertAlmostEqual(seccion.area(), 49200.0, places=3)

    def test_dos_islas_dan_dos_contornos(self):
        a = box(50, 50, 10)
        b = box(50, 50, 10)
        desplazamiento = len(a.vertices)
        malla = MeshData(
            vertices=a.vertices + [(x + 200, y, z) for x, y, z in b.vertices],
            triangles=a.triangles
            + [(i + desplazamiento, j + desplazamiento, k + desplazamiento) for i, j, k in b.triangles],
        )
        seccion = sec.extract_section(malla, axis=2, position=10.0)
        self.assertEqual(len(seccion.loops), 2)
        self.assertAlmostEqual(seccion.area(), 2 * 2500.0)


class TestEjesDelPlano(unittest.TestCase):
    def test_orden_ciclico(self):
        self.assertEqual(sec.plane_axes(0), (1, 2))
        self.assertEqual(sec.plane_axes(1), (2, 0))
        self.assertEqual(sec.plane_axes(2), (0, 1))

    def test_ida_y_vuelta_a_3d(self):
        punto3d = sec.to_3d((30.0, 40.0), axis=2, position=15.0)
        self.assertEqual(punto3d, (30.0, 40.0, 15.0))
        self.assertEqual(sec.to_3d((30.0, 40.0), axis=0, position=15.0), (15.0, 30.0, 40.0))
        self.assertEqual(sec.to_3d((30.0, 40.0), axis=1, position=15.0), (40.0, 15.0, 30.0))


class TestMezclaDeConectores(unittest.TestCase):
    """Dowels e imanes en la misma sección no deben pisarse."""

    def setUp(self):
        self.seccion = cn.Section(
            [[(0.0, 0.0), (120.0, 0.0), (120.0, 120.0), (0.0, 120.0)]]
        )

    def test_los_imanes_esquivan_los_dowels(self):
        dowels = cn.place_connectors(self.seccion, cn.dowel(3.0, 20.0), max_count=2)
        self.assertEqual(dowels.count, 2)

        spec_iman = cn.magnet(8.0, 3.0)
        imanes = cn.place_connectors(
            self.seccion, spec_iman, max_count=2, avoid=dowels.points
        )
        self.assertTrue(imanes.ok)
        for punto in imanes.points:
            for ocupado in dowels.points:
                d = ((punto[0] - ocupado[0]) ** 2 + (punto[1] - ocupado[1]) ** 2) ** 0.5
                self.assertGreaterEqual(d, spec_iman.spacing - 1e-9)

    def test_si_no_queda_sitio_lo_dice(self):
        seccion = cn.Section([[(0, 0), (22, 0), (22, 22), (0, 22)]])
        dowels = cn.place_connectors(seccion, cn.dowel(3.0, 20.0), max_count=1)
        imanes = cn.place_connectors(
            seccion, cn.magnet(12.0, 3.0), max_count=1, avoid=dowels.points
        )
        self.assertFalse(imanes.ok)


if __name__ == "__main__":
    unittest.main()
