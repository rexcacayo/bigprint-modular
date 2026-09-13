"""Interpretación de unidades del modelo.

Blender no guarda en qué unidad se modeló un STL: un cubo de 200 mm puede
llegar como 200 unidades (STL exportado en mm) o como 0.2 (modelado en metros).
Todo el resto del complemento trabaja en milímetros, así que este módulo
concentra la conversión y la heurística de detección.
"""

from __future__ import annotations

from typing import Dict, Sequence, Tuple

MILLIMETERS = "MM"
CENTIMETERS = "CM"
METERS = "M"
INCHES = "IN"
SCENE = "SCENE"
AUTO = "AUTO"

#: Factor para pasar de unidad de Blender a milímetro.
UNIT_TO_MM: Dict[str, float] = {
    MILLIMETERS: 1.0,
    CENTIMETERS: 10.0,
    METERS: 1000.0,
    INCHES: 25.4,
}

UNIT_LABELS: Dict[str, str] = {
    MILLIMETERS: "Milímetros",
    CENTIMETERS: "Centímetros",
    METERS: "Metros",
    INCHES: "Pulgadas",
    SCENE: "Escala de la escena",
    AUTO: "Automático",
}


def unit_factor(unit: str, scene_scale_length: float = 1.0) -> float:
    """Devuelve el factor unidad-de-Blender -> milímetro.

    `scene_scale_length` es `scene.unit_settings.scale_length` (metros por
    unidad de Blender) y solo se usa en modo SCENE.
    """
    if unit == SCENE:
        return float(scene_scale_length) * 1000.0
    try:
        return UNIT_TO_MM[unit]
    except KeyError:
        raise ValueError(f"Unidad desconocida: {unit!r}")


def guess_unit(max_dimension: float) -> str:
    """Adivina la unidad a partir de la dimensión mayor en unidades de Blender.

    Se asume que el modelo es una pieza imprimible (del orden de 10 a 1000 mm),
    que es el caso de uso del complemento. Es una heurística: la interfaz
    siempre muestra el resultado para que se pueda corregir a mano.
    """
    d = abs(float(max_dimension))
    if d <= 0.0:
        return MILLIMETERS
    if d >= 20.0:
        # 20..2000 unidades -> casi siempre un STL en mm
        return MILLIMETERS
    if d >= 2.0:
        # 2..20 unidades -> pieza modelada en cm (o en pulgadas, menos probable)
        return CENTIMETERS
    # < 2 unidades -> modelado en metros, el defecto de Blender
    return METERS


def resolve_unit(unit: str, max_dimension: float, scene_scale_length: float = 1.0) -> Tuple[str, float]:
    """Resuelve AUTO a una unidad concreta y devuelve (unidad, factor a mm)."""
    resolved = guess_unit(max_dimension) if unit == AUTO else unit
    return resolved, unit_factor(resolved, scene_scale_length)


def to_mm(values: Sequence[float], factor: float) -> Tuple[float, ...]:
    return tuple(v * factor for v in values)


def format_mm(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f} mm"
