"""Paneles de la barra lateral (tecla N, pestaña "BigPrint").

`draw()` solo lee la caché del análisis: nunca recalcula ni toca la malla.
"""

import bpy
from bpy.types import Panel

from ..core import cut_plan as cpl
from ..core import cut_planes as cp
from ..core import printer_profiles as pp
from ..core import units as un
from . import connector_objects, cut_plane_object

CATEGORY = "BigPrint"


class BigPrintPanelBase:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


class VIEW3D_PT_bigprint_main(BigPrintPanelBase, Panel):
    bl_idname = "VIEW3D_PT_bigprint_main"
    bl_label = "BigPrint Modular"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Fase 1: preparar y analizar", icon="MOD_BUILD")


class VIEW3D_PT_bigprint_printer(BigPrintPanelBase, Panel):
    bl_idname = "VIEW3D_PT_bigprint_printer"
    bl_parent_id = "VIEW3D_PT_bigprint_main"
    bl_label = "Impresora"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bigprint

        layout.prop(settings, "profile_id", text="")

        if settings.profile_id == pp.CUSTOM_ID:
            col = layout.column(align=True)
            col.prop(settings, "custom_size_x")
            col.prop(settings, "custom_size_y")
            col.prop(settings, "custom_size_z")
            layout.prop(settings, "custom_margin")

        try:
            profile = settings.resolve_profile()
        except ValueError as exc:
            layout.label(text=str(exc), icon="ERROR")
            return

        ux, uy, uz = profile.usable
        box = layout.box()
        box.label(text=f"Volumen: {profile.size_x:g} × {profile.size_y:g} × {profile.size_z:g} mm")
        box.label(text=f"Margen: {profile.margin:g} mm por lado")
        box.label(text=f"Útil: {ux:g} × {uy:g} × {uz:g} mm", icon="SHADING_BBOX")


class VIEW3D_PT_bigprint_model(BigPrintPanelBase, Panel):
    bl_idname = "VIEW3D_PT_bigprint_model"
    bl_parent_id = "VIEW3D_PT_bigprint_main"
    bl_label = "Modelo"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bigprint

        row = layout.row(align=True)
        row.operator("bigprint.import_model", icon="IMPORT")
        row.operator("bigprint.use_active", text="", icon="EYEDROPPER")

        layout.prop(settings, "source_object", text="")
        layout.operator("bigprint.load_example", icon="MESH_CUBE")

        obj = settings.source_object
        if obj is None:
            layout.label(text="Sin modelo seleccionado", icon="INFO")
            return

        col = layout.column(align=True)
        col.prop(settings, "model_unit")
        col.prop(settings, "apply_modifiers")
        col.prop(settings, "allow_rotation")

        col = layout.column(align=True)
        col.prop(settings, "weld_for_analysis")
        sub = col.row()
        sub.enabled = settings.weld_for_analysis
        sub.prop(settings, "weld_tolerance")

        layout.label(text="El original nunca se modifica", icon="LOCKED")


