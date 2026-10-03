"""Corte del modelo en dos piezas con `bisect_plane`.

Se usa bisect y no un booleano porque para un plano recto es más directo,
más rápido y no necesita fabricar un sólido cortador.

El original no se toca: cada mitad se construye en un `bmesh` nuevo a partir de
la malla evaluada, y el modelo de partida solo se oculta.
"""

import bmesh
import bpy
from mathutils import Vector

from ..core import cut_plan as core_plan
from ..core import pieces as core_pieces

ORIGINAL_COLLECTION = "BigPrint_Original"
PIECES_COLLECTION = "BigPrint_Piezas"

ROLE_KEY = "bigprint_role"
ROLE_PIECE = "piece"
SOURCE_KEY = "bigprint_source"
PIECE_INDEX_KEY = "bigprint_piece_index"


class CutError(RuntimeError):
    pass


def _fill_open_boundaries(bm, normal=None) -> int:
    """Tapa los agujeros que ha dejado el corte.

    Se buscan las aristas de borde de toda la malla en lugar de fiarse del
    `geom_cut` que devuelve bisect: así se tapan también las secciones que
    quedan en varios trozos (un plano puede atravesar dos brazos de una pieza
    y dejar dos agujeros separados).

    Se usa `triangle_fill` con todos los contornos a la vez porque respeta los
    contornos interiores: si la pieza está vaciada (cascos, bustos rellenos de
    espuma) la tapa queda en anillo y el hueco sigue siendo hueco. `holes_fill`
    tapaba cada contorno por separado y cerraba también el hueco, dejando caras
    solapadas.

    Es seguro porque solo se corta a partir de mallas cerradas: cualquier borde
    que aparezca aquí lo ha creado el corte.
    """
    bordes = [e for e in bm.edges if e.is_boundary]
    if not bordes:
        return 0

    kwargs = {"use_beauty": True, "use_dissolve": False, "edges": bordes}
    if normal is not None:
        kwargs["normal"] = normal
    resultado = bmesh.ops.triangle_fill(bm, **kwargs)
    caras = sum(1 for g in resultado.get("geom", []) if isinstance(g, bmesh.types.BMFace))

    # Plan B para contornos que la triangulación no admita
    restantes = [e for e in bm.edges if e.is_boundary]
    if restantes:
        extra = bmesh.ops.holes_fill(bm, edges=restantes, sides=0)
        caras += len(extra.get("faces", []))

    return caras


