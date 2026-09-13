import unittest

import _context  # noqa: F401

from core import connectors as cn


def cuadrado(lado, origen=(0.0, 0.0)):
    u, v = origen
    return [(u, v), (u + lado, v), (u + lado, v + lado), (u, v + lado)]


def rectangulo(ancho, alto, origen=(0.0, 0.0)):
    u, v = origen
    return [(u, v), (u + ancho, v), (u + ancho, v + alto), (u, v + alto)]


class TestEspecificacion(unittest.TestCase):
    def test_iman_estandar(self):
        spec = cn.magnet(6.0, 3.0)
        self.assertEqual(spec.kind, cn.MAGNET)
        self.assertAlmostEqual(spec.hole_diameter, 6.1)
        # El alojamiento va un pelín más hondo que el imán
        self.assertGreater(spec.depth, 3.0)
        self.assertIn("imán", spec.label)

    def test_dowel_reparte_la_varilla_entre_las_dos_piezas(self):
        spec = cn.dowel(3.0, 20.0)
        self.assertAlmostEqual(spec.depth, 10.0)
        self.assertAlmostEqual(spec.hole_diameter, 3.2)

    def test_el_iman_grande_pide_mas_pared(self):
        self.assertGreater(cn.magnet(10.0, 3.0).wall, cn.magnet(5.0, 2.0).wall)

    def test_material_necesario_alrededor(self):
        spec = cn.magnet(6.0, 3.0)
        self.assertAlmostEqual(spec.required_clearance, 6.1 / 2 + spec.wall)

    def test_especificaciones_invalidas(self):
        with self.assertRaises(ValueError):
            cn.ConnectorSpec(cn.DOWEL, "malo", 0.0, 10.0)
        with self.assertRaises(ValueError):
            cn.ConnectorSpec(cn.DOWEL, "malo", 3.0, 10.0, clearance=-1)


class TestGeometriaDeSeccion(unittest.TestCase):
    def test_area_y_contorno(self):
        seccion = cn.Section([cuadrado(100)])
        self.assertAlmostEqual(seccion.area(), 10000.0)
        self.assertTrue(seccion.contains((50, 50)))
        self.assertFalse(seccion.contains((150, 50)))
        self.assertFalse(seccion.contains((-1, 50)))

    def test_distancia_al_borde(self):
        seccion = cn.Section([cuadrado(100)])
        self.assertAlmostEqual(seccion.clearance_at((50, 50)), 50.0)
        self.assertAlmostEqual(seccion.clearance_at((10, 50)), 10.0)
        self.assertAlmostEqual(seccion.clearance_at((200, 200)), 0.0)

    def test_seccion_con_agujero(self):
        # Cuadrado de 100 con un agujero de 40 centrado: regla par-impar
        seccion = cn.Section([cuadrado(100), cuadrado(40, origen=(30, 30))])
        self.assertTrue(seccion.contains((10, 50)))
        self.assertFalse(seccion.contains((50, 50)), "el centro está en el agujero")
        self.assertAlmostEqual(seccion.area(), 10000.0 - 1600.0)

    def test_seccion_vacia(self):
        self.assertTrue(cn.Section([]).is_empty)
        self.assertTrue(cn.Section([[(0, 0), (1, 1)]]).is_empty)


