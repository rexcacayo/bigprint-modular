"""Línea de corte: se dibuja con clics sobre el modelo y se corta por ella.

Sustituye al plano manual. Se pincha alrededor de la pieza por donde se quiere
cortar; con los puntos se calcula el plano que mejor pasa por ellos (puede
estar inclinado) y se corta con el mismo `split_object` de siempre.

Controles mientras se dibuja:
  clic izquierdo   añadir punto (sobre la superficie del modelo)
  clic en el 1.º   cerrar la línea   ·   Intro también cierra
  Retroceso        quitar el último punto
  Esc / clic dcho  cancelar
  rueda / botón central   girar y hacer zoom como siempre
"""

import bpy
import gpu
from bpy.types import Operator
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..core import planes as core_planes
from . import cutting, mesh_bridge

_HANDLE = None
_LIVE = {"points": None, "hover": None}   # lo que se está dibujando ahora mismo

COLOR_LINE = (1.0, 0.82, 0.1, 1.0)
COLOR_FIRST = (0.35, 1.0, 0.45, 1.0)
COLOR_HOVER = (1.0, 1.0, 1.0, 0.8)
CLOSE_PX = 14


# --------------------------------------------------------------------------- dibujo
def _draw():
    ctx = bpy.context
    scene = getattr(ctx, "scene", None)
    settings = getattr(scene, "bigprint", None) if scene else None
    vivos = _LIVE["points"]
    if vivos is not None:
        puntos = list(vivos)
        cerrada = False
    elif settings is not None and settings.line_points:
        try:
            puntos = [Vector(p) for p in settings.line_point_list()]
        except ValueError:
            return
        cerrada = len(puntos) >= 3
    else:
        return
    if not puntos and _LIVE["hover"] is None:
        return

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    gpu.state.line_width_set(3.0)

    tramo = list(puntos)
    if vivos is not None and _LIVE["hover"] is not None and puntos:
        tramo.append(_LIVE["hover"])
    if cerrada:
        tramo.append(puntos[0])
    if len(tramo) >= 2:
        batch = batch_for_shader(shader, "LINE_STRIP", {"pos": [tuple(p) for p in tramo]})
        shader.uniform_float("color", COLOR_LINE)
        batch.draw(shader)

    gpu.state.point_size_set(9.0)
    if puntos:
        batch = batch_for_shader(shader, "POINTS", {"pos": [tuple(p) for p in puntos[1:]] or [tuple(puntos[0])]})
        shader.uniform_float("color", COLOR_LINE)
        batch.draw(shader)
        gpu.state.point_size_set(13.0)
        batch = batch_for_shader(shader, "POINTS", {"pos": [tuple(puntos[0])]})
        shader.uniform_float("color", COLOR_FIRST)
        batch.draw(shader)
    if vivos is not None and _LIVE["hover"] is not None:
        gpu.state.point_size_set(7.0)
        batch = batch_for_shader(shader, "POINTS", {"pos": [tuple(_LIVE["hover"])]})
        shader.uniform_float("color", COLOR_HOVER)
        batch.draw(shader)

    gpu.state.point_size_set(1.0)
    gpu.state.line_width_set(1.0)
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.blend_set("NONE")


def register_draw():
    global _HANDLE
    if _HANDLE is None:
        _HANDLE = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_VIEW")


def unregister_draw():
    global _HANDLE
    if _HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_HANDLE, "WINDOW")
        _HANDLE = None


