"""Análisis de la malla: ¿está cerrada?, ¿tiene volumen?, ¿es imprimible?

Trabaja sobre `MeshData` (triángulos en coordenadas de mundo) para poder
probarse sin Blender. La regla del proyecto es que este módulo nunca modifica
nada: solo mide y describe.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set, Tuple

from .geometry import BBox, MeshData, mesh_area, mesh_volume, triangle_area
from .mesh_cleanup import weld_vertices

STATUS_OK = "OK"
STATUS_WARNING = "AVISO"
STATUS_ERROR = "ERROR"

#: Área por debajo de la cual un triángulo se considera degenerado (mm²).
DEGENERATE_AREA_EPS = 1e-9
#: Volumen mínimo para considerar que la malla "tiene volumen" (mm³).
MIN_SOLID_VOLUME = 1e-6


@dataclass
class MeshReport:
    """Resultado del análisis, ya en milímetros."""

    name: str = ""
    unit: str = "MM"
    unit_factor: float = 1.0

    vertex_count: int = 0
    edge_count: int = 0
    polygon_count: int = 0
    triangle_count: int = 0

    boundary_edges: int = 0
    non_manifold_edges: int = 0
    inconsistent_edges: int = 0
    degenerate_triangles: int = 0
    loose_vertices: int = 0
    shell_count: int = 0
    welded_vertices: int = 0

    is_watertight: bool = False
    is_manifold: bool = False
    normals_flipped: bool = False
    has_volume: bool = False

    volume_mm3: float = 0.0
    area_mm2: float = 0.0
    dimensions_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_min_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def is_solid(self) -> bool:
        """Sólido = cerrado, manifold y con volumen real. Requisito para cortar."""
        return self.is_watertight and self.is_manifold and self.has_volume

    @property
    def status(self) -> str:
        if self.errors:
            return STATUS_ERROR
        if self.warnings:
            return STATUS_WARNING
        return STATUS_OK

    @property
    def volume_cm3(self) -> float:
        return self.volume_mm3 / 1000.0

    @property
    def area_cm2(self) -> float:
        return self.area_mm2 / 100.0

    def summary(self) -> str:
        dx, dy, dz = self.dimensions_mm
        estado = "sólido cerrado" if self.is_solid else "no apto para cortar"
        return (
            f"{self.name or 'malla'}: {dx:.2f} × {dy:.2f} × {dz:.2f} mm, "
            f"{self.volume_cm3:.2f} cm³, {estado}"
        )


def _edge_key(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _count_shells(triangles: Sequence[Tuple[int, int, int]], vertex_count: int) -> int:
    """Número de islas conectadas por aristas compartidas.

    Importa porque un STL escaneado puede traer trozos sueltos que romperían el
    corte posterior aunque cada trozo esté cerrado.
    """
    if not triangles:
        return 0
    adjacency: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for idx, (i, j, k) in enumerate(triangles):
        for a, b in ((i, j), (j, k), (k, i)):
            adjacency[_edge_key(a, b)].append(idx)

    visited: Set[int] = set()
    shells = 0
    for start in range(len(triangles)):
        if start in visited:
            continue
        shells += 1
        stack = [start]
        visited.add(start)
        while stack:
            tri = stack.pop()
            i, j, k = triangles[tri]
            for a, b in ((i, j), (j, k), (k, i)):
                for neighbour in adjacency[_edge_key(a, b)]:
                    if neighbour not in visited:
                        visited.add(neighbour)
                        stack.append(neighbour)
    return shells


def analyze_mesh(
    mesh: MeshData,
    unit_factor: float = 1.0,
    unit: str = "MM",
    weld_tolerance: float = 0.0,
) -> MeshReport:
    """Analiza la malla y devuelve el informe en milímetros.

    `unit_factor` convierte las unidades de entrada a milímetros; se aplica aquí
    y no antes para no duplicar la malla en memoria solo por cambiar de escala.
    `weld_tolerance` (en unidades de entrada) funde vértices coincidentes en una
    copia: sin esto, cualquier STL parece una malla abierta.
    """
    report = MeshReport(name=mesh.name, unit=unit, unit_factor=unit_factor)

    if mesh.is_empty:
        report.errors.append("La malla no tiene geometría (0 vértices o 0 caras)")
        return report

    if weld_tolerance > 0.0:
        mesh, fundidos = weld_vertices(mesh, weld_tolerance)
        report.welded_vertices = fundidos

    verts = mesh.vertices
    tris = mesh.triangles

    report.vertex_count = mesh.source_vertex_count
    report.edge_count = mesh.source_edge_count
    report.polygon_count = mesh.source_polygon_count
    report.triangle_count = len(tris)

    # --- Topología: aristas compartidas ---------------------------------
    undirected: Counter = Counter()
    directed: Counter = Counter()
    used_vertices: Set[int] = set()
    degenerate = 0

    for i, j, k in tris:
        used_vertices.update((i, j, k))
        if i == j or j == k or k == i:
            degenerate += 1
            continue
        if triangle_area(verts[i], verts[j], verts[k]) < DEGENERATE_AREA_EPS:
            degenerate += 1
        for a, b in ((i, j), (j, k), (k, i)):
            undirected[_edge_key(a, b)] += 1
            directed[(a, b)] += 1

    boundary = sum(1 for count in undirected.values() if count == 1)
    non_manifold = sum(1 for count in undirected.values() if count > 2)
    # En una malla cerrada y bien orientada cada arista aparece una vez en cada
    # sentido; si aparece dos veces en el mismo sentido, hay caras invertidas.
    inconsistent = sum(1 for count in directed.values() if count > 1)

    report.boundary_edges = boundary
    report.non_manifold_edges = non_manifold
    report.inconsistent_edges = inconsistent
    report.degenerate_triangles = degenerate
    report.loose_vertices = max(0, len(verts) - len(used_vertices))
    report.shell_count = _count_shells(tris, len(verts))

    report.is_watertight = boundary == 0
    report.is_manifold = non_manifold == 0

    # --- Medidas ---------------------------------------------------------
    f = float(unit_factor)
    bbox = BBox.from_points(verts).scaled(f)
    report.bbox_min_mm = bbox.min
    report.bbox_max_mm = bbox.max
    report.dimensions_mm = bbox.size

    signed_volume = mesh_volume(mesh) * (f ** 3)
    report.normals_flipped = signed_volume < 0.0 and report.is_watertight
    report.volume_mm3 = abs(signed_volume)
    report.area_mm2 = mesh_area(mesh) * (f ** 2)
    report.has_volume = report.volume_mm3 > MIN_SOLID_VOLUME and report.is_watertight

    # --- Diagnóstico -----------------------------------------------------
    if boundary:
        report.errors.append(
            f"Malla abierta: {boundary} aristas de borde (agujeros o superficie sin espesor)"
        )
    if non_manifold:
        report.errors.append(
            f"Geometría no-manifold: {non_manifold} aristas compartidas por más de dos caras"
        )
    if report.is_watertight and report.volume_mm3 <= MIN_SOLID_VOLUME:
        report.errors.append("La malla está cerrada pero su volumen es cero: no es un sólido")
    if inconsistent:
        report.warnings.append(
            f"Normales inconsistentes: {inconsistent} aristas con dos caras en el mismo sentido"
        )
    if report.normals_flipped:
        report.warnings.append("Normales invertidas: el sólido está del revés (volumen negativo)")
    if degenerate:
        report.warnings.append(f"{degenerate} triángulos degenerados (área nula)")
    if report.loose_vertices:
        report.warnings.append(f"{report.loose_vertices} vértices sueltos sin cara")
    if report.shell_count > 1:
        report.warnings.append(
            f"{report.shell_count} islas separadas: se cortarán como un único modelo"
        )
    if report.welded_vertices:
        report.notes.append(
            f"{report.welded_vertices} vértices coincidentes fundidos para el análisis "
            "(el original no se toca)"
        )
    if report.is_solid:
        report.notes.append("Malla cerrada, manifold y con volumen: apta para cortar")

    return report
