"""Limpieza no destructiva sobre la copia de trabajo.

Un STL guarda cada triángulo con sus tres vértices repetidos: sin soldar, una
pieza perfectamente cerrada aparece como una malla llena de aristas de borde.
Por eso el análisis suelda primero la copia temporal (nunca el original).
"""

from typing import Dict, List, Tuple

from .geometry import MeshData, Tri, Vec3


def weld_vertices(mesh: MeshData, tolerance: float = 1e-4) -> Tuple[MeshData, int]:
    """Funde vértices coincidentes y devuelve (malla nueva, vértices fundidos).

    Se usa una rejilla de redondeo en vez de una búsqueda por distancia: es
    O(n) y basta para el caso real (coordenadas idénticas bit a bit repetidas
    por el formato STL). Puntos separados justo por el borde de una celda
    podrían no fundirse, algo asumible con tolerancias pequeñas.
    """
    if tolerance <= 0.0:
        return mesh, 0

    inv = 1.0 / tolerance
    mapa: Dict[Tuple[int, int, int], int] = {}
    nuevos: List[Vec3] = []
    remap: List[int] = []

    for x, y, z in mesh.vertices:
        clave = (int(round(x * inv)), int(round(y * inv)), int(round(z * inv)))
        idx = mapa.get(clave)
        if idx is None:
            idx = len(nuevos)
            mapa[clave] = idx
            nuevos.append((x, y, z))
        remap.append(idx)

    fundidos = len(mesh.vertices) - len(nuevos)
    if fundidos == 0:
        return mesh, 0

    triangulos: List[Tri] = []
    for i, j, k in mesh.triangles:
        triangulos.append((remap[i], remap[j], remap[k]))

    limpia = MeshData(
        vertices=nuevos,
        triangles=triangulos,
        source_vertex_count=mesh.source_vertex_count,
        source_edge_count=mesh.source_edge_count,
        source_polygon_count=mesh.source_polygon_count,
        name=mesh.name,
    )
    return limpia, fundidos
