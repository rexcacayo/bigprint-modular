"""Perfiles de impresora y cálculo de encaje del modelo en el volumen útil.

El margen se resta a cada lado de cada eje: es la distancia de seguridad al
borde de la cama y al techo, para no depender de que la pieza quede
perfectamente centrada ni de la precisión del origen de la máquina.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import permutations
from typing import Dict, List, Optional, Sequence, Tuple

from .geometry import Vec3

CUSTOM_ID = "CUSTOM"


@dataclass(frozen=True)
class PrinterProfile:
    """Volumen de impresión de una máquina, en milímetros."""

    id: str
    name: str
    size_x: float
    size_y: float
    size_z: float
    margin: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        for axis, value in (("X", self.size_x), ("Y", self.size_y), ("Z", self.size_z)):
            if value <= 0.0:
                raise ValueError(f"El tamaño en {axis} debe ser mayor que cero (recibido {value})")
        if self.margin < 0.0:
            raise ValueError("El margen no puede ser negativo")
        if self.margin * 2.0 >= min(self.size_x, self.size_y, self.size_z):
            raise ValueError(
                "El margen se come todo el volumen: debe ser menor que la mitad del eje más corto"
            )

    @property
    def size(self) -> Vec3:
        return (self.size_x, self.size_y, self.size_z)

    @property
    def usable(self) -> Vec3:
        """Volumen realmente utilizable tras descontar el margen a ambos lados."""
        m2 = self.margin * 2.0
        return (self.size_x - m2, self.size_y - m2, self.size_z - m2)

    @property
    def usable_volume_mm3(self) -> float:
        ux, uy, uz = self.usable
        return ux * uy * uz

    @property
    def label(self) -> str:
        return f"{self.name} ({self.size_x:g}×{self.size_y:g}×{self.size_z:g} mm)"


BUILTIN_PROFILES: Tuple[PrinterProfile, ...] = (
    PrinterProfile(
        id="GENERIC_256",
        name="Genérica 256",
        size_x=256.0,
        size_y=256.0,
        size_z=256.0,
        margin=10.0,
        notes="Perfil de referencia del proyecto (clase Bambu P1S / X1C).",
    ),
    PrinterProfile(
        id="FLASHFORGE_AD5M_PRO",
        name="Flashforge Adventurer 5M Pro",
        size_x=220.0,
        size_y=220.0,
        size_z=220.0,
        margin=10.0,
        notes="Boquilla 0,4 mm; laminado en Orca Slicer.",
    ),
    PrinterProfile(
        id="ENDER_3",
        name="Creality Ender 3 / V2",
        size_x=220.0,
        size_y=220.0,
        size_z=250.0,
        margin=10.0,
    ),
    PrinterProfile(
        id="PRUSA_MK4",
        name="Prusa MK4",
        size_x=250.0,
        size_y=210.0,
        size_z=220.0,
        margin=10.0,
    ),
    PrinterProfile(
        id="BAMBU_A1_MINI",
        name="Bambu Lab A1 mini",
        size_x=180.0,
        size_y=180.0,
        size_z=180.0,
        margin=5.0,
    ),
)

DEFAULT_PROFILE_ID = "GENERIC_256"

_BY_ID: Dict[str, PrinterProfile] = {p.id: p for p in BUILTIN_PROFILES}


def list_profiles() -> Tuple[PrinterProfile, ...]:
    return BUILTIN_PROFILES


def get_profile(profile_id: str) -> PrinterProfile:
    try:
        return _BY_ID[profile_id]
    except KeyError:
        raise KeyError(f"Perfil de impresora desconocido: {profile_id!r}")


def make_custom_profile(
    size_x: float, size_y: float, size_z: float, margin: float = 0.0, name: str = "Personalizada"
) -> PrinterProfile:
    return PrinterProfile(
        id=CUSTOM_ID, name=name, size_x=size_x, size_y=size_y, size_z=size_z, margin=margin
    )


@dataclass(frozen=True)
class FitResult:
    """Resultado de comprobar si una pieza entera cabe en el volumen útil."""

    fits: bool
    usable: Vec3
    dimensions: Vec3
    orientation: Optional[Tuple[int, int, int]]
    overflow: Vec3
    pieces: Tuple[int, int, int]

    @property
    def total_pieces(self) -> int:
        return self.pieces[0] * self.pieces[1] * self.pieces[2]

    @property
    def max_overflow(self) -> float:
        return max(self.overflow)


def _fits_oriented(dims: Sequence[float], usable: Sequence[float], tolerance: float) -> bool:
    return all(d <= u + tolerance for d, u in zip(dims, usable))


def check_fit(
    dimensions_mm: Sequence[float],
    profile: PrinterProfile,
    allow_rotation: bool = True,
    tolerance: float = 1e-6,
) -> FitResult:
    """Comprueba si el modelo cabe entero y, si no, cuántas piezas harían falta.

    Se prueban las seis permutaciones de ejes porque girar la pieza 90° sobre la
    cama es gratis y a menudo es la diferencia entre partir o no partir.
    El recuento de piezas es una estimación de rejilla para la Fase 1: sirve
    para dimensionar el trabajo, no es todavía el plan de corte real.
    """
    dims = (float(dimensions_mm[0]), float(dimensions_mm[1]), float(dimensions_mm[2]))
    usable = profile.usable

    orientations = list(permutations(range(3))) if allow_rotation else [(0, 1, 2)]
    best_orientation: Optional[Tuple[int, int, int]] = None
    for order in orientations:
        oriented = (dims[order[0]], dims[order[1]], dims[order[2]])
        if _fits_oriented(oriented, usable, tolerance):
            best_orientation = order
            break

    fits = best_orientation is not None
    overflow = tuple(max(0.0, d - u) for d, u in zip(dims, usable))  # type: ignore[assignment]
    pieces = estimate_pieces(dims, profile, allow_rotation=allow_rotation)

    return FitResult(
        fits=fits,
        usable=usable,
        dimensions=dims,
        orientation=best_orientation,
        overflow=overflow,  # type: ignore[arg-type]
        pieces=pieces,
    )


def estimate_pieces(
    dimensions_mm: Sequence[float], profile: PrinterProfile, allow_rotation: bool = True
) -> Tuple[int, int, int]:
    """Estimación de cortes en rejilla: divisiones mínimas por eje.

    Con rotación se elige la asignación de ejes del modelo a ejes de la máquina
    que minimiza el número total de piezas.
    """
    dims = [max(float(d), 0.0) for d in dimensions_mm]
    usable = profile.usable

    best: Optional[Tuple[int, int, int]] = None
    best_total = None
    orders = list(permutations(range(3))) if allow_rotation else [(0, 1, 2)]
    for order in orders:
        counts = []
        for slot, axis in enumerate(order):
            d = dims[axis]
            u = usable[slot]
            counts.append(max(1, int(math.ceil(d / u - 1e-9))) if d > 0 else 1)
        total = counts[0] * counts[1] * counts[2]
        if best_total is None or total < best_total:
            best_total = total
            # Se devuelve en el orden de los ejes del modelo, no de la máquina
            result = [1, 1, 1]
            for slot, axis in enumerate(order):
                result[axis] = counts[slot]
            best = (result[0], result[1], result[2])
    assert best is not None
    return best


def scale_to_fit(dimensions_mm: Sequence[float], profile: PrinterProfile) -> float:
    """Factor de escala uniforme que haría caber la pieza entera (informativo)."""
    usable = profile.usable
    ratios = []
    for order in permutations(range(3)):
        oriented = [dimensions_mm[order[i]] for i in range(3)]
        r = min((u / d) if d > 0 else float("inf") for d, u in zip(oriented, usable))
        ratios.append(r)
    return min(1.0, max(ratios))


def profile_enum_items() -> List[Tuple[str, str, str]]:
    """Items para el EnumProperty de Blender, con la opción personalizada."""
    items = [(p.id, p.label, p.notes or p.name) for p in BUILTIN_PROFILES]
    items.append((CUSTOM_ID, "Personalizada", "Definir a mano el volumen de impresión"))
    return items
