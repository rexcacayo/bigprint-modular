import unittest

import _context  # noqa: F401

from core import explode


class TestCentroDelConjunto(unittest.TestCase):
    def test_media_de_los_centros(self):
        centros = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
        self.assertEqual(explode.assembly_center(centros), (50.0, 0.0, 0.0))

    def test_sin_piezas(self):
        self.assertEqual(explode.assembly_center([]), (0.0, 0.0, 0.0))


class TestDesplazamientos(unittest.TestCase):
    def setUp(self):
        # Cuatro piezas en cuadrado alrededor del origen
        self.centros = [
            (-50.0, 0.0, -50.0),
            (50.0, 0.0, -50.0),
            (-50.0, 0.0, 50.0),
            (50.0, 0.0, 50.0),
        ]

    def test_factor_cero_no_mueve_nada(self):
        for offset in explode.explode_offsets(self.centros, 0.0):
            self.assertEqual(offset, (0.0, 0.0, 0.0))

    def test_cada_pieza_sale_hacia_su_lado(self):
        offsets = explode.explode_offsets(self.centros, 1.0)
        for centro, offset in zip(self.centros, offsets):
            self.assertGreater(centro[0] * offset[0], 0, "se aleja en X, no se acerca")
            self.assertGreater(centro[2] * offset[2], 0, "se aleja en Z, no se acerca")

    def test_el_factor_escala(self):
        mitad = explode.explode_offsets(self.centros, 0.5)
        entero = explode.explode_offsets(self.centros, 1.0)
        for a, b in zip(mitad, entero):
            self.assertAlmostEqual(a[0] * 2, b[0])

    def test_la_pieza_mas_lejana_se_mueve_mas(self):
        centros = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
        offsets = explode.explode_offsets(centros, 1.0)
        self.assertGreater(abs(offsets[2][0]), abs(offsets[1][0]))

    def test_una_pieza_en_el_centro_no_se_queda_encima(self):
        centros = [(0.0, 0.0, 0.0)]
        offsets = explode.explode_offsets(centros, 1.0)
        self.assertEqual(offsets[0], (0.0, 0.0, 0.0), "una sola pieza no se mueve")

        centros = [(-50.0, 0.0, 0.0), (50.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
        offsets = explode.explode_offsets(centros, 1.0)
        self.assertNotEqual(offsets[2], (0.0, 0.0, 0.0))

    def test_el_conjunto_no_se_desplaza(self):
        # Al explotar, el centro del conjunto sigue donde estaba
        offsets = explode.explode_offsets(self.centros, 0.7)
        nuevos = [
            (c[0] + o[0], c[1] + o[1], c[2] + o[2]) for c, o in zip(self.centros, offsets)
        ]
        centro = explode.assembly_center(nuevos)
        for componente in centro:
            self.assertAlmostEqual(componente, 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
