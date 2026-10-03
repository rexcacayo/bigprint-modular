"""Objeto con los cilindros de los conectores.

Primero solo se muestran, para ver dónde caerían los agujeros antes de tocar
las piezas; al perforar, estos mismos cilindros son los cortadores del
booleano, así que lo que se ve es exactamente lo que se hará.
"""

import bpy

from ..core import connectors as cn

PREVIEW_NAME = "BigPrint_Conectores"
ROLE_KEY = "bigprint_role"
ROLE_CONNECTORS = "connectors"


def get_preview(context):
    obj = context.scene.bigprint.connector_preview
    if obj is not None and obj.name not in bpy.data.objects:
        context.scene.bigprint.connector_preview = None
        return None
    return obj


def remove_preview(context) -> bool:
    obj = get_preview(context)
    if obj is None:
        return False
    malla = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if malla is not None and malla.users == 0:
        bpy.data.meshes.remove(malla)
    context.scene.bigprint.connector_preview = None
    return True


def build_preview(context, grupos, factor: float = 1.0):
    """Crea el objeto de vista previa.

    `grupos` es una lista de (plano_mm, puntos_2d_mm, spec). Todo llega
    en milímetros y aquí se pasa a unidades de Blender, que es el único sitio
    donde hace falta saberlo.
    """
    remove_preview(context)

    vertices = []
    triangulos = []
    for plano, puntos, spec in grupos:
        if not puntos:
            continue
        v, t = cn.cutter_cylinders_plane(puntos, plano, spec)
        desplazamiento = len(vertices)
        vertices.extend([(x / factor, y / factor, z / factor) for x, y, z in v])
        triangulos.extend(
            [(a + desplazamiento, b + desplazamiento, c + desplazamiento) for a, b, c in t]
        )

    if not vertices:
        return None

    malla = bpy.data.meshes.new(PREVIEW_NAME)
    malla.from_pydata([list(v) for v in vertices], [], [list(t) for t in triangulos])
    malla.update()

    obj = bpy.data.objects.new(PREVIEW_NAME, malla)
    obj[ROLE_KEY] = ROLE_CONNECTORS
    obj.show_in_front = True
    obj.hide_render = True
    # Bloqueado: su sitio lo decide el cálculo, no el ratón
    obj.lock_location = (True, True, True)
    obj.lock_rotation = (True, True, True)
    obj.lock_scale = (True, True, True)

    context.collection.objects.link(obj)
    context.scene.bigprint.connector_preview = obj
    return obj
