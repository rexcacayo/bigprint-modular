"""Aplicación de la vista explotada a las piezas de la escena.

La posición de montaje se guarda en cada pieza la primera vez que se explota,
y es a la que se vuelve al cerrar. Así el deslizador es reversible siempre, y
no depende de deshacer ni de recordar de dónde venía cada una.
"""

import bpy

from ..core import explode as core_explode
from . import cutting

BASE_KEY = "bigprint_base_location"


def _remember_base(pieza):
    if BASE_KEY not in pieza:
        pieza[BASE_KEY] = tuple(pieza.location)
    return tuple(pieza[BASE_KEY])


def apply_explode(context, factor: float) -> int:
    """Coloca las piezas según el factor. Devuelve cuántas se han movido."""
    settings = context.scene.bigprint
    piezas = cutting.find_pieces(context, settings.cut_result.source_name)
    if not piezas:
        return 0

    piezas = sorted(piezas, key=lambda o: o.get("bigprint_piece_index", 0))
    bases = [_remember_base(p) for p in piezas]

    # matrix_world no se recalcula al asignar location: sin esto, las cajas se
    # leerían en la posición anterior y las direcciones del despiece saldrían
    # torcidas al mover el deslizador dos veces seguidas.
    context.view_layer.update()

    # El centro se calcula sobre la geometría en posición de montaje, no sobre
    # el origen del objeto: las piezas nacen con origen en (0,0,0).
    centros = []
    for pieza, base in zip(piezas, bases):
        caja_min, caja_max = cutting.world_bbox(pieza)
        desplazado = tuple(pieza.location[i] - base[i] for i in range(3))
        centros.append(
            tuple(
                (caja_min[i] + caja_max[i]) * 0.5 - desplazado[i] for i in range(3)
            )
        )

    offsets = core_explode.explode_offsets(centros, factor)
    for pieza, base, offset in zip(piezas, bases, offsets):
        pieza.location = (
            base[0] + offset[0],
            base[1] + offset[1],
            base[2] + offset[2],
        )
    return len(piezas)


def reset(context) -> int:
    return apply_explode(context, 0.0)
