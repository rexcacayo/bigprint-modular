"""Tests de la capa de Blender usando el doble de pruebas `fake_bpy`.

Comprueban lo que se puede comprobar sin Blender: que el paquete importa, que
el registro y el desregistro son simétricos, que los identificadores están bien
puestos y que el informe del núcleo se vuelca correctamente en las propiedades.
"""

from __future__ import annotations

import unittest

import _context  # noqa: F401
import fake_bpy


class AddonTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_bpy.install()
        import bigprint_modular

        cls.addon = bigprint_modular

    @classmethod
    def tearDownClass(cls):
        import sys

        for nombre in list(sys.modules):
            if nombre.startswith("bigprint_modular"):
                del sys.modules[nombre]
        fake_bpy.uninstall()


class TestMetadata(AddonTestCase):
    def test_bl_info(self):
        info = self.addon.bl_info
        self.assertEqual(info["name"], "BigPrint Modular")
        self.assertEqual(info["version"], (0, 10, 0))
        self.assertIn("blender", info)
        self.assertIn("category", info)

    def test_core_does_not_import_bpy(self):
        import inspect

        from bigprint_modular import core

        for modulo in (
            core.geometry,
            core.units,
            core.printer_profiles,
            core.mesh_analysis,
        ):
            fuente = inspect.getsource(modulo)
            self.assertNotIn("import bpy", fuente, f"{modulo.__name__} importa bpy")
            self.assertNotIn("import bmesh", fuente, f"{modulo.__name__} importa bmesh")


class TestAnnotationsAreReal(AddonTestCase):
    """Regresión: PEP 563 dejaría las propiedades como cadenas y Blender no las registraría."""

    def test_no_future_annotations_in_blender_layer(self):
        import __future__

        from bigprint_modular.blender import (
            example_model,
            mesh_bridge,
            operators,
            panels,
            properties,
        )

        for modulo in (properties, operators, panels, mesh_bridge, example_model):
            # Si el módulo activó PEP 563, su espacio de nombres contiene la
            # feature de __future__ bajo el nombre "annotations".
            activo = modulo.__dict__.get("annotations") is __future__.annotations
            self.assertFalse(
                activo,
                f"{modulo.__name__} usa PEP 563: rompería el registro de propiedades",
            )

    def test_property_annotations_are_objects_not_strings(self):
        from bigprint_modular.blender.properties import BigPrintAnalysis, BigPrintSettings

        for cls in (BigPrintSettings, BigPrintAnalysis):
            anotaciones = cls.__annotations__
            self.assertTrue(anotaciones, f"{cls.__name__} sin propiedades")
            for nombre, valor in anotaciones.items():
                self.assertNotIsInstance(
                    valor, str, f"{cls.__name__}.{nombre} quedó como cadena"
                )


class TestRegistration(AddonTestCase):
    def test_register_unregister_are_symmetric(self):
        self.addon.register()
        self.assertGreater(len(fake_bpy.REGISTERED), 0)
        registradas = list(fake_bpy.REGISTERED)
        nombres = [c.__name__ for c in registradas]
        self.assertIn("BigPrintSettings", nombres)
        self.assertIn("BIGPRINT_OT_analyze", nombres)
        self.assertIn("VIEW3D_PT_bigprint_main", nombres)

        self.addon.unregister()
        self.assertEqual(fake_bpy.REGISTERED, [])

    def test_double_cycle(self):
        # Activar y desactivar el complemento dos veces no debe romper nada
        for _ in range(2):
            self.addon.register()
            self.addon.unregister()
        self.assertEqual(fake_bpy.REGISTERED, [])

    def test_scene_property_removed_on_unregister(self):
        import bpy

        self.addon.register()
        self.assertTrue(hasattr(bpy.types.Scene, "bigprint"))
        self.addon.unregister()
        self.assertFalse(hasattr(bpy.types.Scene, "bigprint"))


class TestOperatorsAndPanels(AddonTestCase):
    def test_operator_ids(self):
        from bigprint_modular.blender import operators

        esperados = {
            "bigprint.import_model",
            "bigprint.use_active",
            "bigprint.analyze",
            "bigprint.clear_analysis",
            "bigprint.load_example",
            "bigprint.add_cut_plane",
            "bigprint.center_cut_plane",
            "bigprint.remove_cut_plane",
            "bigprint.split_in_two",
            "bigprint.split_grid",
            "bigprint.remove_pieces",
            "bigprint.preview_connectors",
            "bigprint.clear_connectors",
            "bigprint.apply_connectors",
            "bigprint.export_pieces",
            "bigprint.number_pieces",
            "bigprint.assemble",
            "bigprint.toggle_original",
        }
        self.assertEqual({c.bl_idname for c in operators.CLASSES}, esperados)

    def test_operators_have_labels_and_docstrings(self):
        from bigprint_modular.blender import operators

        for cls in operators.CLASSES:
            self.assertTrue(cls.bl_label, cls.__name__)
            self.assertTrue(cls.__doc__, f"{cls.__name__} sin docstring (es el tooltip)")

    def test_panels_are_in_the_bigprint_category(self):
        from bigprint_modular.blender import panels

        for cls in panels.CLASSES:
            self.assertEqual(cls.bl_space_type, "VIEW_3D")
            self.assertEqual(cls.bl_region_type, "UI")
            self.assertEqual(cls.bl_category, "BigPrint")

    def test_subpanels_point_to_the_main_panel(self):
        from bigprint_modular.blender import panels

        hijos = [c for c in panels.CLASSES if hasattr(c, "bl_parent_id")]
        self.assertEqual(len(hijos), 6)
        for cls in hijos:
            self.assertEqual(cls.bl_parent_id, panels.VIEW3D_PT_bigprint_main.bl_idname)


