"""Exportación de las piezas a STL, una por fichero.

La malla se lee igual que para el análisis (evaluada, en coordenadas de mundo)
y se escala a milímetros antes de escribir: el STL sale siempre en mm, que es
lo que espera el laminador, sin depender de las unidades de la escena.
"""

import os

import bpy

from ..core import dowels as core_dowels
from ..core import parts_list, stl_io
from ..core.mesh_analysis import analyze_mesh
from ..core.printer_profiles import check_fit
from . import mesh_bridge

LIST_FILENAME = "piezas.csv"


class ExportError(RuntimeError):
    pass


def export_pieces(context, piezas, directorio, factor=1.0, profile=None, allow_rotation=True):
    """Escribe un STL por pieza y devuelve las filas de la lista."""
    destino = bpy.path.abspath(directorio)
    if not destino:
        raise ExportError("No se ha indicado carpeta de destino")
    if not os.path.isdir(destino):
        try:
            os.makedirs(destino, exist_ok=True)
        except OSError as exc:
            raise ExportError(f"No se puede crear la carpeta: {exc}")

    filas = []
    for indice, pieza in enumerate(sorted(piezas, key=lambda o: o.name), start=1):
        malla = mesh_bridge.mesh_data_from_object(pieza).scaled(factor)
        informe = analyze_mesh(malla, weld_tolerance=0.01)

        cabe = True
        if profile is not None:
            cabe = check_fit(informe.dimensions_mm, profile, allow_rotation).fits

        nombre = stl_io.safe_filename(pieza.name)
        ruta = os.path.join(destino, f"{nombre}.stl")
        stl_io.write_binary_stl(malla, ruta)

        filas.append(
            parts_list.PartRow(
                index=indice,
                name=pieza.name,
                filename=f"{nombre}.stl",
                dimensions_mm=informe.dimensions_mm,
                volume_cm3=informe.volume_cm3,
                watertight=informe.is_watertight,
                fits=cabe,
            )
        )

    return filas


def write_parts_list(filas, directorio):
    destino = bpy.path.abspath(directorio)
    ruta = os.path.join(destino, LIST_FILENAME)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        # utf-8 con BOM: sin él, Excel se come los acentos de la cabecera
        f.write(parts_list.csv_text(filas))
    return ruta


def export_dowels(directorio, spec, count, fit_gap=core_dowels.DEFAULT_FIT_GAP):
    """Escribe un STL con todas las varillas en fila y devuelve (ruta, fila).

    Van juntas en un solo fichero porque se imprimen de una tirada: separarlas
    en un STL por varilla solo daría trabajo en el laminador.
    """
    if count < 1:
        raise ExportError("No hay varillas que generar")

    destino = bpy.path.abspath(directorio)
    diametro = core_dowels.printed_diameter(spec, fit_gap)
    largo = core_dowels.dowel_length(spec)
    malla = core_dowels.dowel_batch(count, diametro, largo)

    nombre = core_dowels.batch_filename(spec, count, fit_gap)
    ruta = os.path.join(destino, nombre)
    stl_io.write_binary_stl(malla, ruta)

    caja = malla.bbox()
    informe = analyze_mesh(malla)
    fila = parts_list.PartRow(
        index=0,
        name="varillas",
        filename=nombre,
        dimensions_mm=caja.size,
        volume_cm3=informe.volume_cm3,
        watertight=informe.is_watertight,
        fits=True,
        connectors=count,
        kind=parts_list.HARDWARE,
    )
    return ruta, fila
