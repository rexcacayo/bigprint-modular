#!/usr/bin/env python3
"""Empaqueta la extensión lista para instalar en Blender.

    python3 tools_build_zip.py

El manifiesto tiene que quedar en la raíz del ZIP: si se mete dentro de una
carpeta, Blender 4.2+ no lo reconoce como extensión.
"""

import os
import re
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
EXCLUIR = {".git", ".github", "__pycache__", "dist", ".venv"}


def version():
    with open(os.path.join(RAIZ, "blender_manifest.toml"), encoding="utf-8") as f:
        encontrado = re.search(r'^version = "([^"]+)"', f.read(), re.M)
    return encontrado.group(1) if encontrado else "0.0.0"


def main():
    destino_dir = os.path.join(RAIZ, "dist")
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, f"bigprint_modular-{version()}.zip")

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for carpeta, subcarpetas, ficheros in os.walk(RAIZ):
            subcarpetas[:] = [d for d in subcarpetas if d not in EXCLUIR]
            for fichero in ficheros:
                if fichero.endswith((".pyc", ".zip")):
                    continue
                ruta = os.path.join(carpeta, fichero)
                relativa = os.path.relpath(ruta, RAIZ)
                if relativa.startswith("dist" + os.sep):
                    continue
                z.write(ruta, relativa)

    print(f"Escrito: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
