"""Operadores del complemento.

Ninguno de estos operadores escribe en la malla del objeto de origen: el
análisis trabaja sobre copias temporales (ver mesh_bridge).
"""

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from ..core import connectors as cn
from ..core import cut_plan as core_plan
from ..core import sections as core_sections
from ..core import cut_planes as cutp
from ..core import planes as core_planes
from ..core import pieces as core_pieces
from ..core import printer_profiles as pp
from ..core import units as un
from ..core.mesh_analysis import analyze_mesh
from . import (
    connector_objects,
    cut_line,
    cut_plane_object,
    cutting,
    explode,
    exporting,
    labeling,
    mesh_bridge,
)


def _import_mesh_file(filepath: str) -> bool:
    """Importa STL/OBJ/PLY usando el operador disponible en esta versión.

    Blender 4.2 movió el importador de STL a `wm.stl_import` (C++), pero 3.x y
    4.0/4.1 usan `import_mesh.stl`. Se prueban ambos para no atar el complemento
    a una única versión.
    """
    lower = filepath.lower()
    if lower.endswith(".stl"):
        if hasattr(bpy.ops.wm, "stl_import"):
            bpy.ops.wm.stl_import(filepath=filepath)
            return True
        if hasattr(bpy.ops.import_mesh, "stl"):
            bpy.ops.import_mesh.stl(filepath=filepath)
            return True
        return False
    if lower.endswith(".obj"):
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=filepath)
            return True
        if hasattr(bpy.ops.import_scene, "obj"):
            bpy.ops.import_scene.obj(filepath=filepath)
            return True
        return False
    if lower.endswith(".ply"):
        if hasattr(bpy.ops.wm, "ply_import"):
            bpy.ops.wm.ply_import(filepath=filepath)
            return True
        if hasattr(bpy.ops.import_mesh, "ply"):
            bpy.ops.import_mesh.ply(filepath=filepath)
            return True
        return False
    return False



def _modo_objeto(cls, context):
    """Regla del taller: todos los botones trabajan en modo Objeto."""
    if getattr(context, "mode", "OBJECT") != "OBJECT":
        if hasattr(cls, "poll_message_set"):
            cls.poll_message_set("Pasa a modo Objeto (Tab) para usar BigPrint.")
        return False
    return True

class BIGPRINT_OT_import_model(Operator, ImportHelper):
    """Importa un modelo (STL/OBJ/PLY) y lo fija como modelo de trabajo"""

    bl_idname = "bigprint.import_model"
    bl_label = "Importar modelo"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl;*.obj;*.ply", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return _modo_objeto(cls, context)

    def execute(self, context):
        before = set(context.scene.objects)
        try:
            ok = _import_mesh_file(self.filepath)
        except RuntimeError as exc:
            self.report({"ERROR"}, f"Error al importar: {exc}")
            return {"CANCELLED"}

        if not ok:
            self.report({"ERROR"}, "Formato no soportado o importador no disponible")
            return {"CANCELLED"}

        nuevos = [o for o in context.scene.objects if o not in before and o.type == "MESH"]
        if not nuevos:
            self.report({"WARNING"}, "No se ha importado ninguna malla")
            return {"CANCELLED"}

        # Si el fichero trae varias mallas se toma la mayor: en un STL partido
        # por materiales suele ser la pieza principal.
        objetivo = max(nuevos, key=lambda o: len(o.data.vertices))
        context.scene.bigprint.source_object = objetivo
        context.scene.bigprint.analysis.has_data = False
        self.report({"INFO"}, f"Modelo importado: {objetivo.name}")
        return {"FINISHED"}


class BIGPRINT_OT_use_active(Operator):
    """Usa el objeto activo como modelo de trabajo"""

    bl_idname = "bigprint.use_active"
    bl_label = "Usar objeto activo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        return mesh_bridge.is_mesh_object(context.active_object)

    def execute(self, context):
        context.scene.bigprint.source_object = context.active_object
        context.scene.bigprint.analysis.has_data = False
        self.report({"INFO"}, f"Modelo de trabajo: {context.active_object.name}")
        return {"FINISHED"}


