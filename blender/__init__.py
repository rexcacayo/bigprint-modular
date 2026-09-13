"""Capa de integración con Blender: propiedades, operadores y paneles.

El orden de registro importa: las propiedades deben existir antes de que los
paneles intenten pintarlas y antes de que los operadores las lean.
"""

from . import operators, panels, properties

MODULES = (properties, operators, panels)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
