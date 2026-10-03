"""Propiedades de escena del complemento.

El resultado del análisis se cachea en la escena (y no se recalcula al pintar
el panel) porque `draw()` se ejecuta en cada refresco y analizar una malla
grande ahí dejaría la interfaz inutilizable.

Aviso: aquí NO se puede usar `from __future__ import annotations`. Blender
registra las propiedades leyendo `__annotations__`, y PEP 563 las convertiría
en cadenas: las propiedades desaparecerían sin dar error claro.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from ..core.connectors import DOWEL_SIZES as _DOWEL_SIZES
from ..core.connectors import MAGNET_SIZES as _MAGNET_SIZES
from ..core import printer_profiles as pp
from ..core import units as un

# Blender no retiene las cadenas de los EnumProperty dinámicos: si se generan
# en cada llamada, se corrompen. Se cachean a nivel de módulo.
_PROFILE_ITEMS = [
    (pid, label, desc) for pid, label, desc in pp.profile_enum_items()
]

_UNIT_ITEMS = [
    (un.AUTO, "Automático", "Deducir la unidad a partir del tamaño del modelo"),
    (un.MILLIMETERS, "Milímetros", "1 unidad de Blender = 1 mm (lo habitual en STL)"),
    (un.CENTIMETERS, "Centímetros", "1 unidad de Blender = 1 cm"),
    (un.METERS, "Metros", "1 unidad de Blender = 1 m (defecto de Blender)"),
    (un.INCHES, "Pulgadas", "1 unidad de Blender = 25,4 mm"),
    (un.SCENE, "Escala de la escena", "Usar scene.unit_settings.scale_length"),
]


_AXIS_ITEMS = [
    ("X", "X", "Cortar con un plano perpendicular al eje X"),
    ("Y", "Y", "Cortar con un plano perpendicular al eje Y"),
    ("Z", "Z", "Cortar con un plano perpendicular al eje Z"),
]


def _on_cut_changed(self, context):
    """Recoloca el plano guía al mover el deslizador, sin tocar la malla."""
    from . import cut_plane_object

    cut_plane_object.update_plane(context)


def _on_axis_changed(self, context):
    """Al cambiar de eje, recentrar: la posición del eje anterior no significa nada aquí."""
    from ..core import cut_planes as cp
    from . import cut_plane_object

    datos = self.analysis
    if datos.has_data:
        caja_min = (datos.bbox_min_x, datos.bbox_min_y, datos.bbox_min_z)
        caja_max = (datos.bbox_max_x, datos.bbox_max_y, datos.bbox_max_z)
        # Asignar cut_position dispara _on_cut_changed, que ya recoloca el plano
        self.cut_position = cp.center_position(caja_min, caja_max, self.cut_axis)
    else:
        cut_plane_object.update_plane(context)


def _on_explode_changed(self, context):
    """Recolocar en vivo al mover el deslizador: solo mueve objetos."""
    from . import explode

    explode.apply_explode(context, self.explode_factor)


def _profile_items(self, context):
    return _PROFILE_ITEMS


def _mesh_object_poll(self, obj):
    return getattr(obj, "type", None) == "MESH"


class BigPrintAnalysis(PropertyGroup):
    """Caché del último análisis ejecutado."""

    has_data: BoolProperty(name="Analizado", default=False)
    object_name: StringProperty(name="Objeto", default="")
    status: StringProperty(name="Estado", default="")

    resolved_unit: StringProperty(name="Unidad", default="")
    unit_factor: FloatProperty(name="Factor a mm", default=1.0)

    dim_x: FloatProperty(name="X (mm)", default=0.0)
    dim_y: FloatProperty(name="Y (mm)", default=0.0)
    dim_z: FloatProperty(name="Z (mm)", default=0.0)

    bbox_min_x: FloatProperty(name="X mín (mm)", default=0.0)
    bbox_min_y: FloatProperty(name="Y mín (mm)", default=0.0)
    bbox_min_z: FloatProperty(name="Z mín (mm)", default=0.0)
    bbox_max_x: FloatProperty(name="X máx (mm)", default=0.0)
    bbox_max_y: FloatProperty(name="Y máx (mm)", default=0.0)
    bbox_max_z: FloatProperty(name="Z máx (mm)", default=0.0)

    volume_cm3: FloatProperty(name="Volumen (cm³)", default=0.0)
    area_cm2: FloatProperty(name="Superficie (cm²)", default=0.0)

    vertex_count: IntProperty(name="Vértices", default=0)
    edge_count: IntProperty(name="Aristas", default=0)
    polygon_count: IntProperty(name="Caras", default=0)
    triangle_count: IntProperty(name="Triángulos", default=0)

    boundary_edges: IntProperty(name="Aristas de borde", default=0)
    non_manifold_edges: IntProperty(name="Aristas no-manifold", default=0)
    degenerate_triangles: IntProperty(name="Triángulos degenerados", default=0)
    loose_vertices: IntProperty(name="Vértices sueltos", default=0)
    shell_count: IntProperty(name="Islas", default=0)
    welded_vertices: IntProperty(name="Vértices fundidos", default=0)

    is_watertight: BoolProperty(name="Cerrada", default=False)
    is_manifold: BoolProperty(name="Manifold", default=False)
    has_volume: BoolProperty(name="Con volumen", default=False)
    is_solid: BoolProperty(name="Sólido", default=False)
    normals_flipped: BoolProperty(name="Normales invertidas", default=False)

    fits_in_printer: BoolProperty(name="Cabe entera", default=False)
    pieces_x: IntProperty(name="Piezas X", default=0)
    pieces_y: IntProperty(name="Piezas Y", default=0)
    pieces_z: IntProperty(name="Piezas Z", default=0)
    pieces_total: IntProperty(name="Piezas estimadas", default=0)

    # Mensajes serializados: Blender no admite listas de cadenas en un
    # PropertyGroup sin crear una colección entera, y para mostrarlos basta.
    messages: StringProperty(name="Mensajes", default="")

    def message_list(self):
        return [m for m in self.messages.split("\n") if m]


class BigPrintCutResult(PropertyGroup):
    """Resultado del último corte, para poder verificarlo desde el panel."""

    has_data: BoolProperty(name="Cortado", default=False)
    source_name: StringProperty(name="Modelo de origen", default="")
    piece_count: IntProperty(name="Piezas", default=0)

    volume_source_cm3: FloatProperty(name="Volumen original (cm³)", default=0.0)
    volume_pieces_cm3: FloatProperty(name="Volumen de las piezas (cm³)", default=0.0)
    volume_ok: BoolProperty(name="Volumen conservado", default=False)
    volume_error_pct: FloatProperty(name="Diferencia (%)", default=0.0)

    all_solid: BoolProperty(name="Todas cerradas", default=False)
    all_fit: BoolProperty(name="Todas caben", default=False)

    # Una línea por pieza: "nombre|volumen cm³|sólida|cabe"
    details: StringProperty(name="Detalle", default="")

    # Planos usados, una línea por corte: "eje,posición_mm".
    # Se guardan porque los conectores van justo en esas caras y recalcularlos
    # desde el plan no valdría para un corte manual.
    planes: StringProperty(name="Planos de corte", default="")

    def plane_list(self):
        """Planos del último corte (`planes.Plane`), de eje o inclinados."""
        from ..core.planes import Plane

        salida = []
        for linea in self.planes.split("\n"):
            if linea.strip():
                salida.append(Plane.parse(linea))
        return salida

    def piece_rows(self):
        filas = []
        for linea in self.details.split("\n"):
            if not linea:
                continue
            partes = linea.split("|")
            if len(partes) == 4:
                filas.append(
                    (partes[0], float(partes[1]), partes[2] == "1", partes[3] == "1")
                )
        return filas


class BigPrintConnectorResult(PropertyGroup):
    """Resumen del último cálculo de conectores."""

    has_data: BoolProperty(name="Calculado", default=False)
    total: IntProperty(name="Conectores", default=0)
    planes_done: IntProperty(name="Caras resueltas", default=0)
    planes_failed: IntProperty(name="Caras sin sitio", default=0)
    details: StringProperty(name="Detalle", default="")
    applied: BoolProperty(name="Perforado", default=False)
    dowel_count: IntProperty(name="Varillas necesarias", default=0)
    removed_cm3: FloatProperty(name="Material retirado (cm³)", default=0.0)
    depth_warning: StringProperty(name="Aviso de profundidad", default="")
    suggestion: StringProperty(name="Medida que sí cabe", default="")

    def lines(self):
        return [l for l in self.details.split("\n") if l]


class BigPrintSettings(PropertyGroup):
    """Ajustes del complemento, guardados con el .blend."""

    source_object: PointerProperty(
        name="Modelo",
        description="Objeto de malla que se va a analizar y, más adelante, cortar",
        type=bpy.types.Object,
        poll=_mesh_object_poll,
    )

    profile_id: EnumProperty(
        name="Impresora",
        description="Perfil de volumen de impresión",
        items=_profile_items,
        default=0,
    )

    custom_size_x: FloatProperty(
        name="X", description="Ancho de la cama en mm", default=256.0, min=1.0, soft_max=1000.0
    )
    custom_size_y: FloatProperty(
        name="Y", description="Fondo de la cama en mm", default=256.0, min=1.0, soft_max=1000.0
    )
    custom_size_z: FloatProperty(
        name="Z", description="Altura útil en mm", default=256.0, min=1.0, soft_max=1000.0
    )
    custom_margin: FloatProperty(
        name="Margen",
        description="Margen de seguridad por lado, en mm",
        default=10.0,
        min=0.0,
        soft_max=50.0,
    )

    model_unit: EnumProperty(
        name="Unidad del modelo",
        description="Cómo interpretar las unidades de Blender de este modelo",
        items=_UNIT_ITEMS,
        default=un.AUTO,
    )

    apply_modifiers: BoolProperty(
        name="Aplicar modificadores",
        description="Analizar la malla evaluada (con modificadores) sin tocar el original",
        default=True,
    )

    allow_rotation: BoolProperty(
        name="Permitir rotar",
        description="Considerar giros de 90° al comprobar si la pieza cabe",
        default=True,
    )

    weld_for_analysis: BoolProperty(
        name="Soldar al analizar",
        description=(
            "Fundir vértices coincidentes en la copia de trabajo. Imprescindible "
            "con STL, que repite los vértices en cada triángulo. Solo se aplica si "
            "la malla llega abierta y si soldar de verdad la arregla"
        ),
        default=True,
    )

    weld_tolerance: FloatProperty(
        name="Tolerancia de soldado",
        description="Distancia máxima entre vértices para fundirlos, en mm",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        precision=4,
    )

    analysis: PointerProperty(type=BigPrintAnalysis)
    cut_result: PointerProperty(type=BigPrintCutResult)
    connector_result: PointerProperty(type=BigPrintConnectorResult)

    connector_kind: EnumProperty(
        name="Conector",
        description="Qué poner en las caras de corte",
        items=[
            ("DOWEL", "Dowel", "Agujero en las dos piezas para una varilla suelta"),
            ("MAGNET", "Imán", "Alojamiento para imán de disco de neodimio"),
            ("BOTH", "Dowel + imán", "Dowels para la resistencia, imanes para el montaje"),
        ],
        default="DOWEL",
    )

    magnet_size: EnumProperty(
        name="Imán",
        description="Medida del imán de disco",
        items=[
            (f"{d:g}x{t:g}", f"⌀{d:g} × {t:g} mm", f"Imán de disco de {d:g} por {t:g} mm")
            for d, t in _MAGNET_SIZES
        ],
        default="6x3",
    )

    dowel_size: EnumProperty(
        name="Dowel",
        description="Diámetro y longitud de la varilla",
        items=[
            (
                f"{d:g}x{l:g}",
                f"⌀{d:g} × {l:g} mm",
                "Filamento de 1,75" if d == 1.75 else f"Varilla de {d:g} mm",
            )
            for d, l in _DOWEL_SIZES
        ],
        default="3x20",
    )

    nozzle: EnumProperty(
        name="Boquilla",
        description="Boquilla de tu impresora: decide la pared mínima alrededor de imanes y dowels",
        items=[("0.25", "0.25", "Boquilla de 0,25 mm"), ("0.4", "0.4", "Boquilla de 0,4 mm"),
               ("0.6", "0.6", "Boquilla de 0,6 mm"), ("0.8", "0.8", "Boquilla de 0,8 mm")],
        default="0.4",
    )

    wall_mm: FloatProperty(
        name="Pared alrededor (mm)",
        description="Material mínimo entre el agujero y el borde de la pieza. 0 = según la boquilla (unos 2,5 perímetros)",
        default=0.0,
        min=0.0,
        soft_max=4.0,
        precision=2,
    )

    line_points: StringProperty(name="Puntos de la línea", default="")
    line_report: StringProperty(name="Línea de corte", default="")
    show_axis_cut: BoolProperty(name="Corte por eje (avanzado)", default=False)

    connector_max: IntProperty(
        name="Máximo por cara",
        description="Tope de conectores en cada cara de corte",
        default=4,
        min=1,
        max=8,
    )

    explode_factor: FloatProperty(
        name="Despiece",
        description="Separa las piezas para verlas todas; 0 las deja montadas",
        default=0.0,
        min=0.0,
        soft_max=2.0,
        update=_on_explode_changed,
    )

    label_height: FloatProperty(
        name="Altura del número",
        description="Altura de los dígitos en mm; se reduce sola si no cabe",
        default=10.0,
        min=2.0,
        soft_max=40.0,
    )

    label_depth: FloatProperty(
        name="Profundidad",
        description="Cuánto se hunde el número, en mm",
        default=0.6,
        min=0.2,
        soft_max=2.0,
        precision=2,
    )

    label_report: StringProperty(name="Numeración", default="")

    export_dir: StringProperty(
        name="Carpeta",
        description="Dónde se escriben los STL y la lista de piezas",
        default="//piezas/",
        subtype="DIR_PATH",
    )

    export_dowels: BoolProperty(
        name="Varillas (STL)",
        description="Generar también las varillas imprimibles de los dowels",
        default=True,
    )

    dowel_fit_gap: FloatProperty(
        name="Rebaja de la varilla",
        description=(
            "Cuánto más fina se imprime la varilla que el agujero, en mm de "
            "diámetro. Ajústalo tras la primera prueba con el calibre"
        ),
        default=0.15,
        min=0.0,
        soft_max=0.6,
        precision=2,
    )

    export_list: BoolProperty(
        name="Lista de piezas (CSV)",
        description="Escribir también piezas.csv con dimensiones y volúmenes",
        default=True,
    )

    export_report: StringProperty(name="Último export", default="")

    connector_preview: PointerProperty(
        name="Vista previa de conectores",
        type=bpy.types.Object,
    )

    cut_axis: EnumProperty(
        name="Eje de corte",
        description="Eje perpendicular al plano de corte",
        items=_AXIS_ITEMS,
        default="X",
        update=_on_axis_changed,
    )

    cut_position: FloatProperty(
        name="Posición",
        description="Posición del plano a lo largo del eje, en mm",
        default=0.0,
        soft_min=-1000.0,
        soft_max=1000.0,
        unit="NONE",
        update=_on_cut_changed,
    )

    cut_plane: PointerProperty(
        name="Plano de corte",
        description="Objeto guía que representa el plano (se crea y borra desde el panel)",
        type=bpy.types.Object,
    )

    def resolve_magnet(self):
        d, t = (float(v) for v in self.magnet_size.split("x"))
        from ..core import connectors as cn

        return cn.magnet(d, t, wall=self.resolved_wall())

    def resolve_dowel(self):
        d, l = (float(v) for v in self.dowel_size.split("x"))
        from ..core import connectors as cn

        return cn.dowel(d, l, wall=self.resolved_wall())

    def resolved_wall(self) -> float:
        """Pared mínima en mm: la escrita a mano o la de la boquilla."""
        from ..core import connectors as cn

        return self.wall_mm if self.wall_mm > 0 else cn.wall_from_nozzle(float(self.nozzle))

    def line_point_list(self):
        salida = []
        for linea in self.line_points.split(";"):
            if linea.strip():
                salida.append(tuple(float(v) for v in linea.split(",")))
        return salida

    def resolve_profile(self):
        """Devuelve el PrinterProfile activo, incluido el personalizado."""
        if self.profile_id == pp.CUSTOM_ID:
            return pp.make_custom_profile(
                self.custom_size_x, self.custom_size_y, self.custom_size_z, self.custom_margin
            )
        return pp.get_profile(self.profile_id)


CLASSES = (
    BigPrintAnalysis,
    BigPrintCutResult,
    BigPrintConnectorResult,
    BigPrintSettings,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bigprint = PointerProperty(type=BigPrintSettings)


def unregister():
    if hasattr(bpy.types.Scene, "bigprint"):
        del bpy.types.Scene.bigprint
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
