"""Extracción de la sección de corte a partir de la malla de una pieza.

Tras cortar, la cara nueva de la pieza queda sobre el plano de corte. Aquí se
buscan esas caras y se reconstruye su contorno, que es lo que necesita el
colocador de conectores.

No se usa la cara tal cual porque el tapado puede haberla dejado en varios
triángulos: se toman las aristas que solo pertenecen a una cara de la tapa, que
son exactamente el contorno.
"""

from collections import defaultdict
from typing import Dict, List, Sequence, Set, Tuple

from .connectors import Section, Vec2
from .geometry import MeshData

#: Tolerancia por defecto para considerar que un vértice está sobre el plano.
PLANE_TOLERANCE = 1e-3


def faces_on_plane(
    mesh: MeshData, axis: int, position: float, tolerance: float = PLANE_TOLERANCE
) -> List[int]:
    """Índices de los triángulos que están completamente sobre el plano."""
    verts = mesh.vertices
    encontrados = []
    for indice, (i, j, k) in enumerate(mesh.triangles):
        if all(abs(verts[v][axis] - position) <= tolerance for v in (i, j, k)):
            encontrados.append(indice)
    return encontrados


def _boundary_edges(mesh: MeshData, face_indices: Sequence[int]) -> List[Tuple[int, int]]:
    """Aristas usadas por una sola de esas caras: el contorno de la tapa."""
    cuenta: Dict[Tuple[int, int], int] = defaultdict(int)
    for indice in face_indices:
        i, j, k = mesh.triangles[indice]
        for a, b in ((i, j), (j, k), (k, i)):
            cuenta[(a, b) if a < b else (b, a)] += 1
    return [arista for arista, veces in cuenta.items() if veces == 1]


def _build_loops(edges: Sequence[Tuple[int, int]]) -> List[List[int]]:
    """Encadena las aristas sueltas en contornos cerrados."""
    vecinos: Dict[int, List[int]] = defaultdict(list)
    for a, b in edges:
        vecinos[a].append(b)
        vecinos[b].append(a)

    pendientes: Set[Tuple[int, int]] = {(a, b) if a < b else (b, a) for a, b in edges}
    loops: List[List[int]] = []

    while pendientes:
        a, b = next(iter(pendientes))
        pendientes.discard((a, b))
        loop = [a, b]
        actual, anterior = b, a

        while True:
            siguiente = None
            for candidato in vecinos[actual]:
                if candidato == anterior:
                    continue
                clave = (actual, candidato) if actual < candidato else (candidato, actual)
                if clave in pendientes:
                    siguiente = candidato
                    pendientes.discard(clave)
                    break
            if siguiente is None:
                break  # contorno abierto: se descarta más abajo
            if siguiente == loop[0]:
                break  # cerrado
            loop.append(siguiente)
            anterior, actual = actual, siguiente

        if len(loop) >= 3:
            loops.append(loop)

    return loops


def plane_axes(axis: int) -> Tuple[int, int]:
    """Los dos ejes que forman el plano, en orden estable.

    Se mantiene el orden cíclico X→Y→Z para que la proyección no quede
    reflejada, que invertiría izquierda y derecha al devolver los puntos a 3D.
    """
    return ((1, 2), (2, 0), (0, 1))[axis]


def to_3d(point: Vec2, axis: int, position: float) -> Tuple[float, float, float]:
    """Devuelve un punto del plano a coordenadas de mundo."""
    u_axis, v_axis = plane_axes(axis)
    salida = [0.0, 0.0, 0.0]
    salida[axis] = position
    salida[u_axis] = point[0]
    salida[v_axis] = point[1]
    return (salida[0], salida[1], salida[2])


def extract_section(
    mesh: MeshData, axis: int, position: float, tolerance: float = PLANE_TOLERANCE
) -> Section:
    """Sección de la malla sobre el plano, en coordenadas 2D del propio plano."""
    caras = faces_on_plane(mesh, axis, position, tolerance)
    if not caras:
        return Section([])

    aristas = _boundary_edges(mesh, caras)
    if not aristas:
        return Section([])

    u_axis, v_axis = plane_axes(axis)
    verts = mesh.vertices

    loops: List[List[Vec2]] = []
    for loop in _build_loops(aristas):
        loops.append([(verts[i][u_axis], verts[i][v_axis]) for i in loop])

    return Section(loops)


# --------------------------------------------------------------------------- planos inclinados
def faces_on_any_plane(mesh: MeshData, plane, tolerance: float = PLANE_TOLERANCE) -> List[int]:
    """Como `faces_on_plane`, para un `planes.Plane` con cualquier orientación."""
    verts = mesh.vertices
    encontrados = []
    for indice, (i, j, k) in enumerate(mesh.triangles):
        if all(abs(plane.distance(verts[v])) <= tolerance for v in (i, j, k)):
            encontrados.append(indice)
    return encontrados


def extract_section_plane(mesh: MeshData, plane, tolerance: float = PLANE_TOLERANCE) -> Section:
    """Sección sobre un plano cualquiera, en las coordenadas 2D de ese plano.

    Para un plano de eje da exactamente lo mismo que `extract_section`."""
    if plane.axis is not None:
        return extract_section(mesh, plane.axis, plane.origin[plane.axis], tolerance)
    caras = faces_on_any_plane(mesh, plane, tolerance)
    if not caras:
        return Section([])
    aristas = _boundary_edges(mesh, caras)
    if not aristas:
        return Section([])
    verts = mesh.vertices
    return Section([[plane.to_2d(verts[i]) for i in loop] for loop in _build_loops(aristas)])