def _build_side(source_mesh, matrix_world, plane_co, plane_no, keep_positive: bool, name: str):
    """Construye una de las dos mitades como objeto nuevo.

    `keep_positive` indica si se conserva el lado hacia el que apunta la normal
    del plano.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(source_mesh)
        # Se trabaja en coordenadas de mundo y el objeto nuevo nace con matriz
        # identidad: así las piezas quedan exactamente donde estaba el original
        # aunque este tuviera escala o rotación.
        bm.transform(matrix_world)

        bmesh.ops.bisect_plane(
            bm,
            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            dist=1e-6,
            plane_co=plane_co,
            plane_no=plane_no,
            clear_outer=not keep_positive,
            clear_inner=keep_positive,
        )

        if not bm.faces:
            raise CutError(f"El corte ha dejado vacía la pieza {name}")

        _fill_open_boundaries(bm, Vector(plane_no))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

        malla = bpy.data.meshes.new(name)
        bm.to_mesh(malla)
        malla.update()
    finally:
        bm.free()

    return bpy.data.objects.new(name, malla)


def split_object(context, obj, plane_co, plane_no, hide_source: bool = True, names=None):
    """Parte `obj` por el plano y devuelve los dos objetos nuevos.

    `plane_co` y `plane_no` van en coordenadas de mundo (unidades de Blender).
    `names` permite imponer los nombres (el corte en rejilla los pone al final,
    cuando ya sabe cuántas piezas hay y en qué orden van).
    """
    depsgraph = context.evaluated_depsgraph_get()
    evaluado = obj.evaluated_get(depsgraph)
    temporal = evaluado.to_mesh()
    if temporal is None:
        raise CutError("No se ha podido evaluar la malla del modelo")

    if names is None:
        names = core_pieces.piece_names(core_pieces.base_name(obj.name), 2)
    nombres = list(names)

    try:
        matriz = obj.matrix_world.copy()
        # keep_positive=False es el lado bajo del eje (contra la normal)
        pieza_baja = _build_side(temporal, matriz, plane_co, plane_no, False, nombres[0])
        pieza_alta = _build_side(temporal, matriz, plane_co, plane_no, True, nombres[1])
    finally:
        evaluado.to_mesh_clear()

    coleccion_piezas = ensure_collection(context, PIECES_COLLECTION)
    for indice, pieza in enumerate((pieza_baja, pieza_alta), start=1):
        pieza[ROLE_KEY] = ROLE_PIECE
        pieza[SOURCE_KEY] = obj.name
        pieza[PIECE_INDEX_KEY] = indice
        coleccion_piezas.objects.link(pieza)

    if hide_source:
        move_to_collection(context, obj, ORIGINAL_COLLECTION)
        # Ocultar, nunca borrar: el original es la referencia si hay que repetir
        obj.hide_set(True)
        obj.hide_render = True

    return pieza_baja, pieza_alta


def ensure_collection(context, nombre):
    """Colección propia colgando de la escena, creada la primera vez."""
    coleccion = bpy.data.collections.get(nombre)
    if coleccion is None:
        coleccion = bpy.data.collections.new(nombre)
    if nombre not in context.scene.collection.children:
        context.scene.collection.children.link(coleccion)
    return coleccion


def move_to_collection(context, obj, nombre):
    """Saca el objeto de donde esté y lo deja solo en esa colección.

    Separar original y piezas en colecciones distintas permite apagar una de
    las dos desde el esquema, que es la forma natural de mirar solo el despiece
    sin borrar nada.
    """
    coleccion = ensure_collection(context, nombre)
    for actual in list(obj.users_collection):
        actual.objects.unlink(obj)
    coleccion.objects.link(obj)
    return coleccion


def move_to_scene_collection(context, obj):
    """Devuelve el objeto a la colección principal de la escena."""
    destino = context.scene.collection
    for actual in list(obj.users_collection):
        actual.objects.unlink(obj)
    destino.objects.link(obj)


def is_piece(obj) -> bool:
    return obj is not None and obj.get(ROLE_KEY) == ROLE_PIECE


def find_pieces(context, source_name: str):
    return [o for o in context.scene.objects if o.get(SOURCE_KEY) == source_name]


def remove_pieces(context, source_name: str) -> int:
    """Borra las piezas generadas a partir de un modelo y vuelve a mostrarlo."""
    borradas = 0
    for pieza in find_pieces(context, source_name):
        malla = pieza.data
        bpy.data.objects.remove(pieza, do_unlink=True)
        if malla is not None and malla.users == 0:
            bpy.data.meshes.remove(malla)
        borradas += 1

    original = bpy.data.objects.get(source_name)
    if original is not None:
        move_to_scene_collection(context, original)
        try:
            original.hide_set(False)
        except RuntimeError:
            pass  # el objeto puede no estar en la vista activa
        original.hide_render = False

    return borradas


def world_bbox(obj):
    """Caja envolvente del objeto en coordenadas de mundo (unidades de Blender)."""
    esquinas = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in esquinas]
    ys = [c.y for c in esquinas]
    zs = [c.z for c in esquinas]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _discard(obj):
    malla = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if malla is not None and malla.users == 0:
        bpy.data.meshes.remove(malla)


def split_grid(context, obj, plan, factor: float = 1.0):
    """Aplica un plan de corte completo y devuelve las piezas finales, numeradas.

    Los cortes se aplican uno a uno sobre las piezas que cada plano atraviesa;
    las que quedan enteras a un lado se dejan en paz. Los objetos intermedios se
    borran: solo sobreviven el original (oculto) y las piezas finales.
    """
    origen_nombre = obj.name
    base = core_pieces.base_name(origen_nombre)
    actuales = [obj]
    contador = 0

    for corte in plan.cuts:
        posicion = corte.position / factor  # de mm a unidades de Blender
        spec = core_plan.CutSpec(axis=corte.axis, position=posicion)
        siguientes = []

        for pieza in actuales:
            caja_min, caja_max = world_bbox(pieza)
            if not core_plan.crosses(caja_min, caja_max, spec):
                siguientes.append(pieza)
                continue

            origen = [0.0, 0.0, 0.0]
            origen[corte.axis] = posicion
            normal = [0.0, 0.0, 0.0]
            normal[corte.axis] = 1.0

            contador += 2
            temporales = (f"{base}_tmp_{contador - 1}", f"{base}_tmp_{contador}")
            nuevas = split_object(
                context,
                pieza,
                tuple(origen),
                tuple(normal),
                hide_source=False,
                names=temporales,
            )
            siguientes.extend(nuevas)

            if pieza.name == origen_nombre:
                pieza.hide_set(True)
                pieza.hide_render = True
                move_to_collection(context, pieza, ORIGINAL_COLLECTION)
            else:
                _discard(pieza)

        actuales = siguientes

    if len(actuales) == 1 and actuales[0].name == origen_nombre:
        return []  # no había nada que cortar

    for pieza in actuales:
        move_to_collection(context, pieza, PIECES_COLLECTION)

    # Numeración por capas: primero abajo, luego fondo, luego ancho
    actuales.sort(key=lambda o: core_plan.sort_key(world_bbox(o)[0]))
    finales = core_pieces.piece_names(base, len(actuales))

    # Dos pasadas: si un nombre destino ya lo lleva otro objeto, Blender le
    # añadiría un .001 y la numeración quedaría desordenada.
    for indice, pieza in enumerate(actuales):
        pieza.name = f"{base}_renombrando_{indice}"
    for indice, (pieza, nombre) in enumerate(zip(actuales, finales), start=1):
        pieza.name = nombre
        if pieza.data is not None:
            pieza.data.name = nombre
        pieza[ROLE_KEY] = ROLE_PIECE
        pieza[SOURCE_KEY] = origen_nombre
        pieza[PIECE_INDEX_KEY] = indice

    return actuales


def _solvers():
    try:
        return set(bpy.types.BooleanModifier.bl_rna.properties["solver"].enum_items.keys())
    except (AttributeError, KeyError):
        return set()


def apply_holes(context, piezas, cortador):
    """Resta el objeto cortador a cada pieza.

    Se aplica sin `bpy.ops` (no depende del objeto activo ni del modo): se
    evalúa el modificador y la malla resultante sustituye a la de la pieza. Así
    las piezas quedan como mallas autónomas, listas para exportar, y no
    dependen de que el cortador siga existiendo. Se prueba primero el
    solucionador «Manifold» (mucho más rápido, Blender 4.5+) y, si no existe o
    no da un sólido cerrado, el «Exacto». El modelo original sigue intacto, que
    es la red de seguridad.
    """
    disponibles = _solvers()
    orden = [s for s in ("MANIFOLD", "EXACT") if s in disponibles] or [None]
    perforadas = []
    for pieza in piezas:
        ultimo_error = None
        for solver in orden:
            modificador = pieza.modifiers.new("BigPrint_Conectores", "BOOLEAN")
            modificador.operation = "DIFFERENCE"
            modificador.object = cortador
            if solver:
                modificador.solver = solver
            try:
                context.view_layer.update()
                grafo = context.evaluated_depsgraph_get()
                nueva = bpy.data.meshes.new_from_object(
                    pieza.evaluated_get(grafo), preserve_all_data_layers=True, depsgraph=grafo
                )
            except RuntimeError as exc:
                ultimo_error = exc
                continue
            finally:
                pieza.modifiers.remove(modificador)
            if _cerrada(nueva):
                vieja = pieza.data
                pieza.data = nueva
                nueva.name = vieja.name
                if vieja.users == 0:
                    bpy.data.meshes.remove(vieja)
                break
            bpy.data.meshes.remove(nueva)
            ultimo_error = f"el solucionador {solver} no dio un sólido cerrado"
        else:
            raise CutError(f"No se ha podido perforar {pieza.name}: {ultimo_error}")
        perforadas.append(pieza)
    return perforadas


def _cerrada(malla) -> bool:
    bm = bmesh.new()
    try:
        bm.from_mesh(malla)
        return bool(bm.faces) and all(e.is_manifold for e in bm.edges)
    finally:
        bm.free()
