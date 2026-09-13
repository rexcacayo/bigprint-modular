"""Lógica pura de BigPrint Modular: nada de aquí importa bpy.

Mantener el núcleo libre de Blender permite ejecutar los tests con python
normal y reutilizar la lógica desde otro entorno (CLI, servicio) más adelante.
"""

from . import (  # noqa: F401
    connectors,
    cut_plan,
    cut_planes,
    geometry,
    mesh_analysis,
    mesh_cleanup,
    pieces,
    printer_profiles,
    dowels,
    explode,
    labeling,
    parts_list,
    sections,
    stl_io,
    units,
)
from .geometry import BBox, MeshData, Vec3, mesh_area, mesh_volume  # noqa: F401
from .mesh_analysis import MeshReport, analyze_mesh  # noqa: F401
from .mesh_cleanup import weld_vertices  # noqa: F401
from .printer_profiles import (  # noqa: F401
    BUILTIN_PROFILES,
    CUSTOM_ID,
    DEFAULT_PROFILE_ID,
    FitResult,
    PrinterProfile,
    check_fit,
    estimate_pieces,
    get_profile,
    list_profiles,
    make_custom_profile,
    profile_enum_items,
    scale_to_fit,
)
from .units import AUTO, guess_unit, resolve_unit, unit_factor  # noqa: F401

__all__ = [
    "connectors",
    "cut_plan",
    "cut_planes",
    "geometry",
    "mesh_analysis",
    "mesh_cleanup",
    "pieces",
    "printer_profiles",
    "dowels",
    "explode",
    "labeling",
    "parts_list",
    "sections",
    "stl_io",
    "units",
    "BBox",
    "MeshData",
    "Vec3",
    "mesh_area",
    "mesh_volume",
    "MeshReport",
    "analyze_mesh",
    "weld_vertices",
    "BUILTIN_PROFILES",
    "CUSTOM_ID",
    "DEFAULT_PROFILE_ID",
    "FitResult",
    "PrinterProfile",
    "check_fit",
    "estimate_pieces",
    "get_profile",
    "list_profiles",
    "make_custom_profile",
    "profile_enum_items",
    "scale_to_fit",
    "AUTO",
    "guess_unit",
    "resolve_unit",
    "unit_factor",
]
