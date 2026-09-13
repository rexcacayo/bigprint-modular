import unittest

import _context  # noqa: F401

from core.geometry import BBox, MeshData, mesh_area, mesh_volume, triangle_area
from core.sample_shapes import box, l_bracket


class TestBBox(unittest.TestCase):
    def test_from_points(self):
        b = BBox.from_points([(0, 0, 0), (10, -2, 5), (3, 4, 1)])
        self.assertEqual(b.min, (0, -2, 0))
        self.assertEqual(b.max, (10, 4, 5))
        self.assertEqual(b.size, (10, 6, 5))
        self.assertEqual(b.center, (5.0, 1.0, 2.5))
        self.assertEqual(b.longest_axis, 0)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            BBox.from_points([])

    def test_scaled(self):
        b = BBox((0, 0, 0), (1, 2, 3)).scaled(1000)
        self.assertEqual(b.max, (1000, 2000, 3000))


class TestAreaVolume(unittest.TestCase):
    def test_triangle_area(self):
        self.assertAlmostEqual(triangle_area((0, 0, 0), (4, 0, 0), (0, 3, 0)), 6.0)

    def test_box_volume_and_area(self):
        cube = box(10, 20, 30)
        self.assertAlmostEqual(mesh_volume(cube), 6000.0)
        # 2*(10*20 + 10*30 + 20*30)
        self.assertAlmostEqual(mesh_area(cube), 2 * (200 + 300 + 600))

    def test_volume_is_translation_invariant(self):
        cube = box(10, 10, 10)
        moved = MeshData(
            vertices=[(x + 500, y - 120, z + 3) for x, y, z in cube.vertices],
            triangles=cube.triangles,
        )
        self.assertAlmostEqual(mesh_volume(cube), mesh_volume(moved), places=6)

    def test_l_bracket_volume(self):
        # Sección en L: 420*60 + (260-60)*120 = 49200 mm², por 180 mm de fondo
        mesh = l_bracket()
        self.assertAlmostEqual(mesh_volume(mesh), 49200.0 * 180.0, places=3)

    def test_scaled_mesh(self):
        cube = box(1, 1, 1).scaled(10)
        self.assertAlmostEqual(mesh_volume(cube), 1000.0)


if __name__ == "__main__":
    unittest.main()