def _redraw(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == "VIEW_3D":
            area.tag_redraw()


# --------------------------------------------------------------------------- informe
def describe_line(points_bu, factor):
    """Texto corto para el panel: si la línea es plana y cuánto se inclina."""
    if len(points_bu) < 3:
        return "Faltan puntos: pincha al menos tres alrededor de la pieza"
    try:
        plano, desviacion = core_planes.fit_plane(points_bu)
    except ValueError as exc:
        return str(exc)
    plano = core_planes.snap_to_axis(plano)
    inclinacion = core_planes.tilt_degrees(plano)
    forma = "recta" if inclinacion < 0.05 else f"inclinada {inclinacion:.0f}°"
    texto = f"{len(points_bu)} puntos · corte {forma}"
    desviacion_mm = desviacion * factor
    if desviacion_mm > 1.0:
        texto += f" · la línea se aparta hasta {desviacion_mm:.1f} mm del plano medio"
    return texto


# --------------------------------------------------------------------------- operadores
def _poll_source(context):
    if context.mode != "OBJECT":
        return False
    settings = getattr(context.scene, "bigprint", None)
    if settings is None or not settings.analysis.has_data:
        return False
    return mesh_bridge.is_mesh_object(settings.source_object)


class BIGPRINT_OT_draw_cut_line(Operator):
    """Dibuja con clics, sobre el modelo, la línea por donde quieres cortar"""

    bl_idname = "bigprint.draw_cut_line"
    bl_label = "Dibujar línea de corte"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _poll_source(context):
            return False
        return context.area is not None and context.area.type == "VIEW_3D"

    # -- utilidades
    def _hit(self, context, event):
        region = context.region
        rv3d = context.region_data
        if region is None or rv3d is None:
            return None
        coord = (event.mouse_region_x, event.mouse_region_y)
        origen = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direccion = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        obj = self._obj
        inversa = obj.matrix_world.inverted()
        o_local = inversa @ origen
        d_local = (inversa.to_3x3() @ direccion).normalized()
        depsgraph = context.evaluated_depsgraph_get()
        evaluado = obj.evaluated_get(depsgraph)
        ok, punto, _normal, _idx = evaluado.ray_cast(o_local, d_local)
        if not ok:
            return None
        return obj.matrix_world @ punto

    def _near_first(self, context, event):
        if len(self._points) < 3:
            return False
        pantalla = view3d_utils.location_3d_to_region_2d(
            context.region, context.region_data, self._points[0]
        )
        if pantalla is None:
            return False
        dx = pantalla.x - event.mouse_region_x
        dy = pantalla.y - event.mouse_region_y
        return dx * dx + dy * dy <= CLOSE_PX * CLOSE_PX

    def _header(self, context):
        n = len(self._points)
        if n < 3:
            texto = f"Línea de corte: {n} puntos · clic = punto · Retroceso = deshacer · Esc = cancelar"
        else:
            texto = (f"Línea de corte: {n} puntos · clic en el punto verde o Intro = cerrar · "
                     "Retroceso = deshacer · Esc = cancelar")
        context.area.header_text_set(texto)

    def _finish(self, context, cancelled):
        _LIVE["points"] = None
        _LIVE["hover"] = None
        context.area.header_text_set(None)
        context.window.cursor_modal_restore()
        if cancelled:
            for obj, oculto in self._visibility:
                try:
                    obj.hide_set(oculto)
                except RuntimeError:
                    pass
        _redraw(context)

    # -- ciclo
    def invoke(self, context, event):
        settings = context.scene.bigprint
        self._obj = settings.source_object
        self._points = []
        self._visibility = []
        # Se dibuja sobre el modelo entero: si hay piezas, se apartan mientras.
        piezas = cutting.find_pieces(context, self._obj.name)
        for obj in [self._obj, *piezas]:
            try:
                self._visibility.append((obj, obj.hide_get()))
            except RuntimeError:
                pass
        try:
            self._obj.hide_set(False)
            for p in piezas:
                p.hide_set(True)
        except RuntimeError:
            pass

        register_draw()
        _LIVE["points"] = self._points
        _LIVE["hover"] = None
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        self._header(context)
        _redraw(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None:
            self._finish(context, True)
            return {"CANCELLED"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE",
                          "TRACKPADPAN", "TRACKPADZOOM", "NDOF_MOTION"} or (
                event.type.startswith("NUMPAD") and event.type not in {"NUMPAD_ENTER"}):
            return {"PASS_THROUGH"}

        if event.type == "MOUSEMOVE":
            _LIVE["hover"] = self._hit(context, event)
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.value != "PRESS":
            return {"RUNNING_MODAL"}

        if event.type in {"ESC", "RIGHTMOUSE"}:
            self._finish(context, True)
            self.report({"INFO"}, "Línea cancelada")
            return {"CANCELLED"}

        if event.type == "BACK_SPACE":
            if self._points:
                self._points.pop()
            self._header(context)
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        cerrar = event.type in {"RET", "NUMPAD_ENTER", "SPACE"} and len(self._points) >= 3
        if event.type == "LEFTMOUSE":
            if self._near_first(context, event):
                cerrar = True
            else:
                punto = self._hit(context, event)
                if punto is None:
                    self.report({"WARNING"}, "Pincha sobre el modelo")
                else:
                    self._points.append(punto.copy())
                    self._header(context)
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}

        if cerrar:
            settings = context.scene.bigprint
            settings.line_points = ";".join(f"{p.x:.6f},{p.y:.6f},{p.z:.6f}" for p in self._points)
            factor = settings.analysis.unit_factor or 1.0
            settings.line_report = describe_line([tuple(p) for p in self._points], factor)
            self._finish(context, False)
            self.report({"INFO"}, settings.line_report)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


class BIGPRINT_OT_cut_by_line(Operator):
    """Corta el modelo en dos por la línea dibujada (el plano que mejor pasa por ella)"""

    bl_idname = "bigprint.cut_by_line"
    bl_label = "Cortar por la línea"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _poll_source(context):
            return False
        settings = context.scene.bigprint
        return settings.analysis.is_solid and len(settings.line_point_list()) >= 3

    def execute(self, context):
        from . import operators as ops  # import tardío: operators importa este módulo

        settings = context.scene.bigprint
        obj = settings.source_object
        factor = settings.analysis.unit_factor or 1.0
        try:
            plano, _dev = core_planes.fit_plane(settings.line_point_list())
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        plano = core_planes.snap_to_axis(plano)

        # ¿El plano atraviesa el modelo? Si todo queda a un lado no hay corte.
        caja_min, caja_max = cutting.world_bbox(obj)
        d = [plano.distance((x, y, z)) for x in (caja_min[0], caja_max[0])
             for y in (caja_min[1], caja_max[1]) for z in (caja_min[2], caja_max[2])]
        if min(d) >= 0 or max(d) <= 0:
            self.report({"ERROR"}, "La línea no atraviesa el modelo")
            return {"CANCELLED"}

        cutting.remove_pieces(context, obj.name)
        ops.reset_connectors(context, settings)
        try:
            nuevas = cutting.split_object(context, obj, tuple(plano.origin), tuple(plano.normal))
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.report({"ERROR"}, f"No se ha podido cortar: {exc}")
            return {"CANCELLED"}

        ops.verify_pieces(settings, obj, nuevas)
        settings.cut_result.planes = plano.scaled(factor).serialize()
        # La línea ya cumplió: se borra para que no tape las piezas.
        settings.line_points = ""
        settings.line_report = ""
        _redraw(context)
        self.report({"INFO"}, f"{len(nuevas)} piezas generadas")
        return {"FINISHED"}


class BIGPRINT_OT_clear_cut_line(Operator):
    """Borra la línea de corte dibujada"""

    bl_idname = "bigprint.clear_cut_line"
    bl_label = "Borrar línea"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and bool(settings.line_points)

    def execute(self, context):
        settings = context.scene.bigprint
        settings.line_points = ""
        settings.line_report = ""
        _redraw(context)
        return {"FINISHED"}


CLASSES = (BIGPRINT_OT_draw_cut_line, BIGPRINT_OT_cut_by_line, BIGPRINT_OT_clear_cut_line)