class TestSettings(AddonTestCase):
    def test_default_profile_is_the_256(self):
        from bigprint_modular.blender.properties import BigPrintSettings

        settings = BigPrintSettings()
        self.assertEqual(settings.profile_id, "GENERIC_256")
        profile = settings.resolve_profile()
        self.assertEqual(profile.usable, (236.0, 236.0, 236.0))

    def test_custom_profile_uses_the_custom_fields(self):
        from bigprint_modular.blender.properties import BigPrintSettings

        settings = BigPrintSettings()
        settings.profile_id = "CUSTOM"
        settings.custom_size_x = 300.0
        settings.custom_size_y = 300.0
        settings.custom_size_z = 400.0
        settings.custom_margin = 0.0
        self.assertEqual(settings.resolve_profile().usable, (300.0, 300.0, 400.0))

    def test_weld_defaults_are_safe_for_stl(self):
        from bigprint_modular.blender.properties import BigPrintSettings

        settings = BigPrintSettings()
        self.assertTrue(settings.weld_for_analysis)
        self.assertGreater(settings.weld_tolerance, 0.0)
        self.assertLess(settings.weld_tolerance, 0.1)

    def test_cut_settings_exist(self):
        from bigprint_modular.blender.properties import BigPrintSettings

        settings = BigPrintSettings()
        self.assertEqual(settings.cut_axis, "X")
        self.assertEqual(settings.cut_position, 0.0)
        self.assertIsNone(settings.cut_plane)

    def test_analysis_cache_starts_empty(self):
        from bigprint_modular.blender.properties import BigPrintSettings

        settings = BigPrintSettings()
        self.assertFalse(settings.analysis.has_data)
        self.assertEqual(settings.analysis.message_list(), [])


class TestReportStorage(AddonTestCase):
    """El volcado informe -> propiedades es donde más fácil se cuela un error."""

    def test_store_roundtrip(self):
        from bigprint_modular.blender.operators import BIGPRINT_OT_analyze
        from bigprint_modular.blender.properties import BigPrintSettings
        from bigprint_modular.core import check_fit, get_profile
        from bigprint_modular.core.mesh_analysis import analyze_mesh
        from bigprint_modular.core.sample_shapes import l_bracket

        settings = BigPrintSettings()
        report = analyze_mesh(l_bracket(), unit_factor=1.0, unit="MM")
        profile = get_profile("GENERIC_256")
        fit = check_fit(report.dimensions_mm, profile)

        BIGPRINT_OT_analyze._store(settings.analysis, report, fit, "MM", 1.0)

        cache = settings.analysis
        self.assertTrue(cache.has_data)
        self.assertEqual(cache.status, "OK")
        self.assertAlmostEqual(cache.dim_x, 420.0)
        self.assertAlmostEqual(cache.dim_z, 260.0)
        self.assertAlmostEqual(cache.volume_cm3, 8856.0, places=2)
        self.assertTrue(cache.is_solid)
        self.assertFalse(cache.fits_in_printer)
        self.assertEqual(cache.pieces_total, 4)
        self.assertEqual((cache.pieces_x, cache.pieces_y, cache.pieces_z), (2, 1, 2))
        # Una malla sana no genera errores ni avisos: la caja de avisos queda vacía
        self.assertEqual(cache.message_list(), [])
        self.assertAlmostEqual(cache.bbox_max_x, 420.0)
        self.assertAlmostEqual(cache.bbox_min_z, 0.0)


class TestImportDispatch(AddonTestCase):
    def test_modern_blender_uses_wm_stl_import(self):
        from bigprint_modular.blender.operators import _import_mesh_file

        self.assertTrue(_import_mesh_file("/tmp/pieza.stl"))
        self.assertTrue(_import_mesh_file("/tmp/pieza.OBJ"))
        self.assertFalse(_import_mesh_file("/tmp/pieza.3mf"))

    def test_legacy_blender_falls_back(self):
        import sys

        for nombre in list(sys.modules):
            if nombre.startswith("bigprint_modular"):
                del sys.modules[nombre]
        fake_bpy.uninstall()
        fake_bpy.install(stl_import_modern=False)
        try:
            from bigprint_modular.blender.operators import _import_mesh_file

            self.assertTrue(_import_mesh_file("/tmp/pieza.stl"))
            self.assertTrue(_import_mesh_file("/tmp/pieza.ply"))
        finally:
            for nombre in list(sys.modules):
                if nombre.startswith("bigprint_modular"):
                    del sys.modules[nombre]
            fake_bpy.uninstall()
            fake_bpy.install()


if __name__ == "__main__":
    unittest.main()