class VIEW3D_PT_bigprint_analysis(BigPrintPanelBase, Panel):
    bl_idname = "VIEW3D_PT_bigprint_analysis"
    bl_parent_id = "VIEW3D_PT_bigprint_main"
    bl_label = "Análisis"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bigprint
        data = settings.analysis

        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("bigprint.analyze", icon="VIEWZOOM")
        row.operator("bigprint.clear_analysis", text="", icon="X")

        if not data.has_data:
            layout.label(text="Sin analizar", icon="INFO")
            return

        icono = {"OK": "CHECKMARK", "AVISO": "ERROR", "ERROR": "CANCEL"}.get(data.status, "INFO")
        layout.label(text=f"{data.object_name} — {data.status}", icon=icono)

        box = layout.box()
        box.label(text="Dimensiones (mm)", icon="DRIVER_DISTANCE")
        col = box.column(align=True)
        col.label(text=f"X: {data.dim_x:.2f}")
        col.label(text=f"Y: {data.dim_y:.2f}")
        col.label(text=f"Z: {data.dim_z:.2f}")
        unidad = un.UNIT_LABELS.get(data.resolved_unit, data.resolved_unit)
        col.label(text=f"Unidad usada: {unidad} (×{data.unit_factor:g})")

        box = layout.box()
        box.label(text="Estado de la malla", icon="MESH_DATA")
        col = box.column(align=True)
        col.label(
            text="Cerrada: " + ("sí" if data.is_watertight else "no"),
            icon="CHECKMARK" if data.is_watertight else "CANCEL",
        )
        col.label(
            text="Manifold: " + ("sí" if data.is_manifold else "no"),
            icon="CHECKMARK" if data.is_manifold else "CANCEL",
        )
        col.label(
            text=f"Volumen: {data.volume_cm3:.2f} cm³",
            icon="CHECKMARK" if data.has_volume else "CANCEL",
        )
        col.label(text=f"Superficie: {data.area_cm2:.2f} cm²")
        col.label(
            text="Apta para cortar: " + ("sí" if data.is_solid else "no"),
            icon="CHECKMARK" if data.is_solid else "ERROR",
        )

        box = layout.box()
        box.label(text="Topología", icon="OUTLINER_DATA_MESH")
        col = box.column(align=True)
        col.label(text=f"Vértices: {data.vertex_count}   Caras: {data.polygon_count}")
        col.label(text=f"Aristas: {data.edge_count}   Triángulos: {data.triangle_count}")
        if data.boundary_edges:
            col.label(text=f"Aristas de borde: {data.boundary_edges}", icon="ERROR")
        if data.non_manifold_edges:
            col.label(text=f"No-manifold: {data.non_manifold_edges}", icon="ERROR")
        if data.shell_count > 1:
            col.label(text=f"Islas: {data.shell_count}", icon="ERROR")
        if data.welded_vertices:
            col.label(text=f"Vértices fundidos al analizar: {data.welded_vertices}")

        box = layout.box()
        box.label(text="Encaje en la impresora", icon="SHADING_BBOX")
        col = box.column(align=True)
        if data.fits_in_printer:
            col.label(text="Cabe entera: no hace falta partir", icon="CHECKMARK")
        else:
            col.label(text="No cabe: hay que partir", icon="ERROR")
            col.label(
                text=f"{data.pieces_x} × {data.pieces_y} × {data.pieces_z}"
                f" = {data.pieces_total} piezas"
            )
            col.label(text="Estimación previa en rejilla")

        mensajes = data.message_list()
        if mensajes:
            box = layout.box()
            box.label(text="Avisos", icon="INFO")
            col = box.column(align=True)
            for m in mensajes:
                col.label(text=m)