class BIGPRINT_OT_analyze(Operator):
    """Analiza el modelo: dimensiones, estanqueidad y volumen (no lo modifica)"""

    bl_idname = "bigprint.analyze"
    bl_label = "Analizar modelo"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and mesh_bridge.is_mesh_object(settings.source_object)

    def execute(self, context):
        settings = context.scene.bigprint
        obj = settings.source_object

        try:
            mesh = mesh_bridge.mesh_data_from_object(
                obj, apply_modifiers=settings.apply_modifiers
            )
        except Exception as exc:  # noqa: BLE001 - se informa al usuario en la UI
            self.report({"ERROR"}, f"No se ha podido leer la malla: {exc}")
            return {"CANCELLED"}

        if mesh.is_empty:
            self.report({"ERROR"}, "La malla no tiene geometría")
            return {"CANCELLED"}

        max_dim = max(mesh.bbox().size)
        scale_length = context.scene.unit_settings.scale_length
        unidad, factor = un.resolve_unit(settings.model_unit, max_dim, scale_length)

        report = analyze_mesh(
            mesh,
            unit_factor=factor,
            unit=unidad,
            # La tolerancia se configura en mm, pero la malla está en unidades
            # de Blender: hay que traerla al mismo espacio antes de soldar.
            weld_tolerance=(settings.weld_tolerance / factor)
            if (settings.weld_for_analysis and factor > 0.0)
            else 0.0,
        )

        profile = settings.resolve_profile()
        fit = pp.check_fit(
            report.dimensions_mm, profile, allow_rotation=settings.allow_rotation
        )

        self._store(settings.analysis, report, fit, unidad, factor)

        # Un diagnóstico negativo NO es un fallo del operador: el análisis ha
        # hecho su trabajo. Reportar {'ERROR'} haría que bpy.ops lanzase
        # RuntimeError en scripts y sacaría un popup rojo en la interfaz cada
        # vez que se analiza una malla con agujeros. El estado real de la malla
        # se ve en el panel.
        # Si el modelo ha cambiado de tamaño o de unidad, la posición guardada
        # ya no significa nada: se recentra igual que al cambiar de eje.
        caja_min = (report.bbox_min_mm[0], report.bbox_min_mm[1], report.bbox_min_mm[2])
        caja_max = (report.bbox_max_mm[0], report.bbox_max_mm[1], report.bbox_max_mm[2])
        if not cutp.is_valid_position(caja_min, caja_max, settings.cut_axis, settings.cut_position):
            settings.cut_position = cutp.center_position(caja_min, caja_max, settings.cut_axis)
        cut_plane_object.update_plane(context)

        nivel = {"OK": "INFO", "AVISO": "WARNING", "ERROR": "WARNING"}[report.status]
        self.report({nivel}, report.summary())
        return {"FINISHED"}

    @staticmethod
    def _store(cache, report, fit, unidad, factor):
        cache.has_data = True
        cache.object_name = report.name
        cache.status = report.status
        cache.resolved_unit = unidad
        cache.unit_factor = factor

        cache.dim_x, cache.dim_y, cache.dim_z = report.dimensions_mm
        cache.bbox_min_x, cache.bbox_min_y, cache.bbox_min_z = report.bbox_min_mm
        cache.bbox_max_x, cache.bbox_max_y, cache.bbox_max_z = report.bbox_max_mm
        cache.volume_cm3 = report.volume_cm3
        cache.area_cm2 = report.area_cm2

        cache.vertex_count = report.vertex_count
        cache.edge_count = report.edge_count
        cache.polygon_count = report.polygon_count
        cache.triangle_count = report.triangle_count

        cache.boundary_edges = report.boundary_edges
        cache.non_manifold_edges = report.non_manifold_edges
        cache.degenerate_triangles = report.degenerate_triangles
        cache.loose_vertices = report.loose_vertices
        cache.shell_count = report.shell_count
        cache.welded_vertices = report.welded_vertices

        cache.is_watertight = report.is_watertight
        cache.is_manifold = report.is_manifold
        cache.has_volume = report.has_volume
        cache.is_solid = report.is_solid
        cache.normals_flipped = report.normals_flipped

        cache.fits_in_printer = fit.fits
        cache.pieces_x, cache.pieces_y, cache.pieces_z = fit.pieces
        cache.pieces_total = fit.total_pieces

        # Solo errores y avisos: las notas informativas duplican lo que ya
        # muestran los indicadores del panel y solo añaden ruido.
        cache.messages = "\n".join(report.errors + report.warnings)


class BIGPRINT_OT_clear_analysis(Operator):
    """Borra el resultado del análisis"""

    bl_idname = "bigprint.clear_analysis"
    bl_label = "Limpiar análisis"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _modo_objeto(cls, context)

    def execute(self, context):
        context.scene.bigprint.analysis.has_data = False
        return {"FINISHED"}


class BIGPRINT_OT_load_example(Operator):
    """Crea un modelo de ejemplo demasiado grande para la impresora"""

    bl_idname = "bigprint.load_example"
    bl_label = "Cargar ejemplo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _modo_objeto(cls, context)

    def execute(self, context):
        from .example_model import build_example_object

        obj = build_example_object(context)
        context.scene.bigprint.source_object = obj
        context.scene.bigprint.model_unit = un.MILLIMETERS
        context.scene.bigprint.analysis.has_data = False
        self.report({"INFO"}, f"Ejemplo creado: {obj.name}")
        return {"FINISHED"}


class BIGPRINT_OT_add_cut_plane(Operator):
    """Crea el plano de corte guía y lo centra en el eje sugerido"""

    bl_idname = "bigprint.add_cut_plane"
    bl_label = "Crear plano de corte"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.analysis.has_data

    def execute(self, context):
        settings = context.scene.bigprint
        datos = settings.analysis
        caja_min = (datos.bbox_min_x, datos.bbox_min_y, datos.bbox_min_z)
        caja_max = (datos.bbox_max_x, datos.bbox_max_y, datos.bbox_max_z)

        eje = cutp.suggest_axis(
            (datos.dim_x, datos.dim_y, datos.dim_z), settings.resolve_profile()
        )
        # Asignar el eje recentra la posición mediante su callback
        settings.cut_axis = cutp.axis_name(eje)
        settings.cut_position = cutp.center_position(caja_min, caja_max, eje)

        cut_plane_object.ensure_plane(context)
        self.report({"INFO"}, f"Plano de corte en {cutp.axis_name(eje)} = "
                              f"{settings.cut_position:.2f} mm")
        return {"FINISHED"}


class BIGPRINT_OT_center_cut_plane(Operator):
    """Centra el plano de corte en el eje actual"""

    bl_idname = "bigprint.center_cut_plane"
    bl_label = "Centrar"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.analysis.has_data

    def execute(self, context):
        settings = context.scene.bigprint
        datos = settings.analysis
        settings.cut_position = cutp.center_position(
            (datos.bbox_min_x, datos.bbox_min_y, datos.bbox_min_z),
            (datos.bbox_max_x, datos.bbox_max_y, datos.bbox_max_z),
            settings.cut_axis,
        )
        return {"FINISHED"}


class BIGPRINT_OT_remove_cut_plane(Operator):
    """Borra el plano de corte guía de la escena"""

    bl_idname = "bigprint.remove_cut_plane"
    bl_label = "Quitar plano"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and cut_plane_object.get_plane(context) is not None

    def execute(self, context):
        cut_plane_object.remove_plane(context)
        return {"FINISHED"}


class BIGPRINT_OT_split_in_two(Operator):
    """Corta el modelo por el plano y genera dos piezas nuevas"""

    bl_idname = "bigprint.split_in_two"
    bl_label = "Cortar en dos"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        if settings is None or not settings.analysis.has_data:
            return False
        # Cortar una malla abierta produce piezas sin sentido: mejor no dejar
        return settings.analysis.is_solid and mesh_bridge.is_mesh_object(settings.source_object)

    def execute(self, context):
        settings = context.scene.bigprint
        datos = settings.analysis
        obj = settings.source_object

        caja_min = (datos.bbox_min_x, datos.bbox_min_y, datos.bbox_min_z)
        caja_max = (datos.bbox_max_x, datos.bbox_max_y, datos.bbox_max_z)
        eje = cutp.axis_index(settings.cut_axis)

        if not cutp.is_valid_position(caja_min, caja_max, eje, settings.cut_position):
            self.report({"ERROR"}, "El plano de corte cae fuera de la pieza")
            return {"CANCELLED"}

        factor = datos.unit_factor or 1.0
        origen = [0.0, 0.0, 0.0]
        origen[eje] = settings.cut_position / factor  # de mm a unidades de Blender
        normal = [0.0, 0.0, 0.0]
        normal[eje] = 1.0

        # Un corte nuevo reemplaza al anterior: si no, Blender iría añadiendo
        # ".001" a los nombres y la numeración dejaría de significar nada.
        cutting.remove_pieces(context, obj.name)
        reset_connectors(context, settings)

        try:
            nuevas = cutting.split_object(context, obj, tuple(origen), tuple(normal))
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.report({"ERROR"}, f"No se ha podido cortar: {exc}")
            return {"CANCELLED"}

        self._verify(context, settings, obj, nuevas)
        settings.cut_result.planes = core_planes.Plane.from_axis(eje, settings.cut_position).serialize()
        self.report({"INFO"}, f"{len(nuevas)} piezas generadas")
        return {"FINISHED"}

    def _verify(self, context, settings, source, nuevas):
        verify_pieces(settings, source, nuevas)


def reset_connectors(context, settings):
    """Un corte nuevo deja viejo cualquier cálculo de conectores: se borra.

    Antes el panel seguía enseñando el aviso del corte anterior («Z = 25: no
    cabe…») aunque ya se hubiera cortado por otro sitio.
    """
    connector_objects.remove_preview(context)
    r = settings.connector_result
    r.has_data = False
    r.applied = False
    r.total = 0
    r.planes_done = 0
    r.planes_failed = 0
    r.details = ""
    r.depth_warning = ""
    r.suggestion = ""
    r.removed_cm3 = 0.0
    r.dowel_count = 0


def verify_pieces(settings, source, nuevas):
    """Analiza cada pieza recién creada: es la comprobación del corte."""
    perfil = settings.resolve_profile()
    factor = settings.analysis.unit_factor or 1.0
    resultado = settings.cut_result

    volumenes = []
    filas = []
    todas_solidas = True
    todas_caben = True

    for pieza in nuevas:
        malla = mesh_bridge.mesh_data_from_object(pieza)
        informe = analyze_mesh(
            malla,
            unit_factor=factor,
            unit=settings.analysis.resolved_unit or "MM",
            weld_tolerance=(settings.weld_tolerance / factor)
            if (settings.weld_for_analysis and factor > 0.0)
            else 0.0,
        )
        cabe = pp.check_fit(
            informe.dimensions_mm, perfil, allow_rotation=settings.allow_rotation
        ).fits
        volumenes.append(informe.volume_cm3)
        todas_solidas = todas_solidas and informe.is_solid
        todas_caben = todas_caben and cabe
        filas.append(
            f"{pieza.name}|{informe.volume_cm3:.2f}|"
            f"{'1' if informe.is_solid else '0'}|{'1' if cabe else '0'}"
        )

    control = core_pieces.check_volumes(settings.analysis.volume_cm3, volumenes)

    resultado.has_data = True
    resultado.source_name = source.name
    resultado.piece_count = len(nuevas)
    resultado.volume_source_cm3 = control.source_volume
    resultado.volume_pieces_cm3 = control.total
    resultado.volume_ok = control.ok
    resultado.volume_error_pct = control.relative_error * 100.0
    resultado.all_solid = todas_solidas
    resultado.all_fit = todas_caben
    resultado.details = "\n".join(filas)


