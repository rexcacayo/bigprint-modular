#!/usr/bin/env python3
"""Ejecuta toda la batería que no necesita Blender.

    python3 tests/run_tests.py

Para la verificación dentro de Blender:

    blender --background --python tests/test_in_blender.py
"""

import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

# test_in_blender.py necesita el intérprete de Blender: se excluye aquí a
# propósito, no se puede importar con python normal.
EXCLUIDOS = {"test_in_blender"}


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for fichero in sorted(os.listdir(AQUI)):
        if not (fichero.startswith("test_") and fichero.endswith(".py")):
            continue
        modulo = fichero[:-3]
        if modulo in EXCLUIDOS:
            continue
        suite.addTests(loader.loadTestsFromName(modulo))

    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
