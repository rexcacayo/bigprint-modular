"""Plano de corte: dónde ponerlo y qué saldría de él.

Fase 2a: aquí no se corta nada. Solo se calcula la posición del plano, la
transformación del objeto guía que lo representa en la escena y una
previsualización de las dos mitades a partir de la caja envolvente.

Todo en las mismas unidades que la caja que se le pase (el complemento usa mm).
"""

from dataclasses import dataclass
from typing import Sequence, Tuple

from .geometry import Vec3
from .printer_profiles import PrinterProfile, check_fit

AXES = ("X", "Y", "Z")

#: Margen relativo con el que el plano guía sobresale del modelo, para que se
#: vea que atraviesa la pieza entera y no quede escondido dentro.
DEFAULT_OVERSHOOT = 1.2

#: Distancia mínima al borde: un corte pegado a la cara no produce dos piezas.
MIN_MARGIN = 0.001


def axis_index(axis) -> int:
    """Acepta el índice o el nombre del eje y devuelve el índice."""
    if isinstance(axis, int):
        if axis not in (0, 1, 2):
            raise ValueError(f"Eje fuera de rango: {axis}")
        return axis
    try:
        return AXES.index(str(axis).upper())
    except ValueError:
        raise ValueError(f"Eje desconocido: {axis!r}")


def axis_name(axis) -> str:
    return AXES[axis_index(axis)]


def suggest_axis(dimensions: Sequence[float], profile: PrinterProfile) -> int:
    """Eje por el que conviene cortar primero.

    Se elige el que más se pasa del volumen útil, no el más largo: un modelo de
    400 × 100 × 300 con una cama de 236 se pasa 164 en X y 64 en Z, y atacar X
    primero es lo que reduce de verdad el número de piezas. Si cabe entero, se
    devuelve el eje más largo como opción por defecto.
    """
    usable = profile.usable
    desbordes = [max(0.0, d - u) for d, u in zip(dimensions, usable)]
    if max(desbordes) > 0.0:
        return max(range(3), key=lambda i: desbordes[i])
    return max(range(3), key=lambda i: dimensions[i])


def center_position(bbox_min: Sequence[float], bbox_max: Sequence[float], axis) -> float:
    i = axis_index(axis)
    return (bbox_min[i] + bbox_max[i]) * 0.5


def is_valid_position(
    bbox_min: Sequence[float], bbox_max: Sequence[float], axis, position: float
) -> bool:
    """El plano tiene que quedar dentro de la pieza para producir dos mitades."""
    i = axis_index(axis)
    return bbox_min[i] + MIN_MARGIN < position < bbox_max[i] - MIN_MARGIN


def split_bbox(
    bbox_min: Sequence[float], bbox_max: Sequence[float], axis, position: float
) -> Tuple[Tuple[Vec3, Vec3], Tuple[Vec3, Vec3]]:
    """Parte la caja envolvente en dos: la del lado bajo y la del lado alto."""
    i = axis_index(axis)
    if not is_valid_position(bbox_min, bbox_max, axis, position):
        raise ValueError("El plano de corte cae fuera de la pieza")

    bajo_max = list(bbox_max)
    bajo_max[i] = position
    alto_min = list(bbox_min)
    alto_min[i] = position

    return (
        (tuple(bbox_min), tuple(bajo_max)),
        (tuple(alto_min), tuple(bbox_max)),
    )


def _dims(caja: Tuple[Vec3, Vec3]) -> Vec3:
    minimo, maximo = caja
    return (maximo[0] - minimo[0], maximo[1] - minimo[1], maximo[2] - minimo[2])


@dataclass(frozen=True)
class SplitPreview:
    """Qué daría este corte, mirando solo cajas envolventes.

    Es una cota superior: la pieza real puede ser más pequeña que su caja, así
    que si la caja cabe, la pieza cabe seguro. Al revés no siempre.
    """

    axis: int
    position: float
    dims_low: Vec3
    dims_high: Vec3
    fits_low: bool
    fits_high: bool

    @property
    def both_fit(self) -> bool:
        return self.fits_low and self.fits_high

    @property
    def axis_name(self) -> str:
        return AXES[self.axis]


def preview_split(
    bbox_min: Sequence[float],
    bbox_max: Sequence[float],
    axis,
    position: float,
    profile: PrinterProfile,
    allow_rotation: bool = True,
) -> SplitPreview:
    i = axis_index(axis)
    baja, alta = split_bbox(bbox_min, bbox_max, i, position)
    dims_baja, dims_alta = _dims(baja), _dims(alta)
    return SplitPreview(
        axis=i,
        position=position,
        dims_low=dims_baja,
        dims_high=dims_alta,
        fits_low=check_fit(dims_baja, profile, allow_rotation).fits,
        fits_high=check_fit(dims_alta, profile, allow_rotation).fits,
    )


def plane_transform(
    bbox_min: Sequence[float],
    bbox_max: Sequence[float],
    axis,
    position: float,
    overshoot: float = DEFAULT_OVERSHOOT,
) -> Tuple[Vec3, Vec3, Vec3]:
    """Transformación del plano guía: (posición, rotación euler, escala).

    Se parte de un plano unitario en XY (normal +Z) y se orienta con rotaciones
    de 90°, en lugar de reconstruir la malla cada vez que se mueve el deslizador:
    mover un objeto es barato y no toca datos de malla.

    La escala se expresa en semiejes porque el plano unitario va de -1 a 1.
    """
    i = axis_index(axis)
    centro = [
        (bbox_min[0] + bbox_max[0]) * 0.5,
        (bbox_min[1] + bbox_max[1]) * 0.5,
        (bbox_min[2] + bbox_max[2]) * 0.5,
    ]
    centro[i] = position
    tam = [
        (bbox_max[0] - bbox_min[0]) * 0.5 * overshoot,
        (bbox_max[1] - bbox_min[1]) * 0.5 * overshoot,
        (bbox_max[2] - bbox_min[2]) * 0.5 * overshoot,
    ]
    # Un plano degenerado no se ve: se le da un mínimo si la pieza es plana.
    tam = [max(t, MIN_MARGIN) for t in tam]

    media_pi = 1.5707963267948966
    if i == 0:  # normal en X: girar 90° sobre Y (local X -> mundo Z, local Y -> mundo Y)
        rotacion = (0.0, media_pi, 0.0)
        escala = (tam[2], tam[1], 1.0)
    elif i == 1:  # normal en Y: girar 90° sobre X (local X -> mundo X, local Y -> mundo Z)
        rotacion = (media_pi, 0.0, 0.0)
        escala = (tam[0], tam[2], 1.0)
    else:  # normal en Z: el plano ya está orientado
        rotacion = (0.0, 0.0, 0.0)
        escala = (tam[0], tam[1], 1.0)

    return (tuple(centro), rotacion, escala)  # type: ignore[return-value]
