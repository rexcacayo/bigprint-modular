import math
import unittest

import _context  # noqa: F401

from core import connectors as cn
from core import planes as pl
from core import sections as sec
from core.geometry import MeshData
from core.sample_shapes import box


def rotar_x(p, grados):
    a = math.radians(grados)
    x, y, z = p
    return (x, y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a))


def rectangulo(ancho, alto):
    return [(0.0, 0.0), (ancho, 0.0), (ancho, alto), (0.0, alto)]


class TestPlano(unittest.TestCase):
    def test_plano_de_eje_igual_que_siempre(self):
        p = pl.Plane.from_axis(2, 25.0)
        self.assertEqual(p.to_2d((3.0, 4.0, 25.0)), (3.0, 4.0))
        self.assertEqual(p.to_3d((3.0, 4.0), 1.0), (3.0, 4.0, 26.0))
        self.assertEqual(p.label(), "Z = 25")

    def test_guardar_y_leer(self):
        for p in (pl.Plane.from_axis(0, 12.5), pl.Plane.from_normal((1, 2, 3), (0, 1, 1))):
            q = pl.Plane.parse(p.serialize())
            self.assertEqual(q.axis, p.axis)
            for a, b in zip(q.normal, p.normal):
                self.assertAlmostEqual(a, b, places=5)
            self.assertAlmostEqual(q.distance(p.origin), 0.0, places=5)

    def test_ida_y_vuelta_inclinado(self):
        p = pl.Plane.from_normal((5, 5, 5), (1, 1, 0))
        punto = p.to_3d((7.0, -3.0))
        self.assertAlmostEqual(p.distance(punto), 0.0)
        u, v = p.to_2d(punto)
        self.assertAlmostEqual(u, 7.0)
        self.assertAlmostEqual(v, -3.0)

    def test_escalado(self):
        p = pl.Plane.from_axis(1, 2.0).scaled(10.0)
        self.assertAlmostEqual(p.origin[1], 20.0)


class TestAjuste(unittest.TestCase):
    def test_linea_horizontal_da_corte_en_z(self):
        puntos = [(0, 0, 10), (10, 0, 10), (10, 10, 10.0), (0, 10, 10)]
        plano, dev = pl.fit_plane(puntos)
        self.assertEqual(plano.axis, 2)
        self.assertAlmostEqual(plano.origin[2], 10.0)
        self.assertAlmostEqual(dev, 0.0)

    def test_linea_inclinada(self):
        puntos = [rotar_x(p, 30) for p in [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (5, 12, 0)]]
        plano, dev = pl.fit_plane(puntos)
        self.assertIsNone(plano.axis)
        self.assertLess(dev, 1e-9)
        self.assertAlmostEqual(pl.tilt_degrees(plano), 30.0, places=4)
        self.assertGreater(plano.normal[2], 0)   # hacia el lado positivo dominante

    def test_mano_temblorosa_se_endereza(self):
        puntos = [(0, 0, 10), (10, 0, 10.2), (10, 10, 10.0), (0, 10, 9.9)]
        plano, _dev = pl.fit_plane(puntos)
        recto = pl.snap_to_axis(plano)
        self.assertEqual(recto.axis, 2)

    def test_pocos_puntos_o_en_fila(self):
        with self.assertRaises(ValueError):
            pl.fit_plane([(0, 0, 0), (1, 0, 0)])
        with self.assertRaises(ValueError):
            pl.fit_plane([(0, 0, 0), (1, 0, 0), (2, 0, 0)])


class TestSeccionInclinada(unittest.TestCase):
    def test_seccion_de_la_cara_girada(self):
        caja = box(40, 30, 20)
        girada = MeshData(
            vertices=[rotar_x(v, 25) for v in caja.vertices], triangles=list(caja.triangles)
        )
        # La tapa de arriba (z = 20) girada queda en un plano inclinado
        plano = pl.Plane.from_normal(rotar_x((0, 0, 20), 25), rotar_x((0, 0, 1), 25))
        seccion = sec.extract_section_plane(girada, plano, tolerance=1e-6)
        self.assertFalse(seccion.is_empty)
        self.assertAlmostEqual(seccion.area(), 40 * 30, places=3)

    def test_plano_de_eje_delega(self):
        caja = box(100, 100, 50)
        a = sec.extract_section(caja, 2, 50.0)
        b = sec.extract_section_plane(caja, pl.Plane.from_axis(2, 50.0))
        self.assertAlmostEqual(a.area(), b.area())

    def test_cilindros_iguales_en_plano_de_eje(self):
        spec = cn.magnet(6, 3)
        v1, t1 = cn.cutter_cylinders([(10.0, 10.0)], 2, 5.0, spec)
        v2, t2 = cn.cutter_cylinders_plane([(10.0, 10.0)], pl.Plane.from_axis(2, 5.0), spec)
        self.assertEqual(len(v1), len(v2))
        for a, b in zip(sorted(v1), sorted(v2)):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y, places=6)

    def test_cilindro_inclinado_cerrado_y_hacia_fuera(self):
        spec = cn.magnet(6, 3)
        plano = pl.Plane.from_normal((0, 0, 0), (0, 1, 1))
        v, t = cn.cutter_cylinders_plane([(0.0, 0.0)], plano, spec)
        vol = 0.0
        for a, b, c in t:
            pa, pb, pc = v[a], v[b], v[c]
            vol += (pa[0] * (pb[1] * pc[2] - pb[2] * pc[1])
                    - pa[1] * (pb[0] * pc[2] - pb[2] * pc[0])
                    + pa[2] * (pb[0] * pc[1] - pb[1] * pc[0])) / 6.0
        esperado = math.pi * spec.hole_radius ** 2 * spec.depth * 2
        self.assertAlmostEqual(abs(vol), esperado, delta=esperado * 0.03)


class TestImanesYBoquilla(unittest.TestCase):
    def test_pared_segun_boquilla(self):
        self.assertEqual(cn.wall_from_nozzle(0.4), 1.0)
        self.assertEqual(cn.wall_from_nozzle(0.25), 0.62)
        self.assertEqual(cn.wall_from_nozzle(0.6), 1.5)
        self.assertEqual(cn.wall_from_nozzle(0.1), 0.5)

    def test_hay_imanes_pequenos(self):
        for medida in ((3.0, 1.0), (3.0, 2.0), (4.0, 2.0), (4.0, 3.0)):
            self.assertIn(medida, cn.MAGNET_SIZES)

    def test_cintura_estrecha_sugiere_iman_menor(self):
        # 7,5 mm de ancho: el 6×3 con pared de 1 mm pide 8,1; el 5×2 pide 7,1
        seccion = cn.Section([rectangulo(7.5, 40)])
        muro = cn.wall_from_nozzle(0.4)
        self.assertFalse(cn.place_connectors(seccion, cn.magnet(6, 3, wall=muro), 4).ok)
        mejor = cn.best_fitting(seccion, cn.MAGNET_SIZES, cn.MAGNET, wall=muro)
        self.assertIsNotNone(mejor)
        self.assertEqual(mejor.diameter, 5.0)

    def test_nada_cabe(self):
        seccion = cn.Section([rectangulo(2.0, 2.0)])
        self.assertIsNone(cn.best_fitting(seccion, cn.MAGNET_SIZES, cn.MAGNET, wall=1.0))

    def test_pared_vieja_sin_boquilla(self):
        self.assertEqual(cn.magnet(6, 3).wall, 1.5)
        self.assertEqual(cn.magnet(6, 3, wall=1.0).wall, 1.0)


if __name__ == "__main__":
    unittest.main()
