"""Escritura de STL binario.

Se escribe a mano en lugar de llamar al exportador de Blender por dos razones:
la salida queda siempre en milímetros pase lo que pase con las unidades de la
escena, y no depende de una API de operador que cambia entre versiones.
"""

import math
import struct
from typing import Tuple

from .geometry import MeshData, Vec3

#: Cabecera de 80 bytes + entero de 4 + 50 bytes por triángulo.
HEADER_SIZE = 80
TRIANGLE_SIZE = 50


def _normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    largo = math.sqrt(nx * nx + ny * ny + nz * nz)
    if largo == 0.0:
        return (0.0, 0.0, 0.0)
    return (nx / largo, ny / largo, nz / largo)


def stl_bytes(mesh: MeshData, title: str = "") -> bytes:
    partes = [
        (title or f"BigPrint Modular - {mesh.name}").encode("ascii", "replace")[:80].ljust(80, b" "),
        struct.pack("<I", len(mesh.triangles)),
    ]
    for i, j, k in mesh.triangles:
        a, b, c = mesh.vertices[i], mesh.vertices[j], mesh.vertices[k]
        partes.append(struct.pack("<3f", *_normal(a, b, c)))
        for v in (a, b, c):
            partes.append(struct.pack("<3f", *v))
        partes.append(struct.pack("<H", 0))
    return b"".join(partes)


def write_binary_stl(mesh: MeshData, path: str, title: str = "") -> int:
    """Escribe la malla y devuelve el tamaño del fichero en bytes."""
    datos = stl_bytes(mesh, title)
    with open(path, "wb") as f:
        f.write(datos)
    return len(datos)


def expected_size(triangle_count: int) -> int:
    return HEADER_SIZE + 4 + TRIANGLE_SIZE * triangle_count


def safe_filename(name: str) -> str:
    """Nombre de fichero utilizable en Windows y Linux.

    Blender admite caracteres en los nombres de objeto que el sistema de
    ficheros no, y una exportación que falla a mitad es peor que un nombre feo.
    """
    prohibidos = '<>:"/\\|?*'
    limpio = "".join("_" if c in prohibidos else c for c in name).strip()
    limpio = limpio.rstrip(".")
    return limpio or "pieza"
