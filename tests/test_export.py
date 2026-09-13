import os
import struct
import tempfile
import unittest

import _context  # noqa: F401

from core import parts_list, stl_io
from core.sample_shapes import box, l_bracket


class TestEscrituraStl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "pieza.stl")

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        os.rmdir(self.tmp)

    def test_tamano_exacto(self):
        malla = l_bracket()
        escritos = stl_io.write_binary_stl(malla, self.path)
        self.assertEqual(escritos, stl_io.expected_size(len(malla.triangles)))
        self.assertEqual(os.path.getsize(self.path), escritos)

    def test_cabecera_y_recuento(self):
        malla = box(10, 20, 30)
        stl_io.write_binary_stl(malla, self.path)
        with open(self.path, "rb") as f:
            cabecera = f.read(80)
            (n,) = struct.unpack("<I", f.read(4))
        self.assertEqual(n, len(malla.triangles))
        self.assertIn(b"BigPrint", cabecera)

    def test_las_coordenadas_van_en_milimetros(self):
        # Una caja de 0,2 unidades escalada a mm debe medir 200 en el fichero
        malla = box(0.2, 0.2, 0.2).scaled(1000.0)
        stl_io.write_binary_stl(malla, self.path)
        with open(self.path, "rb") as f:
            f.read(84)
            f.read(12)  # normal
            coords = struct.unpack("<9f", f.read(36))
        self.assertLessEqual(max(abs(c) for c in coords), 200.0 + 1e-3)
        self.assertGreater(max(abs(c) for c in coords), 1.0)

    def test_normales_unitarias(self):
        malla = box(10, 10, 10)
        stl_io.write_binary_stl(malla, self.path)
        with open(self.path, "rb") as f:
            f.read(84)
            nx, ny, nz = struct.unpack("<3f", f.read(12))
        self.assertAlmostEqual((nx * nx + ny * ny + nz * nz) ** 0.5, 1.0, places=5)


class TestNombresDeFichero(unittest.TestCase):
    def test_caracteres_prohibidos(self):
        self.assertEqual(stl_io.safe_filename('pieza:1/2?'), "pieza_1_2_")
        self.assertEqual(stl_io.safe_filename("normal_01"), "normal_01")

    def test_nunca_devuelve_vacio(self):
        self.assertEqual(stl_io.safe_filename("   "), "pieza")
        self.assertEqual(stl_io.safe_filename("..."), "pieza")


class TestListaDePiezas(unittest.TestCase):
    def filas(self):
        return [
            parts_list.PartRow(1, "p_01", "p_01.stl", (210.0, 180.0, 130.0), 3780.0, True, True),
            parts_list.PartRow(2, "p_02", "p_02.stl", (210.0, 180.0, 60.0), 2268.0, True, True),
            parts_list.PartRow(3, "p_03", "p_03.stl", (120.0, 180.0, 130.0), 2808.0, False, False),
        ]

    def test_cabecera_y_filas(self):
        texto = parts_list.csv_text(self.filas())
        lineas = texto.strip().split("\n")
        self.assertEqual(len(lineas), 4)
        self.assertTrue(lineas[0].startswith("pieza;fichero"))
        self.assertIn("p_01.stl", lineas[1])

    def test_volumen_total(self):
        self.assertAlmostEqual(parts_list.total_volume_cm3(self.filas()), 8856.0)

    def test_resumen_avisa_de_problemas(self):
        resumen = parts_list.summary(self.filas())
        self.assertIn("3 piezas", resumen)
        self.assertIn("8856.0 cm³", resumen)
        self.assertIn("1 sin cerrar", resumen)
        self.assertIn("1 que no caben", resumen)

    def test_resumen_limpio(self):
        buenas = [f for f in self.filas() if f.watertight and f.fits]
        resumen = parts_list.summary(buenas)
        self.assertNotIn("sin cerrar", resumen)

    def test_sin_piezas(self):
        self.assertEqual(parts_list.summary([]), "Sin piezas")

    def test_separador_para_excel_espanol(self):
        self.assertIn(";", parts_list.csv_text(self.filas()))


if __name__ == "__main__":
    unittest.main()
