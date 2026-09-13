"""Único punto donde se leen datos de Blender para alimentar el núcleo.

Regla del proyecto: el modelo original NUNCA se modifica. Por eso aquí se
trabaja siempre sobre una malla temporal evaluada (`to_mesh`) y sobre una copia
en bmesh; nunca se hace `bm.to_mesh(obj.data)`.
"""

import bmesh
import bpy

from ..core.geometry import MeshData


class MeshBridgeError(RuntimeError):
    pass


def is_mesh_object(obj) -> bool:
    return obj is not None and getattr(obj, "type", None) == "MESH"


def mesh_data_from_object(obj, depsgraph=None, apply_modifiers: bool = True) -> MeshData:
    """Extrae una copia triangulada en coordenadas de mundo del objeto.

    Se aplica `matrix_world` para que las dimensiones medidas coincidan con las
    que muestra Blender en el panel N (incluida la escala del objeto).
    """
    if not is_mesh_object(obj):
        raise MeshBridgeError("El objeto seleccionado no es una malla")

    if depsgraph is None:
        depsgraph = bpy.context.evaluated_depsgraph_get()

    source = obj.evaluated_get(depsgraph) if apply_modifiers else obj
    temp_mesh = source.to_mesh()
    if temp_mesh is None:
        raise MeshBridgeError("No se ha podido evaluar la malla del objeto")

    bm = bmesh.new()
    try:
        bm.from_mesh(temp_mesh)

        source_vertex_count = len(bm.verts)
        source_edge_count = len(bm.edges)
        source_polygon_count = len(bm.faces)

        # Triangular la copia (no el original) simplifica el cálculo de volumen
        # y el recuento de aristas; los recuentos originales ya están guardados.
        bmesh.ops.triangulate(bm, faces=bm.faces[:])

        matrix = obj.matrix_world
        bm.verts.ensure_lookup_table()
        vertices = []
        for v in bm.verts:
            co = matrix @ v.co
            vertices.append((co.x, co.y, co.z))

        triangles = [tuple(loop.vert.index for loop in face.loops) for face in bm.faces]

        return MeshData(
            vertices=vertices,
            triangles=triangles,  # type: ignore[arg-type]
            source_vertex_count=source_vertex_count,
            source_edge_count=source_edge_count,
            source_polygon_count=source_polygon_count,
            name=obj.name,
        )
    finally:
        bm.free()
        # Libera la malla temporal creada por to_mesh(); si no, se acumula.
        source.to_mesh_clear()


def object_dimensions(obj) -> tuple:
    """Dimensiones en unidades de Blender tal y como las ve el usuario."""
    d = obj.dimensions
    return (d.x, d.y, d.z)
