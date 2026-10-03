"""Conectores: dónde caben y cuántos, dada la sección de corte.

Todo esto es geometría 2D en el plano del corte, así que es Python puro y se
prueba sin Blender. El criterio es siempre el mismo para dowels e imanes:
solo cambian el diámetro, la profundidad y la holgura.

Reglas que gobiernan la colocación:

- Un conector necesita material alrededor. El punto debe estar a
  `radio del agujero + pared` del borde de la sección, o se reventaría la
  pared al imprimir.
- Dos conectores separados impiden que la pieza gire sobre el eje del
  conector. Con uno solo, las mitades pivotan.
- Cuantos más quepan, mejor reparto de esfuerzos, pero hay un tope: llenar la
  sección de agujeros la debilita y alarga la impresión.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]

DOWEL = "DOWEL"
MAGNET = "MAGNET"


@dataclass(frozen=True)
class ConnectorSpec:
    """Un tipo de conector, en milímetros.

    `clearance` es la holgura diametral del agujero: el dowel de 3 mm entra en
    un agujero de 3,2. Para un imán la holgura es menor porque va pegado y no
    tiene que deslizar.
    """

    kind: str
    name: str
    diameter: float
    depth: float
    clearance: float = 0.2
    wall: float = 2.0

    def __post_init__(self) -> None:
        if self.diameter <= 0 or self.depth <= 0:
            raise ValueError("Diámetro y profundidad deben ser positivos")
        if self.clearance < 0 or self.wall < 0:
            raise ValueError("Holgura y pared no pueden ser negativas")

    @property
    def hole_diameter(self) -> float:
        return self.diameter + self.clearance

    @property
    def hole_radius(self) -> float:
        return self.hole_diameter * 0.5

    @property
    def required_clearance(self) -> float:
        """Distancia mínima del centro al borde de la sección."""
        return self.hole_radius + self.wall

    @property
    def spacing(self) -> float:
        """Separación mínima entre centros.

        Dos agujeros pegados dejan un tabique finísimo entre ellos, así que se
        exige el doble del hueco que ocupa uno.
        """
        return self.hole_diameter + 2.0 * self.wall

    @property
    def label(self) -> str:
        tipo = "imán" if self.kind == MAGNET else "dowel"
        return f"{self.name} ({tipo} ⌀{self.diameter:g} × {self.depth:g} mm)"


def magnet(diameter: float, thickness: float, clearance: float = 0.1, wall: Optional[float] = None) -> ConnectorSpec:
    """Imán de disco de neodimio. El alojamiento es un pelín más hondo que el
    imán para que quede enrasado o ligeramente hundido y no impida el contacto."""
    return ConnectorSpec(
        kind=MAGNET,
        name=f"{diameter:g}×{thickness:g}",
        diameter=diameter,
        depth=thickness + 0.2,
        clearance=clearance,
        wall=wall_for(diameter, wall, 0.25),
    )


def dowel(diameter: float, length: float, clearance: float = 0.2, wall: Optional[float] = None) -> ConnectorSpec:
    """Dowel suelto: el agujero se hace en las dos piezas, con la mitad de la
    varilla en cada una."""
    return ConnectorSpec(
        kind=DOWEL,
        name=f"⌀{diameter:g}",
        diameter=diameter,
        depth=length * 0.5,
        clearance=clearance,
        wall=wall_for(diameter, wall, 0.6),
    )


#: Medidas corrientes de imán de disco de neodimio (las pequeñas, para figuras).
MAGNET_SIZES = ((3.0, 1.0), (3.0, 2.0), (4.0, 2.0), (4.0, 3.0), (5.0, 2.0), (5.0, 3.0),
                (6.0, 2.0), (6.0, 3.0), (8.0, 3.0), (10.0, 3.0), (12.0, 3.0))


def wall_from_nozzle(nozzle: float) -> float:
    """Pared mínima alrededor de un agujero: unos 2,5 perímetros de la boquilla
    (0,4 → 1,0 mm; 0,25 → 0,6 mm; 0,6 → 1,5 mm)."""
    return round(max(0.5, 2.5 * float(nozzle)), 2)


def wall_for(diameter: float, wall: Optional[float], ratio: float) -> float:
    """Pared de un conector: la indicada (de la boquilla) y, si no se indica,
    la regla antigua (1,5 mm o una fracción del diámetro). Con pared indicada se
    respeta: es el usuario quien conoce su impresora."""
    if wall is not None and wall > 0:
        return float(wall)
    return max(1.5, diameter * ratio)

#: Dowels habituales. El filamento de 1,75 es el que siempre está a mano.
DOWEL_SIZES = ((1.75, 16.0), (3.0, 20.0), (4.0, 24.0), (5.0, 30.0), (6.0, 30.0))


# --------------------------------------------------------------------------
# Geometría de la sección
# --------------------------------------------------------------------------


@dataclass
class Section:
    """Sección de corte: uno o varios contornos cerrados en 2D.

    Los agujeros interiores se tratan con la regla par-impar, así que no hace
    falta distinguir contorno exterior de agujero: un punto dentro de dos
    contornos está en un agujero y queda fuera del material.
    """

    loops: List[List[Vec2]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.loops = [list(loop) for loop in self.loops if len(loop) >= 3]

    @property
    def is_empty(self) -> bool:
        return not self.loops

    def bounds(self) -> Tuple[Vec2, Vec2]:
        us = [p[0] for loop in self.loops for p in loop]
        vs = [p[1] for loop in self.loops for p in loop]
        return (min(us), min(vs)), (max(us), max(vs))

    def area(self) -> float:
        """Área real del material.

        Un contorno metido dentro de otro es un agujero y resta, esté dibujado
        en el sentido que esté. Tiene que ser el mismo criterio que `contains`,
        o el área y la colocación dirían cosas distintas de la misma sección.
        """
        total = 0.0
        for i, loop in enumerate(self.loops):
            profundidad = sum(
                1
                for j, otro in enumerate(self.loops)
                if j != i and _point_in_loop(loop[0], otro)
            )
            signo = -1.0 if profundidad % 2 else 1.0
            total += signo * abs(_loop_area(loop))
        return abs(total)

    def contains(self, point: Vec2) -> bool:
        dentro = False
        for loop in self.loops:
            if _point_in_loop(point, loop):
                dentro = not dentro
        return dentro

    def distance_to_edge(self, point: Vec2) -> float:
        mejor = float("inf")
        for loop in self.loops:
            n = len(loop)
            for i in range(n):
                d = _point_segment_distance(point, loop[i], loop[(i + 1) % n])
                if d < mejor:
                    mejor = d
        return mejor

    def clearance_at(self, point: Vec2) -> float:
        """Cuánto material hay alrededor del punto. Cero si cae fuera."""
        if not self.contains(point):
            return 0.0
        return self.distance_to_edge(point)


def _loop_area(loop: Sequence[Vec2]) -> float:
    total = 0.0
    n = len(loop)
    for i in range(n):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total * 0.5


def _point_in_loop(point: Vec2, loop: Sequence[Vec2]) -> bool:
    """Lanzamiento de rayo horizontal, regla par-impar."""
    x, y = point
    dentro = False
    n = len(loop)
    for i in range(n):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            corte = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if corte > x:
                dentro = not dentro
    return dentro


def _point_segment_distance(point: Vec2, a: Vec2, b: Vec2) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    largo2 = dx * dx + dy * dy
    if largo2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / largo2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# --------------------------------------------------------------------------
# Colocación
# --------------------------------------------------------------------------


@dataclass
class Placement:
    """Resultado de colocar conectores en una sección."""

    spec: ConnectorSpec
    points: List[Vec2] = field(default_factory=list)
    section_area: float = 0.0
    best_clearance: float = 0.0
    reason: str = ""

    @property
    def count(self) -> int:
        return len(self.points)

    @property
    def ok(self) -> bool:
        return bool(self.points)

    @property
    def prevents_rotation(self) -> bool:
        """Con un solo conector las piezas pueden girar sobre su eje."""
        return self.count >= 2

    def describe(self) -> str:
        if not self.ok:
            return f"No cabe ningún {self.spec.label}: {self.reason}"
        aviso = "" if self.prevents_rotation else " (solo uno: la pieza puede girar)"
        return f"{self.count} × {self.spec.label}{aviso}"


def candidate_points(
    section: Section, spec: ConnectorSpec, step: Optional[float] = None
) -> List[Tuple[Vec2, float]]:
    """Puntos de una rejilla que tienen material suficiente alrededor.

    Se muestrea en rejilla en lugar de calcular el polígono erosionado de
    verdad: es mucho más simple, y con un paso fino la diferencia es
    despreciable para colocar unos pocos agujeros.
    """
    if section.is_empty:
        return []

    necesario = spec.required_clearance
    puntos: List[Tuple[Vec2, float]] = []
    for punto in _grid(section, necesario, step):
        holgura = section.clearance_at(punto)
        if holgura >= necesario:
            puntos.append((punto, holgura))
    return puntos


def place_connectors(
    section: Section,
    spec: ConnectorSpec,
    max_count: int = 4,
    step: Optional[float] = None,
    avoid: Optional[Sequence[Vec2]] = None,
) -> Placement:
    """Reparte hasta `max_count` conectores lo más separados posible.

    Se empieza por el punto con más material alrededor (el más seguro) y luego
    se van añadiendo los que estén más lejos de los ya elegidos. Es la
    estrategia que maximiza la resistencia al giro con pocos puntos.

    `avoid` son puntos ya ocupados por otros conectores: sirve para poner
    dowels e imanes en la misma sección sin que se pisen.
    """
    resultado = Placement(spec=spec, section_area=section.area())

    if section.is_empty:
        resultado.reason = "la sección está vacía"
        return resultado

    candidatos = candidate_points(section, spec, step)
    if avoid:
        # Un conector ajeno ocupa su hueco y su pared: se descartan los
        # candidatos que caerían encima o demasiado cerca.
        candidatos = [
            (punto, holgura)
            for punto, holgura in candidatos
            if all(_dist(punto, ocupado) >= spec.spacing for ocupado in avoid)
        ]
    if not candidatos:
        mejor = _best_clearance(section, step)
        resultado.best_clearance = mejor
        resultado.reason = (
            f"hace falta {spec.required_clearance:.1f} mm de material alrededor "
            f"y el mejor punto solo tiene {mejor:.1f} mm"
        )
        return resultado

    candidatos.sort(key=lambda item: item[1], reverse=True)
    resultado.best_clearance = candidatos[0][1]

    elegidos: List[Vec2] = [candidatos[0][0]]
    separacion = spec.spacing

    while len(elegidos) < max_count:
        mejor_punto = None
        mejor_distancia = 0.0
        for punto, _holgura in candidatos:
            distancia = min(_dist(punto, otro) for otro in elegidos)
            if distancia >= separacion and distancia > mejor_distancia:
                mejor_distancia = distancia
                mejor_punto = punto
        if mejor_punto is None:
            break
        elegidos.append(mejor_punto)

    resultado.points = elegidos
    return resultado


def _grid(section: Section, size: float, step: Optional[float] = None, max_samples: int = 40000):
    """Rejilla de muestreo centrada en la sección.

    Antes la rejilla empezaba en una esquina con un paso de medio conector, y en
    una sección estrecha (la cintura de una figura) se saltaba justo la línea
    central, el único sitio donde cabía el imán: decía «no cabe» sin ser
    verdad. Ahora el paso también depende del lado corto y la rejilla pasa por
    el centro, así que un rectángulo estrecho siempre se muestrea por su eje.
    """
    (min_u, min_v), (max_u, max_v) = section.bounds()
    ancho, alto = max_u - min_u, max_v - min_v
    if step is None:
        corto = max(min(ancho, alto), 1e-6)
        step = max(0.2, min(size * 0.5, 4.0, corto / 16.0))
        while (ancho / step + 1) * (alto / step + 1) > max_samples:
            step *= 1.5
    cu, cv = (min_u + max_u) * 0.5, (min_v + max_v) * 0.5
    nu, nv = int(ancho * 0.5 / step) + 1, int(alto * 0.5 / step) + 1
    for i in range(-nu, nu + 1):
        u = cu + i * step
        if u < min_u or u > max_u:
            continue
        for j in range(-nv, nv + 1):
            v = cv + j * step
            if min_v <= v <= max_v:
                yield (u, v)


def _best_clearance(section: Section, step: Optional[float]) -> float:
    """Mejor holgura disponible, para poder explicar por qué no cabe nada."""
    if section.is_empty:
        return 0.0
    return max((section.clearance_at(p) for p in _grid(section, 2.0, step)), default=0.0)


def _dist(a: Vec2, b: Vec2) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def fitting_sizes(section: Section, sizes: Sequence[Tuple[float, float]], kind: str = MAGNET,
                  wall: Optional[float] = None, max_count: int = 4):
    """Qué medidas de la lista caben en esta sección, de mayor a menor.

    Sirve para responder a "qué imán le pongo": se prueban las medidas
    corrientes y se devuelve cuántos entrarían de cada una.
    """
    fabricar = magnet if kind == MAGNET else dowel
    salida = []
    for diametro, grosor in sorted(sizes, reverse=True):
        spec = fabricar(diametro, grosor, wall=wall)
        colocacion = place_connectors(section, spec, max_count)
        salida.append((spec, colocacion.count))
    return salida


def best_fitting(section: Section, sizes: Sequence[Tuple[float, float]], kind: str = MAGNET,
                 wall: Optional[float] = None):
    """La medida más grande que cabe (al menos uno), o None. Para el aviso
    «no cabe 5×2; sí cabe 3×2»."""
    for spec, count in fitting_sizes(section, sizes, kind, wall, max_count=1):
        if count >= 1:
            return spec
    return None


def cutter_cylinders_plane(points: Sequence[Vec2], plane, spec: "ConnectorSpec", segments: int = 24):
    """Como `cutter_cylinders`, para un plano con cualquier orientación (línea de corte)."""
    radio = spec.hole_radius
    mitad = spec.depth
    vertices: List[Tuple[float, float, float]] = []
    triangulos: List[Tuple[int, int, int]] = []
    for centro in points:
        base = len(vertices)
        for desplazamiento in (-mitad, mitad):
            for s in range(segments):
                ang = 2.0 * math.pi * s / segments
                vertices.append(plane.to_3d((centro[0] + radio * math.cos(ang), centro[1] + radio * math.sin(ang)), desplazamiento))
        cb = len(vertices); vertices.append(plane.to_3d(centro, -mitad))
        ct = len(vertices); vertices.append(plane.to_3d(centro, mitad))
        for s in range(segments):
            n = (s + 1) % segments
            b0, b1, t0, t1 = base + s, base + n, base + segments + s, base + segments + n
            triangulos += [(b0, b1, t1), (b0, t1, t0), (cb, b1, b0), (ct, t0, t1)]
    return vertices, triangulos


def cutter_cylinders(
    points: Sequence[Vec2],
    axis: int,
    position: float,
    spec: ConnectorSpec,
    segments: int = 24,
):
    """Cilindros que materializan los agujeros, centrados en el plano de corte.

    Se construye un único cilindro por conector, de longitud doble de la
    profundidad y centrado en el plano: así el mismo cilindro perfora las dos
    piezas a la vez, cada una a su profundidad. Evita tener que emparejar
    agujero con agujero y garantiza que quedan alineados.

    Devuelve (vértices, triángulos) en coordenadas de mundo.
    """
    from .sections import to_3d

    radio = spec.hole_radius
    mitad = spec.depth
    u_axis, v_axis = ((1, 2), (2, 0), (0, 1))[axis]

    vertices: List[Tuple[float, float, float]] = []
    triangulos: List[Tuple[int, int, int]] = []

    for centro in points:
        base = len(vertices)
        for lado, desplazamiento in ((0, -mitad), (1, mitad)):
            for s in range(segments):
                angulo = 2.0 * math.pi * s / segments
                punto2d = (
                    centro[0] + radio * math.cos(angulo),
                    centro[1] + radio * math.sin(angulo),
                )
                punto = list(to_3d(punto2d, axis, position + desplazamiento))
                vertices.append((punto[0], punto[1], punto[2]))

        centro_bajo = len(vertices)
        vertices.append(to_3d(centro, axis, position - mitad))
        centro_alto = len(vertices)
        vertices.append(to_3d(centro, axis, position + mitad))

        for s in range(segments):
            siguiente = (s + 1) % segments
            b0, b1 = base + s, base + siguiente
            t0, t1 = base + segments + s, base + segments + siguiente
            triangulos.append((b0, b1, t1))
            triangulos.append((b0, t1, t0))
            triangulos.append((centro_bajo, b1, b0))
            triangulos.append((centro_alto, t0, t1))

    return vertices, triangulos