class VIEW3D_PT_bigprint_cut(BigPrintPanelBase, Panel):
    bl_idname = "VIEW3D_PT_bigprint_cut"
    bl_parent_id = "VIEW3D_PT_bigprint_main"
    bl_label = "Corte"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bigprint
        data = settings.analysis

        if not data.has_data:
            layout.label(text="Analiza el modelo primero", icon="INFO")
            return

        caja_min_p = (data.bbox_min_x, data.bbox_min_y, data.bbox_min_z)
        caja_max_p = (data.bbox_max_x, data.bbox_max_y, data.bbox_max_z)

        if data.is_solid and caja_max_p[0] > caja_min_p[0]:
            box = layout.box()
            box.label(text="Corte automático", icon="MOD_ARRAY")
            try:
                plan = cpl.plan_grid(
                    caja_min_p, caja_max_p, settings.resolve_profile(), settings.allow_rotation
                )
            except ValueError as exc:
                box.label(text=str(exc), icon="ERROR")
            else:
                box.label(text=plan.describe())
                fila = box.row()
                fila.scale_y = 1.3
                fila.enabled = plan.needs_cutting
                fila.operator("bigprint.split_grid", icon="MOD_ARRAY")

        layout.separator()
        layout.label(text="Corte manual", icon="MOD_BEVEL")

        hay_plano = cut_plane_object.get_plane(context) is not None
        row = layout.row(align=True)
        if hay_plano:
            row.operator("bigprint.add_cut_plane", text="Recolocar", icon="FILE_REFRESH")
            row.operator("bigprint.remove_cut_plane", text="", icon="X")
        else:
            row.operator("bigprint.add_cut_plane", icon="MOD_BEVEL")
            return

        col = layout.column(align=True)
        col.row(align=True).prop(settings, "cut_axis", expand=True)
        fila = col.row(align=True)
        fila.prop(settings, "cut_position", text="Pos (mm)")
        fila.operator("bigprint.center_cut_plane", text="", icon="ANCHOR_CENTER")

        caja_min = (data.bbox_min_x, data.bbox_min_y, data.bbox_min_z)
        caja_max = (data.bbox_max_x, data.bbox_max_y, data.bbox_max_z)
        eje = cp.axis_index(settings.cut_axis)

        if caja_max[eje] - caja_min[eje] <= 0.0:
            # Caché de una versión anterior o análisis vacío
            layout.label(text="Datos incompletos", icon="ERROR")
            layout.label(text="Vuelve a analizar el modelo")
            return

        box = layout.box()
        box.label(text=f"Rango en {settings.cut_axis}", icon="ARROW_LEFTRIGHT")
        box.label(text=f"{caja_min[eje]:.1f} a {caja_max[eje]:.1f} mm")

        if not cp.is_valid_position(caja_min, caja_max, eje, settings.cut_position):
            box.label(text="El plano cae fuera de la pieza", icon="ERROR")
            return

        try:
            vista = cp.preview_split(
                caja_min,
                caja_max,
                eje,
                settings.cut_position,
                settings.resolve_profile(),
                settings.allow_rotation,
            )
        except ValueError:
            return

        box = layout.box()
        box.label(text="Reparto previsto", icon="MOD_BUILD")
        col = box.column(align=True)
        for etiqueta, dims, cabe in (
            ("Lado bajo", vista.dims_low, vista.fits_low),
            ("Lado alto", vista.dims_high, vista.fits_high),
        ):
            col.label(
                text=f"{etiqueta}: {dims[0]:.0f} × {dims[1]:.0f} × {dims[2]:.0f}",
                icon="CHECKMARK" if cabe else "ERROR",
            )
        if vista.both_fit:
            col.label(text="Un solo corte basta")
        else:
            col.label(text="Harán falta más cortes")

        fila = layout.row(align=True)
        fila.scale_y = 1.3
        fila.operator("bigprint.split_in_two", icon="MOD_BOOLEAN")

        if not data.is_solid:
            layout.label(text="Solo se corta una malla sólida", icon="ERROR")

        self._draw_result(layout, settings)

    @staticmethod
    def _draw_result(layout, settings):
        resultado = settings.cut_result
        if not resultado.has_data:
            return

        box = layout.box()
        fila = box.row(align=True)
        fila.label(text=f"{resultado.piece_count} piezas", icon="OUTLINER_OB_MESH")
        fila.operator("bigprint.remove_pieces", text="", icon="TRASH")

        col = box.column(align=True)
        for nombre, volumen, solida, cabe in resultado.piece_rows():
            col.label(
                text=f"{nombre.split('_')[-1]}: {volumen:.1f} cm³",
                icon="CHECKMARK" if (solida and cabe) else "ERROR",
            )
            if not solida:
                col.label(text="   no ha quedado cerrada")
            elif not cabe:
                col.label(text="   sigue sin caber")

        col = box.column(align=True)
        col.label(
            text=f"Suma: {resultado.volume_pieces_cm3:.1f} de "
            f"{resultado.volume_source_cm3:.1f} cm³",
            icon="CHECKMARK" if resultado.volume_ok else "ERROR",
        )
        if not resultado.volume_ok:
            col.label(text=f"Diferencia: {resultado.volume_error_pct:.2f} %")


