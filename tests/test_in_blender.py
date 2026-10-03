"""Verificación dentro de Blender (lo que el arnés falso no puede probar).

    blender --background --python tests/test_in_blender.py

Sale con código 0 si todo pasa y 1 si algo falla, para poder encadenarlo en CI.
Comprueba lo que solo existe con Blender de verdad: registro real de clases y
propiedades, lectura de la malla con bmesh, evaluación de modificadores y —lo
más importante— que el objeto original queda intacto tras analizarlo.
"""

import os
import struct
import sys
import tempfile
import unittest

import bpy

# El complemento se importa desde la carpeta padre, no hace falta instalarlo
AQUI = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(AQUI)
sys.path.insert(0, os.path.dirname(ADDON_DIR))

import bigprint_modular  # noqa: E402
from bigprint_modular.blender import cutting, mesh_bridge  # noqa: E402
from bigprint_modular.core.mesh_analysis import analyze_mesh  # noqa: E402


def limpiar_escena():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class BlenderTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        limpiar_escena()
        bigprint_modular.register()

    @classmethod
    def tearDownClass(cls):
        bigprint_modular.unregister()


class TestRegistro(BlenderTestCase):
    def test_propiedad_de_escena(self):
        self.assertTrue(hasattr(bpy.context.scene, "bigprint"))
        settings = bpy.context.scene.bigprint
        self.assertEqual(settings.profile_id, "GENERIC_256")
        self.assertEqual(settings.resolve_profile().usable, (236.0, 236.0, 236.0))

    def test_operadores_disponibles(self):
        for nombre in (
            "import_model",
            "use_active",
            "analyze",
            "clear_analysis",
            "load_example",
        ):
            self.assertTrue(hasattr(bpy.ops.bigprint, nombre), nombre)

    def test_paneles_registrados(self):
        self.assertTrue(hasattr(bpy.types, "VIEW3D_PT_bigprint_main"))
        self.assertTrue(hasattr(bpy.types, "VIEW3D_PT_bigprint_analysis"))


