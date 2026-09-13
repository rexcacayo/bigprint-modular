"""Creación del objeto de ejemplo dentro de Blender.

La geometría se genera en el núcleo (core.sample_shapes) y aquí solo se vuelca
a una malla de Blender: así el mismo sólido sirve para el ejemplo, el STL de
muestra y los tests.
"""

import bpy

from ..core.sample_shapes import l_bracket


def build_example_object(context=None, name: str = "BigPrint_Ejemplo_Escuadra"):
    """Crea (o recrea) la escuadra de ejemplo de 420 × 180 × 260 mm.

    Se construye en unidades de Blender = milímetros, que es como llega un STL
    normal; el ajuste de unidad del panel se pone en MM al cargarla.
    """
    context = context or bpy.context
    data = l_bracket(name=name)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([list(v) for v in data.vertices], [], [list(t) for t in data.triangles])
    mesh.update()
    mesh.validate()

    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)

    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj
