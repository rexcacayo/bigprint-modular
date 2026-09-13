# BigPrint Modular

Complemento de Blender, software libre bajo licencia MIT.

Complemento de Blender para imprimir modelos grandes en impresoras pequeñas:
importa el modelo, lo parte en piezas que quepan en la cama, añade conectores y
exporta todo listo para laminar.

**Estado: todas las fases.** Analiza, corta, pone conectores y exporta las piezas listas para laminar. Ahora mismo el complemento *analiza*, todavía no
corta. Lo que hay implementado está probado; lo que falta está al final de este
documento, sin adornos.

---

## Instalación

**Blender 4.2 o superior (extensión)**

1. Comprime la carpeta `bigprint_modular/` en un ZIP (o usa el que se
   distribuye: `bigprint_modular-0.1.0.zip`).
2. Blender → Editar → Preferencias → Complementos → flecha ▾ → *Install from
   Disk…* → elige el ZIP.
3. Actívalo si no se activa solo.

**Blender 3.6 a 4.1 (complemento clásico)**

Mismo procedimiento con *Instalar…*; el `bl_info` del `__init__.py` cubre estas
versiones.

**Durante el desarrollo** puedes saltarte la instalación: copia (o enlaza) la
carpeta en `scripts/addons/` de tu configuración de Blender, o ejecuta los tests
directamente, que no requieren instalar nada.

El panel aparece en la **Vista 3D → barra lateral (tecla `N`) → pestaña
BigPrint**.

---

## Uso (Fase 1)

1. **Impresora** — elige el perfil. Por defecto, *Genérica 256* (256×256×256 mm,
   margen 10 mm → volumen útil **236×236×236 mm**). Con *Personalizada* defines
   la cama a mano.
2. **Modelo** — `Importar modelo` (STL/OBJ/PLY) o `Usar objeto activo`. También
   hay `Cargar ejemplo`, que crea una escuadra de 420×180×260 mm.
3. Revisa **Unidad del modelo**. En automático se deduce del tamaño; si el
   modelo llega mal escalado, fíjala a mano.
4. **Analizar modelo**. Obtienes dimensiones en mm, volumen, superficie,
   topología, si la malla está cerrada y cuántas piezas harían falta.
5. **Corte** → `Crear plano de corte`. Aparece un plano en alambre, centrado en
   el eje que más se pasa del volumen útil. Muévelo con el deslizador y mira el
   reparto previsto: dimensiones de cada mitad y si cabrían.
6. `Cortar automáticamente` aplica el plan de rejilla completo: corta por todos
   los planos necesarios, borra los objetos intermedios y deja las piezas
   numeradas de abajo arriba (`_pieza_01`, `_pieza_02`…). El original se oculta,
   no se borra.
7. **Exportar** → elige carpeta y `Exportar piezas`. Escribe un STL por pieza,
   siempre en milímetros, más `piezas.csv` con dimensiones, volúmenes y si cada
   una cabe. Si has puesto dowels, escribe además un STL con todas las varillas
   necesarias, tumbadas y en fila, listas para imprimir de una tirada. El STL se escribe directamente, sin pasar por el exportador de
   Blender, para que las unidades no dependan de la escena.
8. O bien `Cortar en dos`, que genera dos objetos nuevos (`..._pieza_01` y `..._pieza_02`) y
   oculta el original, que no se modifica ni se borra. Debajo aparece la
   verificación: volumen de cada pieza, si ha quedado cerrada, si cabe, y si la
   suma cuadra con el original. `Descartar piezas` deshace todo y vuelve a
   mostrar el modelo.

Al cortar, el original pasa a la colección **BigPrint_Original** y las piezas a
**BigPrint_Piezas**, para poder apagar una de las dos desde el esquema y mirar
solo el despiece. `Descartar piezas` devuelve el original a la escena.

El corte usa `bisect_plane` y tapa la sección buscando las aristas de borde de
toda la malla, no solo las que devuelve bisect: así se cierran también las
secciones que quedan en varios trozos cuando el plano atraviesa dos brazos de
una misma pieza.

El modelo original **nunca se modifica**. El análisis trabaja sobre una copia
temporal: se evalúa la malla con `to_mesh()`, se copia a un `bmesh` propio, se
triangula y se suelda ahí, y se libera. No hay ni una escritura sobre
`obj.data`, y hay un test en Blender que lo comprueba comparando el objeto antes
y después.

### Qué significa cada resultado

| Indicador | Qué es | Por qué importa |
|---|---|---|
| **Cerrada** | Cero aristas de borde | Si está abierta, no se puede cortar en sólidos |
| **Manifold** | Ninguna arista con más de dos caras | La geometría no-manifold rompe los booleanos del corte |
| **Volumen** | Volumen encerrado, en cm³ | Estima material y confirma que es un sólido, no una cáscara |
| **Islas** | Trozos desconectados | Varias islas se tratarán como un solo modelo al cortar |
| **Normales invertidas** | Volumen con signo negativo | La pieza está "del revés"; se arregla con Recalcular normales |
| **Apta para cortar** | Cerrada + manifold + con volumen | Condición de entrada de la Fase 2 |

### Dos ajustes que conviene entender

**Unidad del modelo.** Blender no guarda en qué unidad se modeló un STL: un cubo
de 200 mm puede llegar como `200` (STL típico) o como `0.2` (modelado en
metros). En *Automático* se decide por el tamaño de la caja envolvente: ≥ 20
unidades → mm, entre 2 y 20 → cm, menos de 2 → m. Es una heurística; el panel
siempre muestra qué unidad se ha usado para que puedas corregirla.

**Soldar al analizar.** Un STL repite los tres vértices de cada triángulo, sin
compartirlos. Analizado tal cual, el sólido mejor cerrado del mundo aparece como
una malla llena de agujeros. Por eso, antes del análisis topológico se funden
los vértices coincidentes de la copia (tolerancia por defecto 0,01 mm). Si lo
desactivas y ves miles de aristas de borde, es esto.

---

## Arquitectura

La lógica propia está separada de la interfaz de Blender, que era el requisito
de partida:

```
bigprint_modular/
├── __init__.py               bl_info, registro y recarga en caliente
├── blender_manifest.toml     metadatos de extensión (Blender 4.2+)
├── core/                     Python puro: NADA de aquí importa bpy
│   ├── geometry.py           BBox, MeshData, áreas y volúmenes
│   ├── units.py              conversión y detección de unidades
│   ├── printer_profiles.py   perfiles, volumen útil, encaje, nº de piezas
│   ├── mesh_cleanup.py       soldado de vértices coincidentes
│   ├── mesh_analysis.py      informe completo de la malla
│   └── sample_shapes.py      sólidos generados por código (ejemplo y tests)
├── blender/                  única parte que importa bpy / bmesh
│   ├── mesh_bridge.py        objeto de Blender → MeshData (solo lectura)
│   ├── properties.py         ajustes y caché del análisis en la escena
│   ├── operators.py          importar, seleccionar, analizar, limpiar
│   ├── panels.py             panel BigPrint y sus tres subpaneles
│   └── example_model.py      vuelca el sólido de ejemplo a una malla
├── tests/
├── examples/
└── README.md
```

La frontera es literal: `core/` se puede importar con `python3` a secas y hay un
test que falla si alguien cuela un `import bpy` ahí dentro. Esto es lo que
permite que 75 de los tests corran en segundos sin abrir Blender, y también deja
la puerta abierta a reutilizar el núcleo desde una CLI más adelante.

**El único punto de lectura de Blender es `mesh_bridge.py`.** Todo lo que sale
de ahí son tuplas de Python.

---

## Tests

```bash
# 75 tests, sin Blender: núcleo + estructura del complemento (~0,05 s)
python3 tests/run_tests.py

# Verificación real dentro de Blender
blender --background --python tests/test_in_blender.py
```

La batería de escritorio cubre dos cosas:

- **El núcleo**, contra sólidos de volumen conocido (una caja de 100×50×25
  tiene que dar 125 cm³; la escuadra de ejemplo, 8856 cm³), mallas abiertas,
  normales invertidas, geometría no-manifold, islas separadas, conversión de
  unidades e ida y vuelta a STL binario.
- **La capa de Blender**, con un doble de pruebas de `bpy` (`tests/fake_bpy.py`).
  No emula Blender: solo lo justo para importar el complemento, registrar y
  desregistrar, y ejercitar el volcado informe → propiedades. Sirve para cazar
  los fallos tontos en CI sin abrir Blender.

`tests/test_in_blender.py` cubre lo que el doble no puede: registro real de
clases, lectura con `bmesh`, escala del objeto, modificadores evaluados sin
aplicarlos, importación de un STL de verdad y **la comprobación de que el objeto
original queda byte a byte igual tras analizarlo**.

### Dos fallos reales que encontraron los tests

1. **`from __future__ import annotations` rompía el complemento entero.** Blender
   registra las propiedades leyendo `__annotations__`, y PEP 563 las convierte en
   cadenas: el panel habría salido vacío sin ningún error claro. Está corregido y
   hay un test de regresión que lo detecta en tiempo de ejecución.
2. **Los STL parecían mallas abiertas.** De ahí el soldado de vértices descrito
   arriba, con un test que escribe un STL, lo relee y comprueba ambos
   comportamientos.

---

## Ejemplo

```bash
python3 examples/make_example_stl.py
```

Genera `examples/ejemplo_escuadra_420x180x260.stl`: una escuadra en L de
420×180×260 mm, cerrada y con 8856 cm³. Se genera por código en lugar de
guardar un binario en el repositorio, así el ejemplo es reproducible y los tests
usan exactamente el mismo sólido. Con el perfil de 256 mm el resultado esperado
es *no cabe*, estimación **2 × 1 × 2 = 4 piezas**.

Dentro de Blender, el botón `Cargar ejemplo` crea la misma pieza sin salir de la
aplicación.

---

## Qué funciona hoy

- Estructura del complemento con núcleo separado de la interfaz.
- Panel BigPrint con subpaneles de Impresora, Modelo y Análisis.
- Perfiles de impresora: Genérica 256 (256³, margen 10), Flashforge Adventurer
  5M Pro, Ender 3/V2, Prusa MK4, Bambu A1 mini y perfil personalizado.
- Cálculo de volumen útil descontando el margen por los dos lados de cada eje.
- Importar STL/OBJ/PLY (compatible con `wm.stl_import` de 4.2+ y con el
  `import_mesh.stl` clásico) o usar el objeto activo.
- Dimensiones en mm, con detección de unidades y modificadores evaluados.
- Análisis: cerrada, manifold, volumen, superficie, aristas de borde,
  no-manifold, triángulos degenerados, vértices sueltos, islas, normales
  invertidas.
- Comprobación de encaje con giros de 90° y estimación de piezas en rejilla.
- Garantía de no modificar el original, verificada por test.
- README, 75 tests de escritorio, suite de Blender y ejemplo reproducible.

## Qué NO está implementado todavía

Nada de esto existe aún, ni siquiera a medias:

- **La rebaja de la varilla impresa** (0,15 mm de diámetro por defecto) es un
  valor de partida. La impresión FDM saca los agujeros algo estrechos y los
  cilindros algo gordos, y cuánto depende de tu máquina y tu material. Imprime
  el primer lote, prueba con el calibre y ajusta el valor en el panel.
- **Profundidad automática**: si el conector es más largo que el grueso de la
  pieza, se avisa pero no se recorta solo. La longitud de la varilla la decide
  quien la compra.
- **Planos oblicuos**: los cortes son siempre perpendiculares a un eje.
- **Optimización del corte**: la rejilla reparte a distancias iguales sin mirar
  la forma. Puede caer en una zona delicada de la pieza; para eso está el corte
  manual.

El número de piezas que anuncia el plan es un máximo. Si el modelo no llena toda
la rejilla, las celdas sin material no producen pieza: la escuadra de ejemplo
sale en tres piezas y no en cuatro, porque la celda alta del brazo tumbado está
vacía.
- **Conectores dowel y alojamientos para imanes** (Fase 3): tolerancias,
  posicionado en la cara de corte, macho/hembra.
- **Numeración de piezas y metadatos** (Fase 4).
- **Exportación masiva de STL** (Fase 5) y lista de piezas (CSV/JSON).
- **Mapa de montaje** (Fase 6).
- **Orientación automática** de cada pieza para imprimir sin soportes.
- Escalado del modelo: `scale_to_fit()` existe en el núcleo y está probado, pero
  no está expuesto en la interfaz porque implicaría tocar el modelo.

### Limitaciones conocidas

- El soldado usa una rejilla de redondeo, no una búsqueda por distancia: dos
  puntos separados justo por el borde de una celda podrían no fundirse. Con las
  tolerancias por defecto y coordenadas repetidas de STL no se da.
- La detección automática de unidades falla con piezas muy pequeñas modeladas en
  mm (por debajo de 20 mm se interpretan como cm). Se corrige fijando la unidad.
- La estimación de piezas ignora la forma: una pieza en L de 420 mm puede
  necesitar menos cortes que los que dice la rejilla, o más si el corte tiene que
  esquivar geometría.
- El análisis de islas no distingue una cavidad interna de un trozo suelto.
- Probado por código en Blender 3.6+ vía API estable; queda pendiente la pasada
  manual de interfaz en tu instalación.

---

## Hoja de ruta

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Estructura, panel, perfiles, importación, análisis | **Hecha** |
| 2a | Plano de corte visible, sin cortar | **Hecha** |
| 2b | Un corte real: dos piezas nuevas | **Hecha** |
| 2c | Rejilla completa de N piezas | **Hecha** |
| 3a | Calcular y mostrar los conectores | **Hecha** |
| 3b | Perforar los agujeros | **Hecha** |
| 4 | Numeración grabada en la pieza | **Hecha** |
| 5 | Exportación de STL y lista de piezas | **Hecha** |
| 6 | Vista explotada para revisar el montaje | **Hecha** |

La Fase 2 se apoya en dos cosas que ya están listas: `check_fit()` /
`estimate_pieces()` para decidir la rejilla, y la garantía de que el modelo
original no se toca (las piezas serán objetos nuevos).

---

## Empaquetar una versión

```bash
python3 tools_build_zip.py     # deja el ZIP instalable en dist/
```

El manifiesto tiene que quedar en la raíz del ZIP: dentro de una carpeta,
Blender 4.2+ no lo reconoce como extensión.

## Contribuir

Antes de mandar un cambio:

```bash
python3 tests/run_tests.py                                    # obligatorio
blender --background --python tests/test_in_blender.py        # si tocas blender/
```

Dos reglas que mantienen esto sano:

- **`core/` no importa `bpy` ni `bmesh`.** Hay un test que falla si alguien lo
  intenta. Es lo que permite que la mayoría de los tests corran en segundos.
- **Nada modifica el modelo original.** Las piezas son objetos nuevos; el
  original solo se oculta. Hay tests que lo comprueban comparando el objeto
  antes y después.

Los comentarios del código explican el *porqué* de las decisiones, no lo que
hace el código.

## Estado y garantías

Funciona y está probado, pero es software joven y hay un número que no puede
salir de ningún test: **la holgura del agujero del dowel**. El valor por
defecto (0,2 mm diametrales) es el típico; el bueno depende de tu impresora,
tu boquilla y tu material. Imprime dos trozos de sección y compruébalo con el
calibre antes de fabricar en serio.

## Licencia

MIT. Úsalo, cámbialo y compártelo.
