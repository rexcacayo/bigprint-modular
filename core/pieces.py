"""Piezas resultantes de un corte: cómo se llaman y cómo se comprueban.

El corte en sí es cosa de Blender (bmesh), pero el nombrado y la verificación
son aritmética pura, así que viven aquí y se pueden probar sin Blender.
"""

import re
from dataclasses import dataclass, field
from typing import List, Sequence

PIECE_TOKEN = "pieza"

#: Patrón del sufijo que añade el complemento, para poder quitarlo y no acabar
#: con nombres tipo "soporte_pieza_01_pieza_01" al cortar una pieza otra vez.
_SUFFIX_RE = re.compile(rf"_{PIECE_TOKEN}_\d+$")

#: Tolerancia relativa por defecto al comparar volúmenes (0,5 %).
#: No es cero porque el corte reconstruye la tapa con triángulos nuevos y la
#: aritmética en coma flotante no devuelve exactamente el mismo número.
DEFAULT_VOLUME_TOLERANCE = 0.005


def base_name(name: str) -> str:
    """Quita el sufijo de pieza si ya lo tenía."""
    return _SUFFIX_RE.sub("", name)


def piece_name(base: str, index: int, digits: int = 2) -> str:
    """Nombre de la pieza número `index` (empezando en 1), con ceros a la izquierda."""
    if index < 1:
        raise ValueError("Las piezas se numeran a partir de 1")
    return f"{base_name(base)}_{PIECE_TOKEN}_{index:0{digits}d}"


def piece_names(base: str, count: int, digits: int = 2) -> List[str]:
    if count < 1:
        raise ValueError("Hace falta al menos una pieza")
    return [piece_name(base, i, digits) for i in range(1, count + 1)]


@dataclass
class VolumeCheck:
    """¿Se ha conservado el material al cortar?"""

    source_volume: float
    piece_volumes: List[float] = field(default_factory=list)
    tolerance: float = DEFAULT_VOLUME_TOLERANCE

    @property
    def total(self) -> float:
        return sum(self.piece_volumes)

    @property
    def difference(self) -> float:
        return self.total - self.source_volume

    @property
    def relative_error(self) -> float:
        if self.source_volume <= 0.0:
            return 0.0 if self.total <= 0.0 else 1.0
        return abs(self.difference) / self.source_volume

    @property
    def ok(self) -> bool:
        return self.relative_error <= self.tolerance

    def describe(self) -> str:
        if self.ok:
            return f"Volumen conservado ({self.relative_error * 100:.3f} % de diferencia)"
        return (
            f"Falta o sobra material: {self.total:.2f} frente a {self.source_volume:.2f} "
            f"({self.relative_error * 100:.2f} % de diferencia)"
        )


def check_volumes(
    source_volume: float,
    piece_volumes: Sequence[float],
    tolerance: float = DEFAULT_VOLUME_TOLERANCE,
) -> VolumeCheck:
    """Comprueba que las piezas suman el volumen del original.

    Es la verificación más barata y más reveladora de un corte: si el
    resultado no cuadra, o se ha perdido geometría o alguna tapa ha quedado
    mal cerrada y el volumen calculado ya no significa nada.
    """
    return VolumeCheck(
        source_volume=float(source_volume),
        piece_volumes=[float(v) for v in piece_volumes],
        tolerance=float(tolerance),
    )
