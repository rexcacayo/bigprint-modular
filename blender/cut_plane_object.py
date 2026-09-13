"""Objeto guía que representa el plano de corte en la escena.

Es un simple plano en modo alambre, controlado desde el panel. Se mueve
cambiando posición, rotación y escala de un plano unitario en vez de
reconstruir su malla: mover un objeto es barato y no toca datos de malla, así
que el deslizador puede actualizarlo en vivo.

El plano es un ayudante, no parte del modelo: se marca con una propiedad
personalizada para poder reconocerlo (y, en la Fase 2b, no confundirlo con una
pieza).
"""

import bpy

from ..core import cut_planes as cp

PLANE_NAME = "BigPrint_Plano_Corte"
MESH_NAME = "BigPrint_Plano_Corte_malla"
ROLE_KEY = "bigprint_role"
ROLE_CUT_PLANE = "cut_plane"


def _unit_plane_mesh():
    """Malla de un cuadrado unitario en XY, de -1 a 1, reutilizada entre planos."""
    mesh = bpy.data.meshes.get(MESH_NAME)
    if mesh is not None and len(mesh.vertices) == 4:
        return mesh
    mesh = bpy.data.meshes.new(MESH_NAME)
    mesh.from_pydata(
        [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    return mesh


def get_plane(context):
    settings = context.scene.bigprint
    obj = settings.cut_plane
    # El puntero puede quedar colgando si el usuario borra el objeto a mano
    if obj is not None and obj.name not in bpy.data.objects:
        settings.cut_plane = None
        return None
    return obj


def ensure_plane(context):
    """Crea el plano guía si no existe y lo deja colocado."""
    settings = context.scene.bigprint
    obj = get_plane(context)

    if obj is None:
        obj = bpy.data.objects.new(PLANE_NAME, _unit_plane_mesh())
        obj[ROLE_KEY] = ROLE_CUT_PLANE
        obj.display_type = "WIRE"
        obj.show_in_front = True
        obj.hide_render = True
        # Bloqueado a propósito: el plano lo manda el panel. Si se pudiera
        # arrastrar, el deslizador y el objeto acabarían diciendo cosas distintas.
        obj.lock_location = (True, True, True)
        obj.lock_rotation = (True, True, True)
        obj.lock_scale = (True, True, True)
        settings.cut_plane = obj

    if obj.name not in context.collection.objects:
        context.collection.objects.link(obj)

    update_plane(context)
    return obj


def update_plane(context) -> bool:
    """Recoloca el plano según los ajustes. Devuelve False si aún no hay datos."""
    settings = context.scene.bigprint
    datos = settings.analysis
    obj = get_plane(context)
    if obj is None or not datos.has_data:
        return False

    factor = datos.unit_factor or 1.0
    caja_min = (datos.bbox_min_x, datos.bbox_min_y, datos.bbox_min_z)
    caja_max = (datos.bbox_max_x, datos.bbox_max_y, datos.bbox_max_z)

    loc, rot, esc = cp.plane_transform(
        caja_min, caja_max, settings.cut_axis, settings.cut_position
    )

    # La caché del análisis está en mm y la escena en unidades de Blender
    obj.location = tuple(v / factor for v in loc)
    obj.rotation_euler = rot
    obj.scale = tuple(max(v / factor, 1e-6) for v in esc)
    return True


def remove_plane(context) -> bool:
    settings = context.scene.bigprint
    obj = get_plane(context)
    if obj is None:
        return False
    malla = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if malla is not None and malla.users == 0:
        bpy.data.meshes.remove(malla)
    settings.cut_plane = None
    return True


def is_cut_plane(obj) -> bool:
    return obj is not None and obj.get(ROLE_KEY) == ROLE_CUT_PLANE