class VIEW3D_PT_bigprint_connectors(BigPrintPanelBase, Panel):
    bl_idname = "VIEW3D_PT_bigprint_connectors"
    bl_parent_id = "VIEW3D_PT_bigprint_main"
    bl_label = "Conectores"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bigprint

        if not settings.cut_result.has_data:
            layout.label(text="Corta el modelo primero", icon="INFO")
            return

        col = layout.column(align=True)
        col.prop(settings, "connector_kind", text="")
        if settings.connector_kind in {"DOWEL", "BOTH"}:
            col.prop(settings, "dowel_size")
        if settings.connector_kind in {"MAGNET", "BOTH"}:
            col.prop(settings, "magnet_size")
        col.prop(settings, "connector_max")

        fila = layout.row(align=True)
        fila.scale_y = 1.3
        fila.operator("bigprint.preview_connectors", icon="SNAP_MIDPOINT")
        if connector_objects.get_preview(context) is not None:
            fila.operator("bigprint.clear_connectors", text="", icon="X")

        resultado = settings.connector_result
        if not resultado.has_data:
            return

        box = layout.box()
        if resultado.total:
            box.label(text=f"{resultado.total} conectores", icon="CHECKMARK")
        else:
            box.label(text="No cabe ninguno", icon="ERROR")
        col = box.column(align=True)
        for linea in resultado.lines():
            col.label(text=linea)

        if resultado.depth_warning:
            aviso = layout.box()
            aviso.label(text="Profundidad", icon="ERROR")
            aviso.label(text=resultado.depth_warning)

        if resultado.applied:
            hecho = layout.box()
            hecho.label(text="Agujeros hechos", icon="CHECKMARK")
            hecho.label(text=f"Material retirado: {resultado.removed_cm3:.2f} cm³")
        elif resultado.total:
            fila = layout.row()
            fila.scale_y = 1.3
            fila.operator("bigprint.apply_connectors", icon="MOD_BOOLEAN")


class VIEW3D_PT_bigprint_export(BigPrintPanelBase, Panel):
    bl_idname = "VIEW3D_PT_bigprint_export"
    bl_parent_id = "VIEW3D_PT_bigprint_main"
    bl_label = "Exportar"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bigprint

        if not settings.cut_result.has_data:
            layout.label(text="Corta el modelo primero", icon="INFO")
            return

        fila = layout.row(align=True)
        fila.prop(settings, "explode_factor", slider=True)
        fila.operator("bigprint.assemble", text="", icon="SNAP_ON")
        fila.operator("bigprint.toggle_original", text="", icon="HIDE_OFF")
        layout.separator()

        col = layout.column(align=True)
        col.prop(settings, "label_height")
        col.prop(settings, "label_depth")
        fila = layout.row()
        fila.operator("bigprint.number_pieces", icon="FONT_DATA")
        if settings.label_report:
            layout.label(text=settings.label_report)
        layout.separator()

        col = layout.column(align=True)
        col.prop(settings, "export_dir")
        col.prop(settings, "export_list")

        fila = layout.row()
        fila.scale_y = 1.3
        fila.operator("bigprint.export_pieces", icon="EXPORT")

        layout.label(text="Un STL por pieza, en mm")

        if settings.export_report:
            box = layout.box()
            box.label(text="Último export", icon="CHECKMARK")
            box.label(text=settings.export_report)


CLASSES = (
    VIEW3D_PT_bigprint_main,
    VIEW3D_PT_bigprint_printer,
    VIEW3D_PT_bigprint_model,
    VIEW3D_PT_bigprint_analysis,
    VIEW3D_PT_bigprint_cut,
    VIEW3D_PT_bigprint_connectors,
    VIEW3D_PT_bigprint_export,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
