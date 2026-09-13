"""Generación de los dowels imprimibles.

Se generan tumbados a lo largo de X, apoyados en Z = 0. Es intencionado: un
pivote impreso en vertical apila las capas justo donde va el esfuerzo cortante
y se parte al primer golpe. Tumbado, las capas corren a lo largo de la varilla
y aguanta mucho más.

Los extremos van achaflanados: un canto vivo impreso tiene siempre una rebaba
de la primera capa que impide entrar el agujero.
"""

import math
from typing import List, Optional, Tuple

from .connectors import ConnectorSpec
from .geometry import MeshData, Tri, Vec3

#: Diferencia entre el agujero y la varilla impresa, en mm de diámetro.
#: La impresión FDM saca los agujeros algo estrechos y los cilindros algo
#: gordos, así que sin esta rebaja el dowel no entra. Es un valor de partida:
#: el bueno sale de imprimir y medir.
DEFAULT_FIT_GAP = 0.15

#: Proporción del radio que se achaflana en cada extremo.
CHAMFER_RATIO = 0.25


def printed_diameter(spec: ConnectorSpec, fit_gap: float = DEFAULT_FIT_GAP) -> float:
    """Diámetro al que hay que imprimir la varilla para ese conector."""
    return max(spec.hole_diameter - fit_gap, 0.1)


def dowel_length(spec: ConnectorSpec) -> float:
    """Longitud total: la mitad entra en cada pieza."""
    return spec.depth * 2.0


def _ring(radius: float, x: float, segments: int) -> List[Vec3]:
    return [
        (
            x,
            radius * math.cos(2.0 * math.pi * s / segments),
            radius * math.sin(2.0 * math.pi * s / segments),
        )
        for s in range(segments)
    ]


def dowel_mesh(
    diameter: float,
    length: float,
    segments: int = 32,
    chamfer: Optional[float] = None,
    name: str = "dowel",
) -> MeshData:
    """Varilla cerrada, tumbada en X y apoyada en Z = 0."""
    if diameter <= 0 or length <= 0:
        raise ValueError("Diámetro y longitud deben ser positivos")

    radio = diameter * 0.5
    if chamfer is None:
        chamfer = radio * CHAMFER_RATIO
    chamfer = min(chamfer, radio * 0.4, length * 0.2)

    # Cuatro anillos: los extremos más estrechos por el chaflán
    anillos = [
        _ring(radio - chamfer, 0.0, segments),
        _ring(radio, chamfer, segments),
        _ring(radio, length - chamfer, segments),
        _ring(radio - chamfer, length, segments),
    ]

    vertices: List[Vec3] = []
    for anillo in anillos:
        vertices.extend(anillo)

    triangulos: List[Tri] = []
    for nivel in range(3):
        base_a = nivel * segments
        base_b = (nivel + 1) * segments
        for s in range(segments):
            t = (s + 1) % segments
            triangulos.append((base_a + s, base_a + t, base_b + t))
            triangulos.append((base_a + s, base_b + t, base_b + s))

    # Tapas planas en los dos extremos
    centro_inicio = len(vertices)
    vertices.append((0.0, 0.0, 0.0))
    centro_final = len(vertices)
    vertices.append((length, 0.0, 0.0))

    ultimo = 3 * segments
    for s in range(segments):
        t = (s + 1) % segments
        triangulos.append((centro_inicio, t, s))
        triangulos.append((centro_final, ultimo + s, ultimo + t))

    # Se sube para que quede apoyado en la cama en vez de partido por Z = 0
    vertices = [(x, y, z + radio) for x, y, z in vertices]

    return MeshData(vertices=vertices, triangles=triangulos, name=name)


def dowel_batch(
    count: int,
    diameter: float,
    length: float,
    spacing: Optional[float] = None,
    segments: int = 32,
    name: str = "dowels",
) -> MeshData:
    """Todas las varillas que hacen falta, en fila y listas para laminar."""
    if count < 1:
        raise ValueError("Hace falta al menos una varilla")

    separacion = spacing if spacing is not None else max(diameter * 2.5, diameter + 3.0)
    unidad = dowel_mesh(diameter, length, segments=segments)

    vertices: List[Vec3] = []
    triangulos: List[Tri] = []
    for indice in range(count):
        desplazamiento = len(vertices)
        offset = indice * separacion
        vertices.extend((x, y + offset, z) for x, y, z in unidad.vertices)
        triangulos.extend(
            (a + desplazamiento, b + desplazamiento, c + desplazamiento)
            for a, b, c in unidad.triangles
        )

    return MeshData(vertices=vertices, triangles=triangulos, name=name)


def batch_filename(spec: ConnectorSpec, count: int, fit_gap: float = DEFAULT_FIT_GAP) -> str:
    diametro = printed_diameter(spec, fit_gap)
    return f"varillas_d{diametro:.2f}_L{dowel_length(spec):.0f}_x{count}.stl"


def describe(spec: ConnectorSpec, count: int, fit_gap: float = DEFAULT_FIT_GAP) -> str:
    return (
        f"{count} varillas de ⌀{printed_diameter(spec, fit_gap):.2f} × "
        f"{dowel_length(spec):.0f} mm (agujero ⌀{spec.hole_diameter:.2f})"
    )
