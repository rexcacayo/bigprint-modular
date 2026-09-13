"""Tipos y utilidades geométricas puras (sin bpy).

Todo el núcleo trabaja con listas de tuplas para poder ejecutarse y probarse
fuera de Blender: así los tests no necesitan arrancar Blender ni bpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple

Vec3 = Tuple[float, float, float]
Tri = Tuple[int, int, int]


@dataclass(frozen=True)
class BBox:
    """Caja envolvente alineada a los ejes."""

    min: Vec3
    max: Vec3

    @classmethod
    def from_points(cls, points: Iterable[Vec3]) -> "BBox":
        it = iter(points)
        try:
            first = next(it)
        except StopIteration:
            raise ValueError("No se puede calcular la caja de una malla sin vértices")

        min_x, min_y, min_z = first
        max_x, max_y, max_z = first
        for x, y, z in it:
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
            if z < min_z:
                min_z = z
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y
            if z > max_z:
                max_z = z
        return cls((min_x, min_y, min_z), (max_x, max_y, max_z))

    @property
    def size(self) -> Vec3:
        return (
            self.max[0] - self.min[0],
            self.max[1] - self.min[1],
            self.max[2] - self.min[2],
        )

    @property
    def center(self) -> Vec3:
        return (
            (self.max[0] + self.min[0]) * 0.5,
            (self.max[1] + self.min[1]) * 0.5,
            (self.max[2] + self.min[2]) * 0.5,
        )

    @property
    def volume(self) -> float:
        sx, sy, sz = self.size
        return sx * sy * sz

    @property
    def longest_axis(self) -> int:
        sx, sy, sz = self.size
        return max(range(3), key=lambda i: (sx, sy, sz)[i])

    def scaled(self, factor: float) -> "BBox":
        return BBox(
            tuple(v * factor for v in self.min),  # type: ignore[arg-type]
            tuple(v * factor for v in self.max),  # type: ignore[arg-type]
        )


@dataclass
class MeshData:
    """Malla triangulada en coordenadas de mundo, más los recuentos originales.

    Se guardan los recuentos de la topología original (antes de triangular)
    porque son los que el usuario ve en Blender; los triángulos solo se usan
    para los cálculos de volumen y estanqueidad.
    """

    vertices: List[Vec3] = field(default_factory=list)
    triangles: List[Tri] = field(default_factory=list)
    source_vertex_count: int = 0
    source_edge_count: int = 0
    source_polygon_count: int = 0
    name: str = ""

    def __post_init__(self) -> None:
        if not self.source_vertex_count:
            self.source_vertex_count = len(self.vertices)
        if not self.source_polygon_count:
            self.source_polygon_count = len(self.triangles)

    @property
    def is_empty(self) -> bool:
        return not self.vertices or not self.triangles

    def bbox(self) -> BBox:
        return BBox.from_points(self.vertices)

    def scaled(self, factor: float) -> "MeshData":
        return MeshData(
            vertices=[(x * factor, y * factor, z * factor) for x, y, z in self.vertices],
            triangles=list(self.triangles),
            source_vertex_count=self.source_vertex_count,
            source_edge_count=self.source_edge_count,
            source_polygon_count=self.source_polygon_count,
            name=self.name,
        )


def triangle_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def signed_tetra_volume(a: Vec3, b: Vec3, c: Vec3) -> float:
    """Volumen con signo del tetraedro origen-triángulo (teorema de la divergencia).

    Sumado sobre una malla cerrada da el volumen encerrado; el signo indica si
    las normales apuntan hacia fuera (positivo) o están invertidas (negativo).
    """
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    ) / 6.0


def mesh_volume(mesh: MeshData) -> float:
    """Volumen con signo de la malla, en unidades cúbicas de entrada."""
    verts = mesh.vertices
    total = 0.0
    for i, j, k in mesh.triangles:
        total += signed_tetra_volume(verts[i], verts[j], verts[k])
    return total


def mesh_area(mesh: MeshData) -> float:
    verts = mesh.vertices
    return sum(triangle_area(verts[i], verts[j], verts[k]) for i, j, k in mesh.triangles)


def sort_dims(dims: Sequence[float]) -> Tuple[float, float, float]:
    ordered = sorted(dims, reverse=True)
    return (ordered[0], ordered[1], ordered[2])
