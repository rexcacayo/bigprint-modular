"""Grabado del número de pieza en la cara inferior.

Se usa la tipografía de Blender convertida a malla, no una geometría propia:
así los dígitos salen legibles y con las curvas bien resueltas.

El número va hundido (resta booleana), no en relieve: un relieve en la cara que
apoya en la cama arruina la primera capa, y un hueco de medio milímetro se lee
igual de bien y no molesta al imprimir.
"""

import bpy

from ..core import labeling as core_labeling
from ..core import sections as core_sections
from . import cutting, mesh_bridge

TEMP_NAME = "BigPrint_Numero_tmp"


class LabelError(RuntimeError):
    pass


def _text_mesh(context, texto, altura_bu, espesor_bu):
    """Convierte el texto en una malla temporal con volumen."""
    curva = bpy.data.curves.new(TEMP_NAME, type="FONT")
    curva.body = texto
    curva.size = altura_bu
    curva.align_x = "CENTER"
    curva.align_y = "CENTER"
    curva.extrude = espesor_bu * 0.5

    objeto = bpy.data.objects.new(TEMP_NAME, curva)
    context.collection.objects.link(objeto)
    # El texto se lee desde abajo, así que hay que voltearlo o saldría espejado
    objeto.rotation_euler = (0.0, 3.141592653589793, 0.0)

    depsgraph = context.evaluated_depsgraph_get()
    evaluado = objeto.evaluated_get(depsgraph)
    malla = bpy.data.meshes.new_from_object(evaluado)

    bpy.data.objects.remove(objeto, do_unlink=True)
    if curva.users == 0:
        bpy.data.curves.remove(curva)

    if malla is None or not malla.polygons:
        if malla is not None:
            bpy.data.meshes.remove(malla)
        raise LabelError("La tipografía no ha producido geometría")
    return malla


def engrave_piece(context, pieza, texto, factor=1.0, altura_mm=10.0, profundidad_mm=0.6):
    """Graba `texto` en la cara inferior de la pieza. Devuelve el LabelSpot usado."""
    malla_mm = mesh_bridge.mesh_data_from_object(pieza).scaled(factor)
    caja = malla_mm.bbox()
    z_min = caja.min[2]

    seccion = core_sections.extract_section(malla_mm, axis=2, position=z_min, tolerance=0.05)
    if seccion.is_empty:
        raise LabelError(f"{pieza.name} no tiene una cara inferior plana donde grabar")

    spot = core_labeling.best_spot(seccion, texto, desired_height=altura_mm)
    if spot is None or spot.height <= 0.0:
        raise LabelError(f"No cabe el número en la cara inferior de {pieza.name}")

    holgura = 0.5  # el texto asoma por debajo para que el booleano corte limpio
    espesor_mm = profundidad_mm + holgura
    centro_z_mm = z_min + (profundidad_mm - holgura) * 0.5

    malla_texto = _text_mesh(context, texto, spot.height / factor, espesor_mm / factor)
    cortador = bpy.data.objects.new(TEMP_NAME, malla_texto)
    cortador.location = (
        spot.point[0] / factor,
        spot.point[1] / factor,
        centro_z_mm / factor,
    )
    context.collection.objects.link(cortador)

    try:
        cutting.apply_holes(context, [pieza], cortador)
    finally:
        bpy.data.objects.remove(cortador, do_unlink=True)
        if malla_texto.users == 0:
            bpy.data.meshes.remove(malla_texto)

    return spot


def engrave_pieces(context, piezas, factor=1.0, altura_mm=10.0, profundidad_mm=0.6):
    """Graba todas las piezas y devuelve (hechas, avisos)."""
    hechas = []
    avisos = []
    for pieza in sorted(piezas, key=lambda o: o.get("bigprint_piece_index", 0)):
        indice = pieza.get("bigprint_piece_index", len(hechas) + 1)
        texto = core_labeling.label_text(int(indice))
        try:
            spot = engrave_piece(context, pieza, texto, factor, altura_mm, profundidad_mm)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            avisos.append(f"{pieza.name}: {exc}")
            continue
        if not spot.ok:
            avisos.append(f"{texto}: grabado a {spot.height:.1f} mm, puede no leerse")
        hechas.append(pieza)
    return hechas, avisos