class TestColocacion(unittest.TestCase):
    def test_seccion_amplia_admite_varios(self):
        seccion = cn.Section([cuadrado(100)])
        resultado = cn.place_connectors(seccion, cn.magnet(6.0, 3.0))
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.count, 4)
        self.assertTrue(resultado.prevents_rotation)

    def test_todos_los_puntos_caen_dentro_con_material_suficiente(self):
        seccion = cn.Section([cuadrado(100)])
        spec = cn.magnet(8.0, 3.0)
        resultado = cn.place_connectors(seccion, spec)
        for punto in resultado.points:
            self.assertTrue(seccion.contains(punto))
            self.assertGreaterEqual(
                seccion.clearance_at(punto), spec.required_clearance - 1e-9
            )

    def test_los_puntos_guardan_la_separacion(self):
        seccion = cn.Section([cuadrado(100)])
        spec = cn.magnet(6.0, 3.0)
        resultado = cn.place_connectors(seccion, spec)
        puntos = resultado.points
        for i in range(len(puntos)):
            for j in range(i + 1, len(puntos)):
                d = ((puntos[i][0] - puntos[j][0]) ** 2 + (puntos[i][1] - puntos[j][1]) ** 2) ** 0.5
                self.assertGreaterEqual(d, spec.spacing - 1e-9)

    def test_no_se_mete_un_conector_en_el_agujero(self):
        seccion = cn.Section([cuadrado(100), cuadrado(60, origen=(20, 20))])
        resultado = cn.place_connectors(seccion, cn.magnet(5.0, 2.0))
        for punto in resultado.points:
            self.assertTrue(seccion.contains(punto))

    def test_seccion_estrecha_no_admite_nada(self):
        # Franja de 4 mm de ancho: un imán de 10 no cabe de ninguna manera
        seccion = cn.Section([rectangulo(200, 4)])
        resultado = cn.place_connectors(seccion, cn.magnet(10.0, 3.0))
        self.assertFalse(resultado.ok)
        self.assertIn("material alrededor", resultado.reason)
        self.assertIn("No cabe", resultado.describe())

    def test_seccion_justa_admite_uno_solo(self):
        # Tira larga y estrecha: caben varios en fila pero ninguno gira
        seccion = cn.Section([rectangulo(120, 14)])
        resultado = cn.place_connectors(seccion, cn.dowel(1.75, 16.0))
        self.assertTrue(resultado.ok)
        self.assertGreaterEqual(resultado.count, 2)

    def test_el_tope_se_respeta(self):
        seccion = cn.Section([cuadrado(300)])
        resultado = cn.place_connectors(seccion, cn.magnet(6.0, 3.0), max_count=2)
        self.assertEqual(resultado.count, 2)

    def test_un_solo_conector_avisa_del_giro(self):
        seccion = cn.Section([cuadrado(22)])
        resultado = cn.place_connectors(seccion, cn.magnet(8.0, 3.0))
        self.assertEqual(resultado.count, 1)
        self.assertFalse(resultado.prevents_rotation)
        self.assertIn("girar", resultado.describe())

    def test_seccion_vacia(self):
        resultado = cn.place_connectors(cn.Section([]), cn.magnet(6.0, 3.0))
        self.assertFalse(resultado.ok)
        self.assertIn("vacía", resultado.reason)


class TestMedidasQueCaben(unittest.TestCase):
    def test_ordenadas_de_mayor_a_menor(self):
        seccion = cn.Section([cuadrado(100)])
        salida = cn.fitting_sizes(seccion, cn.MAGNET_SIZES)
        diametros = [spec.diameter for spec, _ in salida]
        self.assertEqual(diametros, sorted(diametros, reverse=True))

    def test_en_seccion_pequena_solo_caben_los_pequenos(self):
        seccion = cn.Section([cuadrado(18)])
        salida = dict((spec.diameter, cantidad) for spec, cantidad in cn.fitting_sizes(
            seccion, cn.MAGNET_SIZES
        ))
        self.assertEqual(salida[12.0], 0)
        self.assertGreaterEqual(salida[5.0], 1)

    def test_dowels(self):
        seccion = cn.Section([cuadrado(60)])
        salida = cn.fitting_sizes(seccion, cn.DOWEL_SIZES, kind=cn.DOWEL)
        self.assertTrue(all(cantidad >= 1 for _spec, cantidad in salida))


class TestSeccionEnL(unittest.TestCase):
    """La sección real del ejemplo: el corte en Z = 130 da un rectángulo,
    pero el corte en X = 210 atraviesa la L y da una escuadra."""

    def setUp(self):
        self.seccion = cn.Section(
            [[(0, 0), (180, 0), (180, 60), (120, 60), (120, 260), (0, 260)]]
        )

    def test_hay_sitio_para_imanes(self):
        resultado = cn.place_connectors(self.seccion, cn.magnet(6.0, 3.0))
        self.assertTrue(resultado.ok)
        self.assertTrue(resultado.prevents_rotation)

    def test_ningun_punto_cae_en_el_hueco_de_la_l(self):
        resultado = cn.place_connectors(self.seccion, cn.magnet(8.0, 3.0))
        for punto in resultado.points:
            self.assertTrue(self.seccion.contains(punto), punto)


if __name__ == "__main__":
    unittest.main()