class TestCuboReal(BlenderTestCase):
    def setUp(self):
        limpiar_escena()
        bpy.ops.mesh.primitive_cube_add(size=2.0)  # 2 × 2 × 2 unidades
        self.obj = bpy.context.active_object
        bpy.context.scene.bigprint.source_object = self.obj

    def test_lectura_de_malla(self):
        malla = mesh_bridge.mesh_data_from_object(self.obj)
        self.assertEqual(malla.source_vertex_count, 8)
        self.assertEqual(malla.source_polygon_count, 6)
        self.assertEqual(len(malla.triangles), 12)
        informe = analyze_mesh(malla)
        self.assertTrue(informe.is_solid)
        self.assertAlmostEqual(informe.volume_mm3, 8.0, places=4)

    def test_la_escala_del_objeto_cuenta(self):
        self.obj.scale = (10.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        malla = mesh_bridge.mesh_data_from_object(self.obj)
        self.assertAlmostEqual(malla.bbox().size[0], 20.0, places=4)

    def test_modificador_evaluado_sin_aplicarlo(self):
        mod = self.obj.modifiers.new("Espejo", "MIRROR")
        mod.use_axis = (True, False, False)
        self.obj.location = (2.0, 0.0, 0.0)
        bpy.context.view_layer.update()

        evaluada = mesh_bridge.mesh_data_from_object(self.obj, apply_modifiers=True)
        cruda = mesh_bridge.mesh_data_from_object(self.obj, apply_modifiers=False)
        self.assertGreater(evaluada.source_vertex_count, cruda.source_vertex_count)
        # El modificador sigue en la pila: no se ha aplicado nada
        self.assertEqual(len(self.obj.modifiers), 1)

    def test_el_original_no_se_toca(self):
        antes = (
            len(self.obj.data.vertices),
            len(self.obj.data.edges),
            len(self.obj.data.polygons),
            tuple(tuple(v.co) for v in self.obj.data.vertices),
            tuple(self.obj.scale),
            tuple(self.obj.location),
        )
        bpy.ops.bigprint.analyze()
        despues = (
            len(self.obj.data.vertices),
            len(self.obj.data.edges),
            len(self.obj.data.polygons),
            tuple(tuple(v.co) for v in self.obj.data.vertices),
            tuple(self.obj.scale),
            tuple(self.obj.location),
        )
        self.assertEqual(antes, despues, "¡El operador ha modificado el modelo original!")


class TestOperadorAnalizar(BlenderTestCase):
    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        self.settings = bpy.context.scene.bigprint

    def test_ejemplo_creado(self):
        obj = self.settings.source_object
        self.assertIsNotNone(obj)
        self.assertAlmostEqual(obj.dimensions.x, 420.0, places=3)
        self.assertAlmostEqual(obj.dimensions.y, 180.0, places=3)
        self.assertAlmostEqual(obj.dimensions.z, 260.0, places=3)

    def test_analisis_completo(self):
        resultado = bpy.ops.bigprint.analyze()
        self.assertEqual(resultado, {"FINISHED"})

        datos = self.settings.analysis
        self.assertTrue(datos.has_data)
        self.assertEqual(datos.status, "OK")
        self.assertAlmostEqual(datos.dim_x, 420.0, places=2)
        self.assertAlmostEqual(datos.dim_z, 260.0, places=2)
        self.assertAlmostEqual(datos.volume_cm3, 8856.0, delta=1.0)
        self.assertTrue(datos.is_watertight)
        self.assertTrue(datos.is_solid)
        self.assertFalse(datos.fits_in_printer)
        self.assertEqual(datos.pieces_total, 4)

    def test_limpiar_analisis(self):
        bpy.ops.bigprint.analyze()
        bpy.ops.bigprint.clear_analysis()
        self.assertFalse(self.settings.analysis.has_data)

    def test_malla_abierta_detectada(self):
        obj = self.settings.source_object
        # Se borra una cara del ejemplo para abrir la malla a propósito
        import bmesh

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY")
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

        # El operador debe terminar bien: una malla rota es un diagnóstico,
        # no un fallo de ejecución (si reportase {'ERROR'}, esto lanzaría)
        resultado = bpy.ops.bigprint.analyze()
        self.assertEqual(resultado, {"FINISHED"})

        datos = self.settings.analysis
        self.assertFalse(datos.is_watertight)
        self.assertFalse(datos.is_solid)
        self.assertEqual(datos.status, "ERROR")
        self.assertGreater(datos.boundary_edges, 0)


class TestImportarStl(BlenderTestCase):
    def test_importar_el_ejemplo(self):
        ruta = os.path.join(ADDON_DIR, "examples", "ejemplo_escuadra_420x180x260.stl")
        if not os.path.exists(ruta):
            self.skipTest("Falta el STL de ejemplo: ejecuta examples/make_example_stl.py")

        limpiar_escena()
        bpy.ops.bigprint.import_model(filepath=ruta)
        settings = bpy.context.scene.bigprint
        self.assertIsNotNone(settings.source_object)

        bpy.ops.bigprint.analyze()
        datos = settings.analysis
        self.assertAlmostEqual(datos.dim_x, 420.0, places=1)
        # Aquí se valida el soldado: un STL sin fundir vértices daría malla abierta
        self.assertTrue(datos.is_watertight, "El STL importado debería cerrarse al soldar")
        self.assertAlmostEqual(datos.volume_cm3, 8856.0, delta=5.0)


class TestPlanoDeCorte(BlenderTestCase):
    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint

    def test_crear_plano(self):
        self.assertEqual(bpy.ops.bigprint.add_cut_plane(), {"FINISHED"})
        plano = self.settings.cut_plane
        self.assertIsNotNone(plano)
        # La escuadra se pasa mucho más en X (184 mm) que en Z (24 mm)
        self.assertEqual(self.settings.cut_axis, "X")
        self.assertAlmostEqual(self.settings.cut_position, 210.0, places=2)
        self.assertAlmostEqual(plano.location.x, 210.0, places=2)
        self.assertAlmostEqual(plano.location.y, 90.0, places=2)

    def test_el_plano_atraviesa_la_pieza(self):
        from mathutils import Vector

        bpy.ops.bigprint.add_cut_plane()
        plano = self.settings.cut_plane

        # obj.dimensions es la caja LOCAL por la escala: ignora la rotación y
        # en un plano siempre da 0 en su Z local. Hay que medir en mundo.
        esquinas = [plano.matrix_world @ Vector(c) for c in plano.bound_box]
        xs = [c.x for c in esquinas]
        ys = [c.y for c in esquinas]
        zs = [c.z for c in esquinas]

        # Perpendicular a X: sin espesor en X, y sobresale un 20 % en Y y Z
        self.assertLess(max(xs) - min(xs), 1e-3)
        self.assertGreater(max(ys) - min(ys), 180.0)
        self.assertGreater(max(zs) - min(zs), 260.0)

    def test_mover_el_deslizador_mueve_el_plano(self):
        bpy.ops.bigprint.add_cut_plane()
        self.settings.cut_position = 120.0
        self.assertAlmostEqual(self.settings.cut_plane.location.x, 120.0, places=2)

    def test_cambiar_de_eje_recentra(self):
        bpy.ops.bigprint.add_cut_plane()
        self.settings.cut_axis = "Z"
        self.assertAlmostEqual(self.settings.cut_position, 130.0, places=2)
        self.assertAlmostEqual(self.settings.cut_plane.location.z, 130.0, places=2)

    def test_centrar(self):
        bpy.ops.bigprint.add_cut_plane()
        self.settings.cut_position = 50.0
        bpy.ops.bigprint.center_cut_plane()
        self.assertAlmostEqual(self.settings.cut_position, 210.0, places=2)

    def test_el_modelo_no_se_toca_al_poner_el_plano(self):
        obj = self.settings.source_object
        antes = (len(obj.data.vertices), tuple(obj.location), tuple(obj.scale))
        bpy.ops.bigprint.add_cut_plane()
        self.settings.cut_position = 90.0
        despues = (len(obj.data.vertices), tuple(obj.location), tuple(obj.scale))
        self.assertEqual(antes, despues)

    def test_quitar_plano(self):
        bpy.ops.bigprint.add_cut_plane()
        self.assertEqual(bpy.ops.bigprint.remove_cut_plane(), {"FINISHED"})
        self.assertIsNone(self.settings.cut_plane)
        self.assertNotIn("BigPrint_Plano_Corte", bpy.data.objects)

    def test_borrar_el_plano_a_mano_no_rompe(self):
        bpy.ops.bigprint.add_cut_plane()
        bpy.data.objects.remove(self.settings.cut_plane, do_unlink=True)
        # El puntero queda colgando: el complemento debe tolerarlo y recrearlo
        self.assertEqual(bpy.ops.bigprint.add_cut_plane(), {"FINISHED"})
        self.assertIsNotNone(self.settings.cut_plane)


class TestCorteReal(BlenderTestCase):
    """La prueba de fuego de la Fase 2b: dos piezas cerradas que suman el original."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint
        bpy.ops.bigprint.add_cut_plane()

    def _analizar(self, obj):
        return analyze_mesh(
            mesh_bridge.mesh_data_from_object(obj), weld_tolerance=0.01
        )

    def test_genera_dos_piezas(self):
        self.assertEqual(bpy.ops.bigprint.split_in_two(), {"FINISHED"})
        piezas = [o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"]
        self.assertEqual(len(piezas), 2)
        nombres = sorted(o.name for o in piezas)
        self.assertEqual(nombres[0], "BigPrint_Ejemplo_Escuadra_pieza_01")

    def test_las_dos_piezas_quedan_cerradas(self):
        bpy.ops.bigprint.split_in_two()
        for pieza in bpy.context.scene.objects:
            if pieza.get("bigprint_role") != "piece":
                continue
            informe = self._analizar(pieza)
            self.assertTrue(informe.is_watertight, f"{pieza.name} no ha quedado cerrada")
            self.assertTrue(informe.is_solid, f"{pieza.name} no es sólida")

    def test_el_volumen_se_conserva(self):
        bpy.ops.bigprint.split_in_two()
        total = sum(
            self._analizar(o).volume_cm3
            for o in bpy.context.scene.objects
            if o.get("bigprint_role") == "piece"
        )
        self.assertAlmostEqual(total, 8856.0, delta=8856.0 * 0.005)

    def test_el_corte_por_el_centro_parte_en_dos_mitades(self):
        # X = 210 sobre la L: el brazo largo se reparte, la columna queda entera
        bpy.ops.bigprint.split_in_two()
        anchuras = sorted(
            o.dimensions.x
            for o in bpy.context.scene.objects
            if o.get("bigprint_role") == "piece"
        )
        self.assertAlmostEqual(anchuras[0], 210.0, places=1)
        self.assertAlmostEqual(anchuras[1], 210.0, places=1)

    def test_el_original_se_oculta_pero_no_se_borra(self):
        obj = self.settings.source_object
        antes = len(obj.data.vertices)
        bpy.ops.bigprint.split_in_two()
        self.assertIn(obj.name, bpy.data.objects)
        self.assertEqual(len(obj.data.vertices), antes)
        self.assertTrue(obj.hide_render)

    def test_el_resultado_queda_verificado_en_el_panel(self):
        bpy.ops.bigprint.split_in_two()
        resultado = self.settings.cut_result
        self.assertTrue(resultado.has_data)
        self.assertEqual(resultado.piece_count, 2)
        self.assertTrue(resultado.volume_ok)
        self.assertTrue(resultado.all_solid)
        # 260 mm en Z siguen sin caber: el complemento no debe decir que sí
        self.assertFalse(resultado.all_fit)
        self.assertEqual(len(resultado.piece_rows()), 2)

    def test_corte_descentrado(self):
        self.settings.cut_position = 100.0
        bpy.ops.bigprint.split_in_two()
        volumenes = sorted(
            self._analizar(o).volume_cm3
            for o in bpy.context.scene.objects
            if o.get("bigprint_role") == "piece"
        )
        self.assertAlmostEqual(sum(volumenes), 8856.0, delta=8856.0 * 0.005)
        self.assertLess(volumenes[0], volumenes[1])

    def test_descartar_piezas_restaura_el_original(self):
        bpy.ops.bigprint.split_in_two()
        self.assertEqual(bpy.ops.bigprint.remove_pieces(), {"FINISHED"})
        piezas = [o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"]
        self.assertEqual(piezas, [])
        self.assertFalse(self.settings.source_object.hide_render)
        self.assertFalse(self.settings.cut_result.has_data)

    def test_cortar_dos_veces_no_duplica_nombres(self):
        bpy.ops.bigprint.split_in_two()
        bpy.ops.bigprint.split_in_two()
        nombres = [
            o.name for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"
        ]
        self.assertEqual(len(nombres), 2)
        self.assertFalse(any("." in n for n in nombres), nombres)

    def test_no_corta_fuera_de_la_pieza(self):
        self.settings.cut_position = 999.0
        with self.assertRaises(RuntimeError):
            bpy.ops.bigprint.split_in_two()

    def test_cortar_una_pieza_no_encadena_sufijos(self):
        bpy.ops.bigprint.split_in_two()
        pieza = next(
            o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"
        )
        self.settings.source_object = pieza
        bpy.ops.bigprint.analyze()
        bpy.ops.bigprint.add_cut_plane()
        bpy.ops.bigprint.split_in_two()
        nombres = [
            o.name for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"
        ]
        self.assertFalse(any(n.count("_pieza_") > 1 for n in nombres), nombres)


class TestCorteAutomatico(BlenderTestCase):
    """Fase 2c: un botón y todas las piezas salen cabiendo en la impresora."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint

    def _piezas(self):
        return [o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"]

    def _analizar(self, obj):
        return analyze_mesh(mesh_bridge.mesh_data_from_object(obj), weld_tolerance=0.01)

    def test_genera_solo_las_piezas_con_material(self):
        self.assertEqual(bpy.ops.bigprint.split_grid(), {"FINISHED"})
        # La rejilla es 2×1×2, pero la escuadra en L no llena la celda alta del
        # brazo tumbado: esa celda está vacía y no debe producir pieza.
        self.assertEqual(len(self._piezas()), 3)

    def test_no_quedan_objetos_intermedios(self):
        bpy.ops.bigprint.split_grid()
        sobrantes = [o for o in bpy.context.scene.objects if "_tmp_" in o.name]
        self.assertEqual(sobrantes, [], "han quedado piezas intermedias sin borrar")
        self.assertFalse(any("renombrando" in o.name for o in bpy.context.scene.objects))

    def test_numeracion_correlativa_sin_huecos(self):
        bpy.ops.bigprint.split_grid()
        nombres = sorted(o.name for o in self._piezas())
        self.assertEqual(
            nombres,
            [f"BigPrint_Ejemplo_Escuadra_pieza_{i:02d}" for i in range(1, 4)],
        )

    def test_se_numera_de_abajo_arriba(self):
        bpy.ops.bigprint.split_grid()
        por_indice = sorted(self._piezas(), key=lambda o: o["bigprint_piece_index"])
        alturas = [cutting.world_bbox(o)[0][2] for o in por_indice]
        # Las dos primeras son la capa de abajo, la última la de arriba
        self.assertLess(alturas[1], alturas[2])
        self.assertEqual(alturas, sorted(alturas))

    def test_todas_las_piezas_quedan_cerradas(self):
        bpy.ops.bigprint.split_grid()
        for pieza in self._piezas():
            informe = self._analizar(pieza)
            self.assertTrue(informe.is_solid, f"{pieza.name} no es sólida")

    def test_el_volumen_se_conserva_tras_varios_cortes(self):
        bpy.ops.bigprint.split_grid()
        total = sum(self._analizar(p).volume_cm3 for p in self._piezas())
        self.assertAlmostEqual(total, 8856.0, delta=8856.0 * 0.005)

    def test_todas_las_piezas_caben_en_la_impresora(self):
        bpy.ops.bigprint.split_grid()
        resultado = self.settings.cut_result
        self.assertTrue(resultado.all_fit, "el corte automático debe dejarlo todo cabiendo")
        self.assertTrue(resultado.all_solid)
        self.assertTrue(resultado.volume_ok)
        self.assertEqual(resultado.piece_count, 3)

    def test_el_original_sigue_intacto_y_oculto(self):
        obj = self.settings.source_object
        antes = len(obj.data.vertices)
        bpy.ops.bigprint.split_grid()
        self.assertIn(obj.name, bpy.data.objects)
        self.assertEqual(len(obj.data.vertices), antes)
        self.assertTrue(obj.hide_render)

    def test_descartar_piezas_lo_deja_como_estaba(self):
        bpy.ops.bigprint.split_grid()
        bpy.ops.bigprint.remove_pieces()
        self.assertEqual(self._piezas(), [])
        self.assertFalse(self.settings.source_object.hide_render)

    def test_recortar_reemplaza_el_corte_anterior(self):
        bpy.ops.bigprint.split_grid()
        primeros = sorted(o.name for o in self._piezas())
        bpy.ops.bigprint.split_grid()
        segundos = sorted(o.name for o in self._piezas())
        # Mismos nombres, misma cantidad: nada de ".001" acumulándose
        self.assertEqual(primeros, segundos)
        self.assertEqual(len(segundos), 3)
        self.assertFalse(any("." in n for n in segundos), segundos)

    def test_lo_que_ya_cabe_no_se_corta(self):
        limpiar_escena()
        bpy.ops.mesh.primitive_cube_add(size=100.0)  # 100 mm de lado
        bpy.context.scene.bigprint.source_object = bpy.context.active_object
        bpy.context.scene.bigprint.model_unit = "MM"
        bpy.ops.bigprint.analyze()
        self.assertEqual(bpy.ops.bigprint.split_grid(), {"CANCELLED"})
        self.assertEqual(self._piezas(), [])


class TestConectores(BlenderTestCase):
    """Fase 3a: proponer conectores sin tocar las piezas."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint
        bpy.ops.bigprint.split_grid()

    def test_se_registran_los_planos_de_corte(self):
        planos = self.settings.cut_result.plane_list()
        self.assertEqual(len(planos), 2)
        ejes = sorted(eje for eje, _ in planos)
        self.assertEqual(ejes, [0, 2])

    def test_propone_conectores(self):
        self.assertEqual(bpy.ops.bigprint.preview_connectors(), {"FINISHED"})
        resultado = self.settings.connector_result
        self.assertTrue(resultado.has_data)
        self.assertGreater(resultado.total, 0)
        self.assertIsNotNone(self.settings.connector_preview)

    def test_los_cilindros_estan_sobre_las_caras_de_corte(self):
        bpy.ops.bigprint.preview_connectors()
        previa = self.settings.connector_preview
        caja_min, caja_max = cutting.world_bbox(previa)
        # Los conectores del corte en X = 210 se centran en ese plano
        self.assertLess(caja_min[0], 210.0)
        self.assertGreater(caja_max[0], 210.0)

    def test_no_se_tocan_las_piezas(self):
        piezas = [o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"]
        antes = {o.name: len(o.data.vertices) for o in piezas}
        bpy.ops.bigprint.preview_connectors()
        despues = {o.name: len(o.data.vertices) for o in piezas}
        self.assertEqual(antes, despues, "la fase 3a no debe modificar las piezas")

    def test_imanes(self):
        self.settings.connector_kind = "MAGNET"
        self.settings.magnet_size = "8x3"
        bpy.ops.bigprint.preview_connectors()
        self.assertGreater(self.settings.connector_result.total, 0)
        self.assertIn("imán", " ".join(self.settings.connector_result.lines()))

    def test_dowel_e_iman_a_la_vez(self):
        self.settings.connector_kind = "BOTH"
        bpy.ops.bigprint.preview_connectors()
        lineas = " ".join(self.settings.connector_result.lines())
        self.assertIn("dowel", lineas)
        self.assertIn("imán", lineas)

    def test_el_tope_se_respeta(self):
        self.settings.connector_kind = "DOWEL"
        self.settings.connector_max = 2
        bpy.ops.bigprint.preview_connectors()
        # Dos caras de corte, dos conectores como mucho en cada una
        self.assertLessEqual(self.settings.connector_result.total, 4)

    def test_quitar_la_vista_previa(self):
        bpy.ops.bigprint.preview_connectors()
        self.assertEqual(bpy.ops.bigprint.clear_connectors(), {"FINISHED"})
        self.assertIsNone(self.settings.connector_preview)
        self.assertNotIn("BigPrint_Conectores", bpy.data.objects)

    def test_descartar_piezas_limpia_los_conectores(self):
        bpy.ops.bigprint.preview_connectors()
        bpy.ops.bigprint.remove_pieces()
        self.assertIsNone(self.settings.connector_preview)
        self.assertFalse(self.settings.connector_result.has_data)


class TestPerforado(BlenderTestCase):
    """Fase 3b: los agujeros de verdad, con el booleano."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint
        bpy.ops.bigprint.split_grid()
        self.settings.connector_kind = "DOWEL"
        self.settings.dowel_size = "3x20"
        bpy.ops.bigprint.preview_connectors()

    def _piezas(self):
        return [o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"]

    def _volumen(self, obj):
        return analyze_mesh(
            mesh_bridge.mesh_data_from_object(obj), weld_tolerance=0.01
        ).volume_cm3

    def test_perfora_y_retira_material(self):
        antes = sum(self._volumen(p) for p in self._piezas())
        self.assertEqual(bpy.ops.bigprint.apply_connectors(), {"FINISHED"})
        despues = sum(self._volumen(p) for p in self._piezas())
        self.assertLess(despues, antes, "no se ha retirado material")
        self.assertGreater(self.settings.connector_result.removed_cm3, 0.0)

    def test_el_material_retirado_cuadra_con_los_cilindros(self):
        resultado = self.settings.connector_result
        total = resultado.total
        bpy.ops.bigprint.apply_connectors()
        # Cada conector retira un cilindro de ⌀3,2 y 20 mm de largo
        import math

        esperado = total * math.pi * (3.2 / 2) ** 2 * 20.0 / 1000.0
        self.assertAlmostEqual(
            self.settings.connector_result.removed_cm3, esperado, delta=esperado * 0.05
        )

    def test_las_piezas_siguen_cerradas(self):
        bpy.ops.bigprint.apply_connectors()
        for pieza in self._piezas():
            informe = analyze_mesh(
                mesh_bridge.mesh_data_from_object(pieza), weld_tolerance=0.01
            )
            self.assertTrue(informe.is_solid, f"{pieza.name} se ha roto al perforar")

    def test_los_agujeros_existen_en_la_malla(self):
        antes = {p.name: len(p.data.vertices) for p in self._piezas()}
        bpy.ops.bigprint.apply_connectors()
        despues = {p.name: len(p.data.vertices) for p in self._piezas()}
        for nombre in antes:
            self.assertGreater(despues[nombre], antes[nombre], f"{nombre} sin geometría nueva")

    def test_no_quedan_modificadores_vivos(self):
        bpy.ops.bigprint.apply_connectors()
        for pieza in self._piezas():
            self.assertEqual(len(pieza.modifiers), 0, "el booleano debe quedar aplicado")

    def test_el_cortador_desaparece_tras_perforar(self):
        bpy.ops.bigprint.apply_connectors()
        self.assertIsNone(self.settings.connector_preview)
        self.assertNotIn("BigPrint_Conectores", bpy.data.objects)

    def test_el_original_sigue_intacto(self):
        obj = self.settings.source_object
        antes = len(obj.data.vertices)
        bpy.ops.bigprint.apply_connectors()
        self.assertEqual(len(obj.data.vertices), antes)

    def test_no_se_perfora_dos_veces(self):
        bpy.ops.bigprint.apply_connectors()
        self.assertTrue(self.settings.connector_result.applied)
        self.assertFalse(bpy.ops.bigprint.apply_connectors.poll())

    def test_imanes(self):
        self.settings.connector_kind = "MAGNET"
        self.settings.magnet_size = "6x3"
        bpy.ops.bigprint.preview_connectors()
        antes = sum(self._volumen(p) for p in self._piezas())
        bpy.ops.bigprint.apply_connectors()
        self.assertLess(sum(self._volumen(p) for p in self._piezas()), antes)


class TestExportacion(BlenderTestCase):
    """Fase 5: un STL por pieza, en milímetros, más la lista."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint
        bpy.ops.bigprint.split_grid()
        self.tmp = tempfile.mkdtemp()
        self.settings.export_dir = self.tmp

    def tearDown(self):
        for nombre in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, nombre))
        os.rmdir(self.tmp)

    def _ficheros(self, extension=".stl"):
        return sorted(n for n in os.listdir(self.tmp) if n.endswith(extension))

    def test_un_fichero_por_pieza(self):
        self.assertEqual(bpy.ops.bigprint.export_pieces(), {"FINISHED"})
        self.assertEqual(len(self._ficheros()), 3)

    def test_los_nombres_son_los_de_las_piezas(self):
        bpy.ops.bigprint.export_pieces()
        self.assertEqual(
            self._ficheros(),
            [f"BigPrint_Ejemplo_Escuadra_pieza_{i:02d}.stl" for i in range(1, 4)],
        )

    def test_los_stl_salen_en_milimetros(self):
        bpy.ops.bigprint.export_pieces()
        ruta = os.path.join(self.tmp, self._ficheros()[0])
        with open(ruta, "rb") as f:
            f.read(84)
            f.read(12)
            coords = struct.unpack("<9f", f.read(36))
        # La escuadra mide cientos de mm: si saliera en metros, todo sería < 1
        self.assertGreater(max(abs(c) for c in coords), 10.0)

    def test_los_stl_son_solidos_cerrados(self):
        from bigprint_modular.core.geometry import MeshData
        from bigprint_modular.core.mesh_analysis import analyze_mesh as analizar

        bpy.ops.bigprint.export_pieces()
        for nombre in self._ficheros():
            with open(os.path.join(self.tmp, nombre), "rb") as f:
                f.read(80)
                (n,) = struct.unpack("<I", f.read(4))
                verts = []
                tris = []
                for _ in range(n):
                    f.read(12)
                    base = len(verts)
                    for _ in range(3):
                        verts.append(struct.unpack("<3f", f.read(12)))
                    f.read(2)
                    tris.append((base, base + 1, base + 2))
            informe = analizar(MeshData(vertices=verts, triangles=tris), weld_tolerance=0.01)
            self.assertTrue(informe.is_watertight, f"{nombre} no está cerrada")

    def test_la_suma_de_los_stl_es_el_original(self):
        from bigprint_modular.core.geometry import MeshData
        from bigprint_modular.core.mesh_analysis import analyze_mesh as analizar

        bpy.ops.bigprint.export_pieces()
        total = 0.0
        for nombre in self._ficheros():
            with open(os.path.join(self.tmp, nombre), "rb") as f:
                f.read(80)
                (n,) = struct.unpack("<I", f.read(4))
                verts = []
                tris = []
                for _ in range(n):
                    f.read(12)
                    base = len(verts)
                    for _ in range(3):
                        verts.append(struct.unpack("<3f", f.read(12)))
                    f.read(2)
                    tris.append((base, base + 1, base + 2))
            total += analizar(MeshData(vertices=verts, triangles=tris), weld_tolerance=0.01).volume_cm3
        self.assertAlmostEqual(total, 8856.0, delta=8856.0 * 0.005)

    def test_lista_csv(self):
        bpy.ops.bigprint.export_pieces()
        self.assertEqual(self._ficheros(".csv"), ["piezas.csv"])
        with open(os.path.join(self.tmp, "piezas.csv"), encoding="utf-8-sig") as f:
            lineas = f.read().strip().split("\n")
        self.assertEqual(len(lineas), 4)  # cabecera + tres piezas
        self.assertIn("volumen_cm3", lineas[0])

    def test_sin_lista_si_se_desmarca(self):
        self.settings.export_list = False
        bpy.ops.bigprint.export_pieces()
        self.assertEqual(self._ficheros(".csv"), [])

    def test_exportar_con_agujeros(self):
        bpy.ops.bigprint.preview_connectors()
        bpy.ops.bigprint.apply_connectors()
        bpy.ops.bigprint.export_pieces()
        # Tres piezas más el fichero de varillas, que no es una pieza
        piezas = [n for n in self._ficheros() if not n.startswith("varillas")]
        self.assertEqual(len(piezas), 3)
        self.assertIn("3 piezas", self.settings.export_report)

    def test_crea_la_carpeta_si_no_existe(self):
        destino = os.path.join(self.tmp, "nueva")
        self.settings.export_dir = destino
        self.assertEqual(bpy.ops.bigprint.export_pieces(), {"FINISHED"})
        self.assertTrue(os.path.isdir(destino))
        for nombre in os.listdir(destino):
            os.remove(os.path.join(destino, nombre))
        os.rmdir(destino)


class TestNumeracionGrabada(BlenderTestCase):
    """Fase 4: el número hundido en la cara inferior de cada pieza."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint
        bpy.ops.bigprint.split_grid()

    def _piezas(self):
        return [o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"]

    def _volumen(self, obj):
        return analyze_mesh(
            mesh_bridge.mesh_data_from_object(obj), weld_tolerance=0.01
        ).volume_cm3

    def test_numera_todas_las_piezas(self):
        self.assertEqual(bpy.ops.bigprint.number_pieces(), {"FINISHED"})
        self.assertIn("3 de 3", self.settings.label_report)

    def test_el_grabado_retira_material(self):
        antes = sum(self._volumen(p) for p in self._piezas())
        bpy.ops.bigprint.number_pieces()
        despues = sum(self._volumen(p) for p in self._piezas())
        self.assertLess(despues, antes)
        # Un número de 10 mm y 0,6 de hondo retira muy poco: menos de 1 cm³
        self.assertLess(antes - despues, 1.0)

    def test_las_piezas_siguen_cerradas(self):
        bpy.ops.bigprint.number_pieces()
        for pieza in self._piezas():
            informe = analyze_mesh(
                mesh_bridge.mesh_data_from_object(pieza), weld_tolerance=0.01
            )
            self.assertTrue(informe.is_solid, f"{pieza.name} se ha roto al grabar")

    def test_el_grabado_esta_en_la_cara_inferior(self):
        piezas = self._piezas()
        antes = {p.name: cutting.world_bbox(p) for p in piezas}
        bpy.ops.bigprint.number_pieces()
        for pieza in piezas:
            caja_antes = antes[pieza.name]
            caja_ahora = cutting.world_bbox(pieza)
            # El hueco no cambia la caja envolvente: no asoma por fuera
            for i in range(3):
                self.assertAlmostEqual(caja_antes[0][i], caja_ahora[0][i], places=2)
                self.assertAlmostEqual(caja_antes[1][i], caja_ahora[1][i], places=2)

    def test_no_quedan_objetos_de_texto_sueltos(self):
        bpy.ops.bigprint.number_pieces()
        sobrantes = [o for o in bpy.data.objects if "Numero_tmp" in o.name]
        self.assertEqual(sobrantes, [])
        self.assertFalse(any("Numero_tmp" in c.name for c in bpy.data.curves))

    def test_no_quedan_modificadores(self):
        bpy.ops.bigprint.number_pieces()
        for pieza in self._piezas():
            self.assertEqual(len(pieza.modifiers), 0)

    def test_numerar_y_luego_perforar(self):
        bpy.ops.bigprint.number_pieces()
        bpy.ops.bigprint.preview_connectors()
        self.assertEqual(bpy.ops.bigprint.apply_connectors(), {"FINISHED"})
        for pieza in self._piezas():
            informe = analyze_mesh(
                mesh_bridge.mesh_data_from_object(pieza), weld_tolerance=0.01
            )
            self.assertTrue(informe.is_solid)

    def test_el_original_sigue_intacto(self):
        obj = self.settings.source_object
        antes = len(obj.data.vertices)
        bpy.ops.bigprint.number_pieces()
        self.assertEqual(len(obj.data.vertices), antes)


class TestDespiece(BlenderTestCase):
    """Fase 6: ver las piezas separadas sin tocar la geometría."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint
        bpy.ops.bigprint.split_grid()

    def _piezas(self):
        return [o for o in bpy.context.scene.objects if o.get("bigprint_role") == "piece"]

    def test_el_deslizador_separa_las_piezas(self):
        antes = [tuple(p.location) for p in self._piezas()]
        self.settings.explode_factor = 1.0
        despues = [tuple(p.location) for p in self._piezas()]
        self.assertNotEqual(antes, despues)
        self.assertTrue(any(any(abs(c) > 1.0 for c in loc) for loc in despues))

    def test_montar_devuelve_todo_a_su_sitio(self):
        antes = [tuple(p.location) for p in self._piezas()]
        self.settings.explode_factor = 1.5
        bpy.ops.bigprint.assemble()
        despues = [tuple(p.location) for p in self._piezas()]
        for a, d in zip(antes, despues):
            for i in range(3):
                self.assertAlmostEqual(a[i], d[i], places=4)
        self.assertEqual(self.settings.explode_factor, 0.0)

    def test_la_geometria_no_cambia(self):
        antes = {p.name: len(p.data.vertices) for p in self._piezas()}
        self.settings.explode_factor = 1.0
        despues = {p.name: len(p.data.vertices) for p in self._piezas()}
        self.assertEqual(antes, despues)

    def test_las_piezas_se_alejan_unas_de_otras(self):
        def distancia_media():
            bpy.context.view_layer.update()  # world_bbox lee matrix_world
            centros = [cutting.world_bbox(p) for p in self._piezas()]
            medios = [
                tuple((c[0][i] + c[1][i]) * 0.5 for i in range(3)) for c in centros
            ]
            total = 0.0
            cuenta = 0
            for i in range(len(medios)):
                for j in range(i + 1, len(medios)):
                    total += sum((medios[i][k] - medios[j][k]) ** 2 for k in range(3)) ** 0.5
                    cuenta += 1
            return total / max(cuenta, 1)

        montado = distancia_media()
        self.settings.explode_factor = 1.0
        self.assertGreater(distancia_media(), montado)

    def test_exportar_devuelve_las_piezas_a_montaje(self):
        import tempfile

        tmp = tempfile.mkdtemp()
        self.settings.export_dir = tmp
        self.settings.explode_factor = 1.0
        bpy.ops.bigprint.export_pieces()
        # Los STL deben salir en coordenadas de montaje, no despiezadas
        for pieza in self._piezas():
            for componente in pieza.location:
                self.assertAlmostEqual(componente, 0.0, places=4)
        for nombre in os.listdir(tmp):
            os.remove(os.path.join(tmp, nombre))
        os.rmdir(tmp)

    def test_mover_el_deslizador_varias_veces_no_desvia(self):
        """Regresión: con matrix_world sin actualizar, las direcciones se torcían."""
        self.settings.explode_factor = 1.0
        bpy.context.view_layer.update()
        directo = [tuple(p.location) for p in self._piezas()]

        bpy.ops.bigprint.assemble()
        for factor in (0.3, 0.6, 1.0):
            self.settings.explode_factor = factor
        bpy.context.view_layer.update()
        por_pasos = [tuple(p.location) for p in self._piezas()]

        for a, b in zip(directo, por_pasos):
            for i in range(3):
                self.assertAlmostEqual(a[i], b[i], places=3)

    def test_ida_y_vuelta_repetida(self):
        antes = [tuple(p.location) for p in self._piezas()]
        for factor in (0.5, 1.2, 0.0, 2.0, 0.0):
            self.settings.explode_factor = factor
        despues = [tuple(p.location) for p in self._piezas()]
        for a, d in zip(antes, despues):
            for i in range(3):
                self.assertAlmostEqual(a[i], d[i], places=4)


class TestColecciones(BlenderTestCase):
    """El original y las piezas viven separados para poder apagar uno de los dos."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint

    def _nombres(self, coleccion):
        col = bpy.data.collections.get(coleccion)
        return sorted(o.name for o in col.objects) if col else []

    def test_la_rejilla_separa_original_y_piezas(self):
        bpy.ops.bigprint.split_grid()
        piezas = self._nombres(cutting.PIECES_COLLECTION)
        self.assertEqual(len(piezas), 3)
        self.assertEqual(
            self._nombres(cutting.ORIGINAL_COLLECTION), ["BigPrint_Ejemplo_Escuadra"]
        )

    def test_el_corte_manual_tambien(self):
        bpy.ops.bigprint.add_cut_plane()
        bpy.ops.bigprint.split_in_two()
        self.assertEqual(len(self._nombres(cutting.PIECES_COLLECTION)), 2)
        self.assertEqual(len(self._nombres(cutting.ORIGINAL_COLLECTION)), 1)

    def test_cada_objeto_esta_en_una_sola_coleccion(self):
        bpy.ops.bigprint.split_grid()
        for obj in bpy.context.scene.objects:
            if obj.get("bigprint_role") == "piece":
                self.assertEqual(len(obj.users_collection), 1, obj.name)

    def test_no_quedan_intermedias_en_la_coleccion(self):
        bpy.ops.bigprint.split_grid()
        for nombre in self._nombres(cutting.PIECES_COLLECTION):
            self.assertIn("_pieza_", nombre)

    def test_descartar_devuelve_el_original_a_la_escena(self):
        bpy.ops.bigprint.split_grid()
        bpy.ops.bigprint.remove_pieces()
        self.assertEqual(self._nombres(cutting.PIECES_COLLECTION), [])
        original = self.settings.source_object
        self.assertIn(original.name, [o.name for o in bpy.context.scene.collection.objects])
        self.assertFalse(original.hide_get())

    def test_mostrar_y_ocultar_el_original(self):
        bpy.ops.bigprint.split_grid()
        original = self.settings.source_object
        self.assertTrue(original.hide_get(), "tras cortar debe quedar oculto")
        bpy.ops.bigprint.toggle_original()
        self.assertFalse(original.hide_get())
        bpy.ops.bigprint.toggle_original()
        self.assertTrue(original.hide_get())


class TestVarillas(BlenderTestCase):
    """Las varillas de los dowels, imprimibles y a medida del agujero."""

    def setUp(self):
        limpiar_escena()
        bpy.ops.bigprint.load_example()
        bpy.ops.bigprint.analyze()
        self.settings = bpy.context.scene.bigprint
        bpy.ops.bigprint.split_grid()
        self.settings.connector_kind = "DOWEL"
        self.settings.dowel_size = "3x20"
        bpy.ops.bigprint.preview_connectors()
        self.tmp = tempfile.mkdtemp()
        self.settings.export_dir = self.tmp

    def tearDown(self):
        for nombre in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, nombre))
        os.rmdir(self.tmp)

    def _ficheros(self):
        return sorted(os.listdir(self.tmp))

    def test_se_cuentan_las_varillas_necesarias(self):
        resultado = self.settings.connector_result
        self.assertGreater(resultado.dowel_count, 0)
        self.assertEqual(resultado.dowel_count, resultado.total)

    def test_se_exporta_el_fichero_de_varillas(self):
        bpy.ops.bigprint.export_pieces()
        varillas = [n for n in self._ficheros() if n.startswith("varillas")]
        self.assertEqual(len(varillas), 1)
        self.assertIn(f"x{self.settings.connector_result.dowel_count}", varillas[0])

    def test_la_varilla_entra_en_el_agujero(self):
        from bigprint_modular.core import dowels as core_dowels

        bpy.ops.bigprint.export_pieces()
        spec = self.settings.resolve_dowel()
        impreso = core_dowels.printed_diameter(spec, self.settings.dowel_fit_gap)
        self.assertLess(impreso, spec.hole_diameter, "la varilla no entraría")

    def test_el_stl_de_varillas_es_correcto(self):
        from bigprint_modular.core.geometry import MeshData
        from bigprint_modular.core.mesh_analysis import analyze_mesh as analizar

        bpy.ops.bigprint.export_pieces()
        nombre = [n for n in self._ficheros() if n.startswith("varillas")][0]
        with open(os.path.join(self.tmp, nombre), "rb") as f:
            f.read(80)
            (n,) = struct.unpack("<I", f.read(4))
            verts = []
            tris = []
            for _ in range(n):
                f.read(12)
                base = len(verts)
                for _ in range(3):
                    verts.append(struct.unpack("<3f", f.read(12)))
                f.read(2)
                tris.append((base, base + 1, base + 2))

        informe = analizar(MeshData(vertices=verts, triangles=tris), weld_tolerance=0.01)
        self.assertTrue(informe.is_watertight)
        # Una varilla por conector, cada una tumbada y apoyada en la cama
        self.assertEqual(informe.shell_count, self.settings.connector_result.dowel_count)
        self.assertAlmostEqual(informe.dimensions_mm[0], 20.0, delta=0.5)
        self.assertAlmostEqual(informe.bbox_min_mm[2], 0.0, places=2)

    def test_la_varilla_va_tumbada(self):
        from bigprint_modular.core import dowels as core_dowels
        from bigprint_modular.core.mesh_analysis import analyze_mesh as analizar

        malla = core_dowels.dowel_mesh(3.0, 20.0)
        informe = analizar(malla)
        # Larga en X, fina en Z: las capas corren a lo largo de la varilla
        self.assertGreater(informe.dimensions_mm[0], informe.dimensions_mm[2] * 3)

    def test_sin_varillas_si_se_desmarca(self):
        self.settings.export_dowels = False
        bpy.ops.bigprint.export_pieces()
        self.assertEqual([n for n in self._ficheros() if n.startswith("varillas")], [])

    def test_con_imanes_no_se_generan_varillas(self):
        self.settings.connector_kind = "MAGNET"
        bpy.ops.bigprint.preview_connectors()
        self.assertEqual(self.settings.connector_result.dowel_count, 0)
        bpy.ops.bigprint.export_pieces()
        self.assertEqual([n for n in self._ficheros() if n.startswith("varillas")], [])

    def test_la_lista_incluye_las_varillas(self):
        bpy.ops.bigprint.export_pieces()
        with open(os.path.join(self.tmp, "piezas.csv"), encoding="utf-8-sig") as f:
            contenido = f.read()
        self.assertIn("varillas", contenido)


def main():
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if resultado.wasSuccessful() else 1)



class TestTallerModoObjetoYHuecos(BlenderTestCase):
    """0.12: piezas vaciadas y regla de modo Objeto."""

    def _esfera_hueca(self):
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=30)
        dentro = bmesh.new()
        bmesh.ops.create_uvsphere(dentro, u_segments=48, v_segments=24, radius=26)
        bmesh.ops.reverse_faces(dentro, faces=dentro.faces[:])
        tmp = bpy.data.meshes.new("tmp")
        dentro.to_mesh(tmp)
        dentro.free()
        bm.from_mesh(tmp)
        malla = bpy.data.meshes.new("Hueca")
        bm.to_mesh(malla)
        bm.free()
        obj = bpy.data.objects.new("Hueca", malla)
        bpy.context.scene.collection.objects.link(obj)
        return obj

    def test_corte_de_pieza_hueca_deja_tapa_en_anillo(self):
        import math
        import bmesh
        obj = self._esfera_hueca()
        piezas = cutting.split_object(bpy.context, obj, (0, 0, 5), (0, 0, 1))
        total = 0.0
        for pieza in piezas:
            bm = bmesh.new()
            bm.from_mesh(pieza.data)
            self.assertTrue(all(e.is_manifold for e in bm.edges), pieza.name)
            total += abs(bm.calc_volume(signed=True))
            bm.free()
        cascara = 4 / 3 * math.pi * (30 ** 3 - 26 ** 3)
        self.assertLess(abs(total - cascara) / cascara, 0.05)

    def test_botones_desactivados_en_modo_edicion(self):
        obj = self._esfera_hueca()
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            self.assertFalse(bpy.ops.bigprint.use_active.poll())
            self.assertFalse(bpy.ops.bigprint.load_example.poll())
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
        self.assertTrue(bpy.ops.bigprint.use_active.poll())

if __name__ == "__main__":
    main()