class BIGPRINT_OT_split_grid(Operator):
    """Corta el modelo en todas las piezas necesarias para que quepan"""

    bl_idname = "bigprint.split_grid"
    bl_label = "Cortar automáticamente"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        if settings is None or not settings.analysis.has_data:
            return False
        return settings.analysis.is_solid and mesh_bridge.is_mesh_object(settings.source_object)

    def execute(self, context):
        settings = context.scene.bigprint
        datos = settings.analysis
        obj = settings.source_object

        caja_min = (datos.bbox_min_x, datos.bbox_min_y, datos.bbox_min_z)
        caja_max = (datos.bbox_max_x, datos.bbox_max_y, datos.bbox_max_z)

        try:
            plan = core_plan.plan_grid(
                caja_min, caja_max, settings.resolve_profile(), settings.allow_rotation
            )
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        if not plan.needs_cutting:
            self.report({"INFO"}, "El modelo ya cabe entero: no hay nada que cortar")
            return {"CANCELLED"}

        factor = datos.unit_factor or 1.0
        cutting.remove_pieces(context, obj.name)
        reset_connectors(context, settings)

        try:
            piezas = cutting.split_grid(context, obj, plan, factor)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.report({"ERROR"}, f"No se ha podido cortar: {exc}")
            return {"CANCELLED"}

        if not piezas:
            self.report({"WARNING"}, "El plan no ha producido ninguna pieza")
            return {"CANCELLED"}

        verify_pieces(settings, obj, piezas)
        settings.cut_result.planes = "\n".join(
            core_planes.Plane.from_axis(corte.axis, corte.position).serialize()
            for corte in plan.cuts
        )
        self.report({"INFO"}, f"{len(piezas)} piezas generadas ({plan.describe()})")
        return {"FINISHED"}


class BIGPRINT_OT_remove_pieces(Operator):
    """Borra las piezas generadas y vuelve a mostrar el modelo original"""

    bl_idname = "bigprint.remove_pieces"
    bl_label = "Descartar piezas"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.cut_result.has_data

    def execute(self, context):
        settings = context.scene.bigprint
        borradas = cutting.remove_pieces(context, settings.cut_result.source_name)
        reset_connectors(context, settings)
        settings.cut_result.has_data = False
        self.report({"INFO"}, f"{borradas} piezas descartadas")
        return {"FINISHED"}


