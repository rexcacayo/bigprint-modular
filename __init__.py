"""BigPrint Modular — imprimir modelos grandes en impresoras pequeñas.

Fase 1: perfiles de impresora, selección/importación del modelo, medidas y
análisis de la malla. El corte, los conectores y la exportación llegan después.

Estructura: `core/` es Python puro (testeable sin Blender) y `blender/` es la
única parte que importa bpy.
"""

bl_info = {
    "name": "BigPrint Modular",
    "author": "Ricardo Lugaresi",
    "version": (0, 11, 1),
    "blender": (3, 6, 0),
    "location": "Vista 3D > Barra lateral (N) > BigPrint",
    "description": "Prepara modelos grandes para imprimirlos por piezas (Fase 1: análisis)",
    "warning": "Versión de desarrollo: solo análisis, todavía no corta el modelo",
    "category": "Mesh",
}

import importlib
import sys

# Recarga en caliente: importlib.reload reejecuta este módulo sobre el mismo
# diccionario, así que la presencia de _RELOADABLE indica que ya se cargó antes.
_RELOADABLE = (
    "core.geometry",
    "core.units",
    "core.printer_profiles",
    "core.mesh_cleanup",
    "core.mesh_analysis",
    "core.cut_planes",
    "core.pieces",
    "core.cut_plan",
    "core.connectors",
    "core.sections",
    "core.stl_io",
    "core.parts_list",
    "core.labeling",
    "core.dowels",
    "core.explode",
    "core.sample_shapes",
    "core",
    "blender.mesh_bridge",
    "blender.cut_plane_object",
    "blender.cutting",
    "blender.connector_objects",
    "blender.exporting",
    "blender.labeling",
    "blender.explode",
    "blender.example_model",
    "blender.properties",
    "blender.operators",
    "blender.panels",
    "blender",
)

if "_ALREADY_LOADED" in locals():
    for _name in _RELOADABLE:
        _mod = sys.modules.get(f"{__name__}.{_name}")
        if _mod is not None:
            importlib.reload(_mod)

_ALREADY_LOADED = True

from . import blender as blender_layer  # noqa: E402
from . import core  # noqa: E402,F401


def register():
    blender_layer.register()


def unregister():
    blender_layer.unregister()


if __name__ == "__main__":
    register()
