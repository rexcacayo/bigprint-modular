import unittest

import _context  # noqa: F401

from core.geometry import MeshData
from core.mesh_analysis import STATUS_ERROR, STATUS_OK, analyze_mesh
from core.sample_shapes import box, flat_plane, l_bracket, open_box


class TestClosedSolid(unittest.TestCase):
    def setUp(self):
        self.report = analyze_mesh(box(100, 50, 25))

    def test_is_solid(self):
        r = self.report
        self.assertTrue(r.is_watertight)
        self.assertTrue(r.is_manifold)
        self.assertTrue(r.has_volume)
        self.assertTrue(r.is_solid)
        self.assertEqual(r.status, STATUS_OK)
        self.assertFalse(r.errors)

    def test_measures(self):
        r = self.report
        self.assertEqual(r.dimensions_mm, (100.0, 50.0, 25.0))
        self.assertAlmostEqual(r.volume_mm3, 125000.0)
        self.assertAlmostEqual(r.volume_cm3, 125.0)
        self.assertEqual(r.boundary_edges, 0)
        self.assertEqual(r.non_manifold_edges, 0)
        self.assertEqual(r.shell_count, 1)
        self.assertEqual(r.degenerate_triangles, 0)

    def test_normals_not_flipped(self):
        self.assertFalse(self.report.normals_flipped)


class TestOpenMesh(unittest.TestCase):
    def test_open_box_is_detected(self):
        r = analyze_mesh(open_box(100, 100, 100))
        self.assertFalse(r.is_watertight)
        self.assertFalse(r.is_solid)
        self.assertFalse(r.has_volume)
        self.assertGreater(r.boundary_edges, 0)
        self.assertEqual(r.status, STATUS_ERROR)

    def test_flat_plane_has_no_volume(self):
        r = analyze_mesh(flat_plane(50))
        self.assertFalse(r.is_watertight)
        self.assertFalse(r.has_volume)
        self.assertEqual(r.dimensions_mm, (50.0, 50.0, 0.0))
        self.assertAlmostEqual(r.area_mm2, 2500.0)

    def test_empty_mesh(self):
        r = analyze_mesh(MeshData())
        self.assertEqual(r.status, STATUS_ERROR)
        self.assertFalse(r.is_solid)


class TestFlippedNormals(unittest.TestCase):
    def test_inverted_winding(self):
        cube = box(10, 10, 10)
        cube.triangles = [(c, b, a) for a, b, c in cube.triangles]
        r = analyze_mesh(cube)
        self.assertTrue(r.is_watertight)
        self.assertTrue(r.normals_flipped)
        self.assertAlmostEqual(r.volume_mm3, 1000.0)  # se informa en valor absoluto
        self.assertTrue(any("invertidas" in w for w in r.warnings))


class TestNonManifold(unittest.TestCase):
    def test_extra_face_on_edge(self):
        cube = box(10, 10, 10)
        # Se añade una aleta que comparte una arista ya usada por dos caras
        cube.vertices.append((5.0, -10.0, 5.0))
        extra = len(cube.vertices) - 1
        a, b, _ = cube.triangles[0]
        cube.triangles.append((a, b, extra))
        r = analyze_mesh(cube)
        self.assertFalse(r.is_manifold)
        self.assertEqual(r.status, STATUS_ERROR)


class TestDegenerate(unittest.TestCase):
    def test_zero_area_triangle_is_counted(self):
        cube = box(10, 10, 10)
        cube.triangles.append((0, 0, 1))
        r = analyze_mesh(cube)
        self.assertEqual(r.degenerate_triangles, 1)


class TestShells(unittest.TestCase):
    def test_two_islands(self):
        a = box(10, 10, 10)
        b = box(10, 10, 10)
        offset = len(a.vertices)
        a.vertices += [(x + 100, y, z) for x, y, z in b.vertices]
        a.triangles += [(i + offset, j + offset, k + offset) for i, j, k in b.triangles]
        r = analyze_mesh(a)
        self.assertEqual(r.shell_count, 2)
        self.assertTrue(r.is_watertight)
        self.assertAlmostEqual(r.volume_mm3, 2000.0)


class TestUnitConversion(unittest.TestCase):
    def test_model_in_meters(self):
        # Un cubo de 0,2 unidades modelado en metros son 200 mm
        cube = box(0.2, 0.2, 0.2)
        r = analyze_mesh(cube, unit_factor=1000.0, unit="M")
        self.assertAlmostEqual(r.dimensions_mm[0], 200.0)
        self.assertAlmostEqual(r.volume_mm3, 200.0 ** 3, places=3)
        self.assertAlmostEqual(r.area_mm2, 6 * 200.0 ** 2, places=3)


class TestExampleModel(unittest.TestCase):
    def test_l_bracket_is_solid_and_big(self):
        r = analyze_mesh(l_bracket())
        self.assertTrue(r.is_solid)
        self.assertEqual(r.dimensions_mm, (420.0, 180.0, 260.0))
        self.assertAlmostEqual(r.volume_cm3, 8856.0, places=3)
        self.assertIn("Malla cerrada", " ".join(r.notes))

    def test_summary_text(self):
        r = analyze_mesh(l_bracket())
        self.assertIn("420.00", r.summary())


if __name__ == "__main__":
    unittest.main()
