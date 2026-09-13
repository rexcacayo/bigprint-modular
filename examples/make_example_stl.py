#!/usr/bin/env python3
"""Genera el STL de ejemplo: una escuadra de 420 × 180 × 260 mm.

    python3 examples/make_example_stl.py

Se genera por código en lugar de guardar un binario en el repositorio: así el
ejemplo es reproducible y los tests pueden usar exactamente el mismo sólido.

El escritor de STL que hay aquí es solo para el ejemplo; la exportación real
del complemento (Fase 5) la hará Blender.
"""

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from core.stl_io import write_binary_stl  # noqa: E402
from core.mesh_analysis import analyze_mesh  # noqa: E402
from core.printer_profiles import check_fit, get_profile  # noqa: E402
from core.sample_shapes import l_bracket  # noqa: E402

SALIDA = os.path.join(AQUI, "ejemplo_escuadra_420x180x260.stl")


def main() -> int:
    mesh = l_bracket()
    write_binary_stl(mesh, SALIDA)

    informe = analyze_mesh(mesh)
    perfil = get_profile("GENERIC_256")
    encaje = check_fit(informe.dimensions_mm, perfil)

    print(f"Escrito: {SALIDA}")
    print(f"  {informe.summary()}")
    print(f"  Triángulos: {informe.triangle_count}, islas: {informe.shell_count}")
    print(f"  Perfil: {perfil.label}, útil {perfil.usable[0]:g} mm")
    print(f"  ¿Cabe entera?: {'sí' if encaje.fits else 'no'}")
    if not encaje.fits:
        px, py, pz = encaje.pieces
        print(f"  Estimación de corte: {px} × {py} × {pz} = {encaje.total_pieces} piezas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
