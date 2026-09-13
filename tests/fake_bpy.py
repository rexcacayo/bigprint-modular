"""Doble de pruebas de bpy/bmesh/bpy_extras.

No pretende emular Blender: solo lo justo para importar y registrar el
complemento y para ejercitar el código que mueve datos entre el núcleo y las
propiedades. Sirve para detectar en CI los fallos tontos (nombres de clase,
orden de registro, propiedades mal declaradas) sin arrancar Blender.

La verificación de verdad sigue siendo tests/test_in_blender.py.
"""

from __future__ import annotations

import sys
import types


class _Prop:
    """Sustituto de una propiedad de Blender: solo guarda el valor por defecto."""

    def __init__(self, kind, **kwargs):
        self.kind = kind
        self.kwargs = kwargs
        self.default = kwargs.get("default", None)
        self.type = kwargs.get("type", None)
        self.items = kwargs.get("items", None)

    def resolve_default(self):
        if self.kind == "Pointer":
            tipo = self.type
            if isinstance(tipo, type) and issubclass(tipo, PropertyGroup):
                return tipo()
            return None
        if self.kind == "Enum":
            items = self.items
            if callable(items):
                items = items(None, None)
            if items and isinstance(self.default, int):
                return items[self.default][0]
            if self.default is None and items:
                return items[0][0]
            return self.default
        if self.kind == "Collection":
            return []
        if self.default is not None:
            return self.default
        return {"Bool": False, "Int": 0, "Float": 0.0, "String": ""}.get(self.kind)


def _prop_factory(kind):
    def factory(*args, **kwargs):
        return _Prop(kind, **kwargs)

    factory.__name__ = f"{kind}Property"
    return factory


class _StructRNA:
    pass


class PropertyGroup(_StructRNA):
    def __init__(self):
        for nombre, prop in getattr(type(self), "__annotations__", {}).items():
            if isinstance(prop, _Prop):
                setattr(self, nombre, prop.resolve_default())


class Operator(_StructRNA):
    pass


class Panel(_StructRNA):
    pass


class Object(_StructRNA):
    pass


class Scene(_StructRNA):
    pass


class Mesh(_StructRNA):
    pass


REGISTERED = []


def register_class(cls):
    if cls in REGISTERED:
        raise RuntimeError(f"Clase ya registrada: {cls.__name__}")
    if issubclass(cls, (Operator, Panel)) and not getattr(cls, "bl_idname", ""):
        raise RuntimeError(f"{cls.__name__} no define bl_idname")
    REGISTERED.append(cls)


def unregister_class(cls):
    if cls not in REGISTERED:
        raise RuntimeError(f"Clase no registrada: {cls.__name__}")
    REGISTERED.remove(cls)


class _OpsNamespace:
    """Espacio de nombres de operadores: hasattr solo es cierto si se declara."""

    def __init__(self, nombres=()):
        for n in nombres:
            setattr(self, n, lambda **kwargs: {"FINISHED"})


def install(stl_import_modern: bool = True):
    """Instala los módulos falsos en sys.modules y los devuelve."""
    bpy = types.ModuleType("bpy")

    bpy_types = types.ModuleType("bpy.types")
    for nombre, cls in (
        ("PropertyGroup", PropertyGroup),
        ("Operator", Operator),
        ("Panel", Panel),
        ("Object", Object),
        ("Scene", Scene),
        ("Mesh", Mesh),
    ):
        setattr(bpy_types, nombre, cls)

    bpy_props = types.ModuleType("bpy.props")
    for kind in ("Bool", "Int", "Float", "String", "Enum", "Pointer", "Collection", "FloatVector"):
        setattr(bpy_props, f"{kind}Property", _prop_factory(kind))

    bpy_utils = types.ModuleType("bpy.utils")
    bpy_utils.register_class = register_class
    bpy_utils.unregister_class = unregister_class

    bpy_ops = types.ModuleType("bpy.ops")
    bpy_ops.wm = _OpsNamespace(("stl_import", "obj_import", "ply_import") if stl_import_modern else ())
    bpy_ops.import_mesh = _OpsNamespace(() if stl_import_modern else ("stl", "ply"))
    bpy_ops.import_scene = _OpsNamespace(() if stl_import_modern else ("obj",))

    bpy.types = bpy_types
    bpy.props = bpy_props
    bpy.utils = bpy_utils
    bpy.ops = bpy_ops
    bpy.data = types.SimpleNamespace()
    bpy.context = types.SimpleNamespace()
    bpy.app = types.SimpleNamespace(version=(4, 2, 0))

    bmesh = types.ModuleType("bmesh")
    bmesh.ops = types.SimpleNamespace(triangulate=lambda *a, **k: None)
    bmesh.new = lambda: None
    bmesh.types = types.SimpleNamespace(BMVert=object, BMesh=object)

    mathutils = types.ModuleType("mathutils")

    class Vector(tuple):
        def __new__(cls, valores=(0.0, 0.0, 0.0)):
            return super().__new__(cls, tuple(valores))

        @property
        def x(self):
            return self[0]

        @property
        def y(self):
            return self[1]

        @property
        def z(self):
            return self[2]

    mathutils.Vector = Vector

    bpy_extras = types.ModuleType("bpy_extras")
    io_utils = types.ModuleType("bpy_extras.io_utils")

    class ImportHelper:
        filepath = ""

    io_utils.ImportHelper = ImportHelper
    bpy_extras.io_utils = io_utils

    sys.modules.update(
        {
            "bpy": bpy,
            "bpy.types": bpy_types,
            "bpy.props": bpy_props,
            "bpy.utils": bpy_utils,
            "bpy.ops": bpy_ops,
            "bmesh": bmesh,
            "mathutils": mathutils,
            "bpy_extras": bpy_extras,
            "bpy_extras.io_utils": io_utils,
        }
    )
    return bpy


def uninstall():
    for nombre in list(sys.modules):
        if nombre == "bpy" or nombre.startswith("bpy.") or nombre in ("bmesh", "bpy_extras", "mathutils"):
            del sys.modules[nombre]
        elif nombre.startswith("bpy_extras."):
            del sys.modules[nombre]
    REGISTERED.clear()
