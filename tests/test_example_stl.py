"""Prueba de ida y vuelta con un STL de verdad.

Un STL no comparte vértices entre triángulos, así que releído en crudo parece
una malla abierta. Este test fija ese comportamiento y comprueba que soldar lo
resuelve, que es justo lo que hace el operador de análisis.
"""

import os
import struct
import sys
import tempfile
import unittest

import _context  # noqa: F401

sys.path.insert(0, os.path.join(_context.ADDON_DIR, "examples"))

from core.geometry import MeshData  # noqa: E402
from core.mesh_analysis import analyze_mesh  # noqa: E402
from core.mesh_cleanup import weld_vertices  # noqa: E402
from core.sample_shapes import box, l_bracket  # noqa: E402
from make_example_stl import write_binary_stl  # noqa: E402


def read_binary_stl(path: str) -> MeshData:
    """Lector mínimo de STL binario: cada triángulo con sus tres vértices."""
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        verts = []
        tris = []
        for _ in range(n):
            f.read(12)  # normal, se ignora: se recalcula desde la geometría
            base = len(verts)
            for _ in range(3):
                verts.append(struct.unpack("<3f", f.read(12)))
            f.read(2)
            tris.append((base, base + 1, base + 2))
    return MeshData(vertices=verts, triangles=tris, name=os.path.basename(path))


class TestStlRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "prueba.stl")

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        os.rmdir(self.tmp)

    def test_raw_stl_looks_open(self):
        write_binary_stl(l_bracket(), self.path)
        malla = read_binary_stl(self.path)
        informe = analyze_mesh(malla)  # sin soldar
        self.assertFalse(informe.is_watertight)
        self.assertGreater(informe.boundary_edges, 0)

    def test_welded_stl_is_solid(self):
        write_binary_stl(l_bracket(), self.path)
        malla = read_binary_stl(self.path)
        informe = analyze_mesh(malla, weld_tolerance=1e-3)
        self.assertTrue(informe.is_watertight)
        self.assertTrue(informe.is_solid)
        self.assertEqual(informe.dimensions_mm, (420.0, 180.0, 260.0))
        self.assertAlmostEqual(informe.volume_cm3, 8856.0, places=1)
        self.assertGreater(informe.welded_vertices, 0)

    def test_file_size_matches_triangle_count(self):
        malla = l_bracket()
        write_binary_stl(malla, self.path)
        esperado = 84 + 50 * len(malla.triangles)
        self.assertEqual(os.path.getsize(self.path), esperado)


class TestWeld(unittest.TestCase):
    def test_weld_reduces_vertices(self):
        malla = box(10, 10, 10)
        duplicada = MeshData(
            vertices=malla.vertices + list(malla.vertices),
            triangles=list(malla.triangles),
            name="duplicada",
        )
        limpia, fundidos = weld_vertices(duplicada, 1e-4)
        self.assertEqual(fundidos, 8)
        self.assertEqual(len(limpia.vertices), 8)

    def test_weld_is_a_no_op_when_nothing_matches(self):
        malla = box(10, 10, 10)
        limpia, fundidos = weld_vertices(malla, 1e-4)
        self.assertEqual(fundidos, 0)
        self.assertIs(limpia, malla)

    def test_zero_tolerance_does_nothing(self):
        malla = box(10, 10, 10)
        limpia, fundidos = weld_vertices(malla, 0.0)
        self.assertIs(limpia, malla)
        self.assertEqual(fundidos, 0)

    def test_weld_does_not_touch_the_input(self):
        malla = l_bracket()
        antes = len(malla.vertices)
        weld_vertices(malla, 1.0)
        self.assertEqual(len(malla.vertices), antes)


if __name__ == "__main__":
    unittest.main()
