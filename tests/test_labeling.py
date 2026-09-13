import unittest

import _context  # noqa: F401

from core import connectors as cn
from core import labeling as lb


def cuadrado(lado, origen=(0.0, 0.0)):
    u, v = origen
    return [(u, v), (u + lado, v), (u + lado, v + lado), (u, v + lado)]


class TestTexto(unittest.TestCase):
    def test_numeracion_con_ceros(self):
        self.assertEqual(lb.label_text(1), "01")
        self.assertEqual(lb.label_text(12), "12")
        self.assertEqual(lb.label_text(5, digits=3), "005")

    def test_indice_invalido(self):
        with self.assertRaises(ValueError):
            lb.label_text(0)

    def test_caja_del_texto(self):
        ancho, alto = lb.text_box("01", 10.0)
        self.assertEqual(alto, 10.0)
        self.assertGreater(ancho, 10.0)  # dos dígitos son más anchos que altos


class TestColocacion(unittest.TestCase):
    def test_sitio_de_sobra(self):
        seccion = cn.Section([cuadrado(200)])
        spot = lb.best_spot(seccion, "01", desired_height=10.0)
        self.assertIsNotNone(spot)
        self.assertTrue(spot.ok)
        self.assertEqual(spot.height, 10.0, "no debe encoger si cabe entero")
        self.assertTrue(seccion.contains(spot.point))

    def test_se_encoge_si_no_cabe(self):
        seccion = cn.Section([cuadrado(20)])
        spot = lb.best_spot(seccion, "01", desired_height=30.0)
        self.assertIsNotNone(spot)
        self.assertLess(spot.height, 30.0)

    def test_demasiado_pequeno_para_leerse(self):
        seccion = cn.Section([[(0, 0), (60, 0), (60, 3), (0, 3)]])
        spot = lb.best_spot(seccion, "01", desired_height=10.0)
        self.assertIsNotNone(spot)
        self.assertFalse(spot.ok, "debe avisar de que no se leería")

    def test_el_punto_esta_metido_en_el_material(self):
        seccion = cn.Section([[(0, 0), (200, 0), (200, 60), (120, 60), (120, 260), (0, 260)]])
        spot = lb.best_spot(seccion, "03", desired_height=12.0)
        self.assertTrue(seccion.contains(spot.point))
        self.assertGreater(spot.clearance, 0.0)

    def test_no_cae_en_un_agujero(self):
        seccion = cn.Section([cuadrado(100), cuadrado(60, origen=(20, 20))])
        spot = lb.best_spot(seccion, "01", desired_height=8.0)
        self.assertTrue(seccion.contains(spot.point))

    def test_seccion_vacia(self):
        self.assertIsNone(lb.best_spot(cn.Section([]), "01"))


if __name__ == "__main__":
    unittest.main()
