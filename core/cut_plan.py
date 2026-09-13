"""Plan de corte en rejilla: la lista de planos necesarios para que todo quepa.

Los cortes se reparten a distancias iguales dentro de cada eje. Es la opción
predecible: todas las piezas de un mismo eje salen del mismo tamaño, lo que
facilita numerarlas, orientarlas en la cama y montar el puzle después.

Como todo lo del núcleo, aquí no se corta nada: solo se calcula dónde.
"""

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .cut_planes import AXES, axis_index
from .printer_profiles import PrinterProfile, estimate_pieces

#: Tope de seguridad: por encima de esto, seguramente el modelo esté mal
#: escalado o el perfil mal elegido, y cortar sería peor que avisar.
MAX_PIECES = 64


@dataclass(frozen=True)
class CutSpec:
    """Un plano de corte: eje perpendicular y posición a lo largo de ese eje."""

    axis: int
    position: float

    @property
    def axis_name(self) -> str:
        return AXES[self.axis]

    def describe(self) -> str:
        return f"{self.axis_name} = {self.position:.2f} mm"


@dataclass(frozen=True)
class CutPlan:
    cuts: Tuple[CutSpec, ...]
    counts: Tuple[int, int, int]

    @property
    def total_pieces(self) -> int:
        return self.counts[0] * self.counts[1] * self.counts[2]

    @property
    def needs_cutting(self) -> bool:
        return bool(self.cuts)

    def cuts_on(self, axis) -> List[CutSpec]:
        i = axis_index(axis)
        return [c for c in self.cuts if c.axis == i]

    def describe(self) -> str:
        if not self.cuts:
            return "No hace falta cortar: cabe entera"
        partes = []
        for i, nombre in enumerate(AXES):
            n = len(self.cuts_on(i))
            if n:
                partes.append(f"{n} en {nombre}")
        # "hasta": si el modelo no llena toda la rejilla, alguna celda queda vacía
        # y no produce pieza (una L cortada en 2×2 da tres piezas, no cuatro).
        return f"{', '.join(partes)} → hasta {self.total_pieces} piezas"


def plan_grid(
    bbox_min: Sequence[float],
    bbox_max: Sequence[float],
    profile: PrinterProfile,
    allow_rotation: bool = True,
    max_pieces: int = MAX_PIECES,
) -> CutPlan:
    """Calcula los planos necesarios para que cada celda quepa en la impresora.

    El número de divisiones por eje sale de `estimate_pieces`, que ya tiene en
    cuenta que girar la pieza 90° sobre la cama es gratis.
    """
    dims = [float(bbox_max[i] - bbox_min[i]) for i in range(3)]
    if min(dims) < 0.0:
        raise ValueError("Caja envolvente inválida")

    counts = estimate_pieces(dims, profile, allow_rotation=allow_rotation)
    total = counts[0] * counts[1] * counts[2]
    if total > max_pieces:
        raise ValueError(
            f"Harían falta {total} piezas (el tope es {max_pieces}): "
            "revisa la escala del modelo o el perfil de impresora"
        )

    cortes: List[CutSpec] = []
    for eje in range(3):
        n = counts[eje]
        if n < 2:
            continue
        paso = dims[eje] / n
        for k in range(1, n):
            cortes.append(CutSpec(axis=eje, position=bbox_min[eje] + paso * k))

    return CutPlan(cuts=tuple(cortes), counts=counts)


def crosses(
    bbox_min: Sequence[float], bbox_max: Sequence[float], cut: CutSpec, margin: float = 0.001
) -> bool:
    """¿Este plano atraviesa esta caja?

    Se usa para no intentar cortar las piezas que quedan enteras a un lado del
    plano: cortarlas daría una mitad vacía y un error.
    """
    return bbox_min[cut.axis] + margin < cut.position < bbox_max[cut.axis] - margin


def sort_key(bbox_min: Sequence[float]) -> Tuple[float, float, float]:
    """Orden de numeración de las piezas: por altura, luego fondo, luego ancho.

    Numerar por capas es lo que tiene sentido al montar: se empieza por abajo.
    """
    return (round(bbox_min[2], 3), round(bbox_min[1], 3), round(bbox_min[0], 3))
