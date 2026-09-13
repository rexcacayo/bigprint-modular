"""Sólidos generados por código, en milímetros.

Sirven para tres cosas: el ejemplo del complemento, el STL de muestra y los
tests (son mallas con volumen conocido de antemano, así se valida el análisis
sin depender de ningún fichero externo).
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .geometry import MeshData, Tri, Vec3, mesh_volume


def _ensure_outward(mesh: MeshData) -> MeshData:
    """Invierte el bobinado si el volumen sale negativo.

    Evita depender de haber ordenado bien el perfil a mano: la orientación
    correcta se deduce del signo del volumen.
    """
    if mesh_volume(mesh) < 0:
        mesh.triangles = [(c, b, a) for a, b, c in mesh.triangles]
    return mesh


def prism_from_profile(
    profile_xz: Sequence[Tuple[float, float]],
    depth: float,
    name: str = "prisma",
) -> MeshData:
    """Extruye un perfil del plano XZ a lo largo de Y.

    El perfil debe ser simple y visible al completo desde su primer vértice
    (star-shaped), porque las tapas se triangulan en abanico desde ese vértice.
    """
    n = len(profile_xz)
    if n < 3:
        raise ValueError("El perfil necesita al menos tres puntos")

    verts: List[Vec3] = [(x, 0.0, z) for x, z in profile_xz]
    verts += [(x, depth, z) for x, z in profile_xz]

    tris: List[Tri] = []
    # Laterales
    for i in range(n):
        j = (i + 1) % n
        b_i, b_j, t_i, t_j = i, j, i + n, j + n
        tris.append((b_i, b_j, t_j))
        tris.append((b_i, t_j, t_i))
    # Tapas en abanico
    for i in range(1, n - 1):
        tris.append((0, i + 1, i))
        tris.append((n, n + i, n + i + 1))

    return _ensure_outward(
        MeshData(vertices=verts, triangles=tris, source_edge_count=3 * n, name=name)
    )


def box(size_x: float, size_y: float, size_z: float, name: str = "caja") -> MeshData:
    """Caja cerrada con una esquina en el origen."""
    profile = [(0.0, 0.0), (size_x, 0.0), (size_x, size_z), (0.0, size_z)]
    mesh = prism_from_profile(profile, size_y, name=name)
    mesh.source_edge_count = 12
    mesh.source_polygon_count = 12
    return mesh


def l_bracket(
    length: float = 420.0,
    depth: float = 180.0,
    height: float = 260.0,
    bar: float = 60.0,
    column: float = 120.0,
    name: str = "BigPrint_Ejemplo_Escuadra",
) -> MeshData:
    """Escuadra en L de 420 × 180 × 260 mm: no cabe en ninguna impresora pequeña.

    Es el caso de uso del complemento en una sola pieza: larga en X, alta en Z y
    con una zona hueca que obliga a pensar dónde cortar.
    """
    if bar >= height or column >= length:
        raise ValueError("Las proporciones de la escuadra no son válidas")
    profile = [
        (0.0, 0.0),
        (length, 0.0),
        (length, bar),
        (column, bar),
        (column, height),
        (0.0, height),
    ]
    return prism_from_profile(profile, depth, name=name)


def open_box(size_x: float = 100.0, size_y: float = 100.0, size_z: float = 100.0) -> MeshData:
    """Caja sin la tapa superior: malla abierta para probar el diagnóstico."""
    mesh = box(size_x, size_y, size_z, name="caja_abierta")
    # Se quitan los dos triángulos de la tapa Y = size_y (los últimos del abanico)
    mesh.triangles = mesh.triangles[:-2]
    return mesh


def flat_plane(size: float = 100.0) -> MeshData:
    """Plano de dos triángulos: cerrado no, volumen cero."""
    verts: List[Vec3] = [(0, 0, 0), (size, 0, 0), (size, size, 0), (0, size, 0)]
    tris: List[Tri] = [(0, 1, 2), (0, 2, 3)]
    return MeshData(vertices=verts, triangles=tris, source_edge_count=5, name="plano")