class BIGPRINT_OT_preview_connectors(Operator):
    """Calcula dónde van los conectores y los muestra sin tocar las piezas"""

    bl_idname = "bigprint.preview_connectors"
    bl_label = "Calcular conectores"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.cut_result.has_data

    def execute(self, context):
        settings = context.scene.bigprint
        planos = settings.cut_result.plane_list()
        if not planos:
            self.report({"ERROR"}, "No hay caras de corte registradas: vuelve a cortar")
            return {"CANCELLED"}

        factor = settings.analysis.unit_factor or 1.0
        piezas = cutting.find_pieces(context, settings.cut_result.source_name)
        if not piezas:
            self.report({"ERROR"}, "No quedan piezas del corte")
            return {"CANCELLED"}

        grupos = []
        filas = []
        total = 0
        dowels_puestos = 0
        sin_sitio = 0
        sugerencia = ""
        muro = settings.resolved_wall()

        for plano in planos:
            seccion = self._section_at(piezas, plano, factor)
            if seccion is None or seccion.is_empty:
                filas.append(f"{plano.label()}: no se encuentra la cara de corte")
                sin_sitio += 1
                continue

            colocaciones = self._place(settings, seccion)
            etiqueta = plano.label()
            for colocacion in colocaciones:
                if colocacion.ok:
                    grupos.append((plano, colocacion.points, colocacion.spec))
                    total += colocacion.count
                    if colocacion.spec.kind == cn.DOWEL:
                        dowels_puestos += colocacion.count
                    filas.append(f"{etiqueta}: {colocacion.describe()}")
                    continue
                sin_sitio += 1
                kind = colocacion.spec.kind
                tamanos = cn.MAGNET_SIZES if kind == cn.MAGNET else cn.DOWEL_SIZES
                otra = cn.best_fitting(seccion, tamanos, kind, wall=muro)
                if otra is not None:
                    filas.append(f"{etiqueta}: no cabe {colocacion.spec.label}; sí cabe {otra.label}")
                    if not sugerencia:
                        sugerencia = f"{kind}|{_size_key(otra)}|{otra.label}"
                else:
                    filas.append(f"{etiqueta}: {colocacion.describe()} (ni el más pequeño: mejor pegar)")

        aviso = self._check_depth(piezas, grupos, factor)
        resultado = settings.connector_result
        resultado.depth_warning = aviso
        resultado.suggestion = sugerencia

        if not grupos:
            resultado.has_data = True
            resultado.applied = False
            resultado.total = 0
            resultado.planes_done = 0
            resultado.planes_failed = sin_sitio
            resultado.details = "\n".join(filas)
            connector_objects.remove_preview(context)
            self.report({"WARNING"}, "No cabe ningún conector en estas caras")
            return {"FINISHED"}

        connector_objects.build_preview(context, grupos, factor)

        resultado.has_data = True
        resultado.applied = False
        resultado.removed_cm3 = 0.0
        resultado.total = total
        resultado.dowel_count = dowels_puestos
        resultado.planes_done = len({id(g[0]) for g in grupos})
        resultado.planes_failed = sin_sitio
        resultado.details = "\n".join(filas)

        self.report({"INFO"}, f"{total} conectores propuestos")
        return {"FINISHED"}

    @staticmethod
    def _check_depth(piezas, grupos, factor=1.0):
        """¿Cabe el conector sin salir por el otro lado de la pieza?

        Se mide el grosor de cada pieza que toca el plano a lo largo de la
        normal (sirve también para cortes inclinados) y se avisa; no se recorta
        sola porque la longitud del dowel la decide quien lo compra.
        """
        for plano, _puntos, spec in grupos:
            for pieza in piezas:
                bajo, alto = _extent_along(pieza, plano, factor)
                if bajo > 0.01 or alto < -0.01:
                    continue          # esta pieza no toca el plano
                # Cada pieza queda a un lado: su grosor es lo que se aleja del plano
                grosor = alto if abs(alto) > abs(bajo) else -bajo
                if spec.depth > grosor * 0.8:
                    return (
                        f"El conector entra {spec.depth:.1f} mm en una pieza de "
                        f"{grosor:.1f} mm: puede atravesarla"
                    )
        return ""

    @staticmethod
    def _section_at(piezas, plano, factor):
        """Sección de corte en milímetros, tomada de la primera pieza que la tenga.

        Las dos piezas que se tocan comparten exactamente la misma cara, así
        que con una basta. `plano` ya está en milímetros.
        """
        tolerancia = 0.01 if plano.axis is not None else 0.02
        for pieza in piezas:
            malla = mesh_bridge.mesh_data_from_object(pieza).scaled(factor)
            seccion = core_sections.extract_section_plane(malla, plano, tolerance=tolerancia)
            if not seccion.is_empty:
                return seccion
        return None

    @staticmethod
    def _place(settings, seccion):
        """Coloca lo elegido. Con los dos, el dowel manda y el imán se adapta."""
        tope = settings.connector_max
        if settings.connector_kind == "MAGNET":
            return [cn.place_connectors(seccion, settings.resolve_magnet(), tope)]
        if settings.connector_kind == "DOWEL":
            return [cn.place_connectors(seccion, settings.resolve_dowel(), tope)]

        dowels = cn.place_connectors(seccion, settings.resolve_dowel(), max(1, tope // 2))
        imanes = cn.place_connectors(
            seccion,
            settings.resolve_magnet(),
            max(1, tope // 2),
            avoid=dowels.points,
        )
        return [dowels, imanes]


def _extent_along(pieza, plano, factor):
    """Distancia mínima y máxima (mm) de la pieza al plano, medida en su normal."""
    if plano.axis is not None:
        caja_min, caja_max = cutting.world_bbox(pieza)
        p = plano.origin[plano.axis]
        return caja_min[plano.axis] * factor - p, caja_max[plano.axis] * factor - p
    try:
        import numpy as np

        malla = pieza.data
        co = np.empty(len(malla.vertices) * 3, dtype=np.float64)
        malla.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        m = np.array(pieza.matrix_world, dtype=np.float64)
        mundo = co @ m[:3, :3].T + m[:3, 3]
        d = (mundo * factor - np.array(plano.origin)) @ np.array(plano.normal)
        return float(d.min()), float(d.max())
    except Exception:  # noqa: BLE001 - sin numpy se cae a la caja
        caja_min, caja_max = cutting.world_bbox(pieza)
        d = [plano.distance((x * factor, y * factor, z * factor))
             for x in (caja_min[0], caja_max[0]) for y in (caja_min[1], caja_max[1])
             for z in (caja_min[2], caja_max[2])]
        return min(d), max(d)


def _size_key(spec):
    """Clave del desplegable de medidas («3x2», «5x30») para un ConnectorSpec."""
    if spec.kind == cn.MAGNET:
        return f"{spec.diameter:g}x{round(spec.depth - 0.2, 2):g}"
    return f"{spec.diameter:g}x{round(spec.depth * 2.0, 2):g}"


class BIGPRINT_OT_use_suggested_size(Operator):
    """Cambia a la medida que sí cabe y recalcula los conectores"""

    bl_idname = "bigprint.use_suggested_size"
    bl_label = "Usar esta medida"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and bool(settings.connector_result.suggestion)

    def execute(self, context):
        settings = context.scene.bigprint
        kind, clave, _texto = settings.connector_result.suggestion.split("|", 2)
        if kind == cn.MAGNET:
            settings.magnet_size = clave
        else:
            settings.dowel_size = clave
        return bpy.ops.bigprint.preview_connectors()


class BIGPRINT_OT_apply_connectors(Operator):
    """Perfora los agujeros de los conectores en las piezas"""

    bl_idname = "bigprint.apply_connectors"
    bl_label = "Perforar agujeros"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        if settings is None or not settings.connector_result.has_data:
            return False
        if settings.connector_result.applied:
            return False
        return connector_objects.get_preview(context) is not None

    def execute(self, context):
        settings = context.scene.bigprint
        cortador = connector_objects.get_preview(context)
        piezas = cutting.find_pieces(context, settings.cut_result.source_name)
        if not piezas:
            self.report({"ERROR"}, "No quedan piezas que perforar")
            return {"CANCELLED"}

        factor = settings.analysis.unit_factor or 1.0
        antes = self._volumen_total(piezas, factor)

        try:
            cutting.apply_holes(context, piezas, cortador)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        despues = self._volumen_total(piezas, factor)
        connector_objects.remove_preview(context)

        resultado = settings.connector_result
        resultado.applied = True
        resultado.removed_cm3 = antes - despues

        # Al perforar cambian volúmenes y estanqueidad: se revalida todo
        verify_pieces(settings, settings.source_object, piezas)

        if not settings.cut_result.all_solid:
            self.report({"WARNING"}, "Alguna pieza ha dejado de estar cerrada tras perforar")
        else:
            self.report({"INFO"}, f"Agujeros hechos ({resultado.removed_cm3:.2f} cm³ retirados)")
        return {"FINISHED"}

    @staticmethod
    def _volumen_total(piezas, factor):
        total = 0.0
        for pieza in piezas:
            malla = mesh_bridge.mesh_data_from_object(pieza)
            total += analyze_mesh(malla, unit_factor=factor).volume_cm3
        return total


class BIGPRINT_OT_toggle_original(Operator):
    """Muestra u oculta el modelo original sin borrarlo"""

    bl_idname = "bigprint.toggle_original"
    bl_label = "Ver original"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.cut_result.has_data

    def execute(self, context):
        settings = context.scene.bigprint
        original = bpy.data.objects.get(settings.cut_result.source_name)
        if original is None:
            self.report({"ERROR"}, "No se encuentra el modelo original")
            return {"CANCELLED"}

        visible = not original.hide_get()
        try:
            original.hide_set(visible)
        except RuntimeError:
            self.report({"WARNING"}, "El original está en una colección desactivada")
            return {"CANCELLED"}
        self.report({"INFO"}, "Original oculto" if visible else "Original visible")
        return {"FINISHED"}


class BIGPRINT_OT_assemble(Operator):
    """Vuelve a juntar las piezas en su posición de montaje"""

    bl_idname = "bigprint.assemble"
    bl_label = "Montar"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.cut_result.has_data

    def execute(self, context):
        context.scene.bigprint.explode_factor = 0.0
        explode.reset(context)
        return {"FINISHED"}


class BIGPRINT_OT_number_pieces(Operator):
    """Graba el número de cada pieza en su cara inferior"""

    bl_idname = "bigprint.number_pieces"
    bl_label = "Numerar piezas"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.cut_result.has_data

    def execute(self, context):
        settings = context.scene.bigprint
        piezas = cutting.find_pieces(context, settings.cut_result.source_name)
        if not piezas:
            self.report({"ERROR"}, "No hay piezas que numerar")
            return {"CANCELLED"}

        factor = settings.analysis.unit_factor or 1.0
        hechas, avisos = labeling.engrave_pieces(
            context,
            piezas,
            factor=factor,
            altura_mm=settings.label_height,
            profundidad_mm=settings.label_depth,
        )

        settings.label_report = f"{len(hechas)} de {len(piezas)} numeradas"
        if avisos:
            settings.label_report += " · " + avisos[0]

        if not hechas:
            self.report({"ERROR"}, avisos[0] if avisos else "No se ha podido numerar")
            return {"CANCELLED"}

        verify_pieces(settings, settings.source_object, piezas)
        nivel = "WARNING" if avisos else "INFO"
        self.report({nivel}, settings.label_report)
        return {"FINISHED"}


class BIGPRINT_OT_export_pieces(Operator):
    """Escribe un STL por pieza, en milímetros, más la lista en CSV"""

    bl_idname = "bigprint.export_pieces"
    bl_label = "Exportar piezas"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        settings = getattr(context.scene, "bigprint", None)
        return settings is not None and settings.cut_result.has_data

    def execute(self, context):
        settings = context.scene.bigprint
        piezas = cutting.find_pieces(context, settings.cut_result.source_name)
        if not piezas:
            self.report({"ERROR"}, "No hay piezas que exportar")
            return {"CANCELLED"}

        # El despiece es solo para mirar: los STL salen en posición de montaje
        # para que las coordenadas sigan siendo las del modelo original.
        if settings.explode_factor > 0.0:
            explode.reset(context)

        factor = settings.analysis.unit_factor or 1.0
        try:
            filas = exporting.export_pieces(
                context,
                piezas,
                settings.export_dir,
                factor=factor,
                profile=settings.resolve_profile(),
                allow_rotation=settings.allow_rotation,
            )
            varillas = settings.connector_result.dowel_count
            if settings.export_dowels and varillas:
                _ruta, fila = exporting.export_dowels(
                    settings.export_dir,
                    settings.resolve_dowel(),
                    varillas,
                    settings.dowel_fit_gap,
                )
                filas.append(fila)

            if settings.export_list:
                exporting.write_parts_list(filas, settings.export_dir)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.report({"ERROR"}, f"No se ha podido exportar: {exc}")
            return {"CANCELLED"}

        from ..core import parts_list

        resumen = parts_list.summary(filas)
        settings.export_report = resumen
        self.report({"INFO"}, f"Exportado: {resumen}")
        return {"FINISHED"}


class BIGPRINT_OT_clear_connectors(Operator):
    """Quita la vista previa de conectores"""

    bl_idname = "bigprint.clear_connectors"
    bl_label = "Quitar conectores"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _modo_objeto(cls, context):
            return False
        return connector_objects.get_preview(context) is not None

    def execute(self, context):
        connector_objects.remove_preview(context)
        context.scene.bigprint.connector_result.has_data = False
        return {"FINISHED"}


CLASSES = (
    BIGPRINT_OT_import_model,
    BIGPRINT_OT_use_active,
    BIGPRINT_OT_analyze,
    BIGPRINT_OT_clear_analysis,
    BIGPRINT_OT_load_example,
    BIGPRINT_OT_add_cut_plane,
    BIGPRINT_OT_center_cut_plane,
    BIGPRINT_OT_remove_cut_plane,
    BIGPRINT_OT_split_in_two,
    BIGPRINT_OT_split_grid,
    BIGPRINT_OT_remove_pieces,
    *cut_line.CLASSES,
    BIGPRINT_OT_preview_connectors,
    BIGPRINT_OT_use_suggested_size,
    BIGPRINT_OT_apply_connectors,
    BIGPRINT_OT_clear_connectors,
    BIGPRINT_OT_assemble,
    BIGPRINT_OT_toggle_original,
    BIGPRINT_OT_number_pieces,
    BIGPRINT_OT_export_pieces,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    cut_line.register_draw()


def unregister():
    cut_line.unregister_draw()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
