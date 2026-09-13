"""Dónde grabar el número de pieza.

El número va hundido en la cara inferior: es la que apoya en la cama, no se ve
una vez montado y siempre es plana por definición del laminado. Grabarlo en la
cara de corte sería más cómodo de encontrar, pero estropearía la junta.

El problema es el mismo que con los conectores: encontrar un sitio con
material suficiente alrededor. Aquí lo que tiene que caber es el rectángulo
del texto, no un círculo.
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from .connectors import Section, Vec2

#: Proporción ancho/alto de un dígito con la tipografía por defecto de Blender.
DIGIT_ASPECT = 0.62

#: Tamaño mínimo por debajo del cual el número no se lee una vez impreso.
MIN_TEXT_HEIGHT = 4.0


def label_text(index: int, digits: int = 2) -> str:
    if index < 1:
        raise ValueError("Las piezas se numeran a partir de 1")
    return f"{index:0{digits}d}"


def text_box(text: str, height: float) -> Tuple[float, float]:
    """Ancho y alto aproximados del texto, en las mismas unidades que `height`."""
    return (len(text) * height * DIGIT_ASPECT, height)


@dataclass(frozen=True)
class LabelSpot:
    """Dónde y de qué tamaño va el número."""

    point: Vec2
    height: float
    clearance: float

    @property
    def ok(self) -> bool:
        return self.height >= MIN_TEXT_HEIGHT


def best_spot(
    section: Section,
    text: str,
    desired_height: float = 10.0,
    margin: float = 1.0,
    step: Optional[float] = None,
) -> Optional[LabelSpot]:
    """Busca el punto más metido en el material y ajusta el tamaño a lo que cabe.

    Se reduce el texto si hace falta en lugar de renunciar a grabarlo: un número
    pequeño se lee, y uno que se sale de la pieza no se imprime.
    """
    if section.is_empty:
        return None

    (min_u, min_v), (max_u, max_v) = section.bounds()
    if step is None:
        step = max(0.5, min(max_u - min_u, max_v - min_v) / 30.0)

    mejor_punto = None
    mejor_holgura = 0.0
    u = min_u
    while u <= max_u:
        v = min_v
        while v <= max_v:
            holgura = section.clearance_at((u, v))
            if holgura > mejor_holgura:
                mejor_holgura = holgura
                mejor_punto = (u, v)
            v += step
        u += step

    if mejor_punto is None:
        return None

    ancho, alto = text_box(text, desired_height)
    # El texto cabe si su media diagonal entra en el material disponible
    media_diagonal = math.hypot(ancho, alto) * 0.5 + margin
    if media_diagonal <= mejor_holgura:
        altura = desired_height
    else:
        factor = (mejor_holgura - margin) / max(media_diagonal - margin, 1e-9)
        altura = max(0.0, desired_height * factor)

    return LabelSpot(point=mejor_punto, height=altura, clearance=mejor_holgura)
