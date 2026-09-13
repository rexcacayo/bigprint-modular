"""Preparación de sys.path para los tests.

El núcleo se importa como paquete de primer nivel (`core`) para demostrar que
no necesita ni Blender ni el resto del complemento.
"""

import os
import sys

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(ADDON_DIR)

if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
