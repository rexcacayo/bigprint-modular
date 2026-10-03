"""Planos de corte con cualquier orientación.

Un plano de BigPrint era siempre perpendicular a un eje (X, Y o Z) y se guardaba
como «eje,posición». Con la línea de corte dibujada sobre el modelo el plano
puede estar inclinado, así que aquí vive la versión general: origen + normal y
una base (u, v) para pasar del plano a 2D y volver.

Para un plano de eje se usa la misma base que `sections.plane_axes`, de modo que
las coordenadas 2D coinciden con las de siempre.

Python puro, sin numpy: se puede probar fuera de Blender.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]
Vec2 = Tuple[float, float]

_AXES = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _cross(a, b) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a) -> Vec3:
    n = math.sqrt(_dot(a, a))
    if n < 1e-12:
        raise ValueError("Vector nulo")
    return (a[0] / n, a[1] / n, a[2] / n)


@dataclass(frozen=True)
class Plane:
    origin: Vec3
    normal: Vec3
    u: Vec3
    v: Vec3
    axis: Optional[int] = None     # 0/1/2 si es un plano de eje, None si está inclinado

    # ------------------------------------------------------------------ crear
    @staticmethod
    def from_axis(axis: int, position: float) -> "Plane":
        u_axis, v_axis = ((1, 2), (2, 0), (0, 1))[axis]
        origin = [0.0, 0.0, 0.0]
        origin[axis] = float(position)
        return Plane(tuple(origin), _AXES[axis], _AXES[u_axis], _AXES[v_axis], axis)

    @staticmethod
    def from_normal(origin: Sequence[float], normal: Sequence[float]) -> "Plane":
        n = _norm(tuple(float(c) for c in normal))
        # Si la normal es (casi) la de un eje, se trata como plano de eje: así los
        # cortes que se dibujan rectos se comportan exactamente igual que antes.
        for axis, e in enumerate(_AXES):
            if abs(abs(_dot(n, e)) - 1.0) < 1e-9:
                pos = _dot(tuple(origin), e)
                if _dot(n, e) > 0:
                    return Plane.from_axis(axis, pos)
        ref = _AXES[0] if abs(n[0]) < 0.9 else _AXES[1]
        u = _norm(_cross(ref, n))
        v = _cross(n, u)
        return Plane(tuple(float(c) for c in origin), n, u, v, None)

    # ------------------------------------------------------------------ usar
    @property
    def offset(self) -> float:
        return _dot(self.origin, self.normal)

    def distance(self, p: Sequence[float]) -> float:
        return _dot(_sub(p, self.origin), self.normal)

    def to_2d(self, p: Sequence[float]) -> Vec2:
        d = _sub(p, self.origin)
        if self.axis is not None:
            # Mismas coordenadas absolutas que el código de siempre (sin restar origen).
            u_axis, v_axis = ((1, 2), (2, 0), (0, 1))[self.axis]
            return (float(p[u_axis]), float(p[v_axis]))
        return (_dot(d, self.u), _dot(d, self.v))

    def to_3d(self, q: Sequence[float], along: float = 0.0) -> Vec3:
        if self.axis is not None:
            u_axis, v_axis = ((1, 2), (2, 0), (0, 1))[self.axis]
            out = [0.0, 0.0, 0.0]
            out[self.axis] = self.origin[self.axis] + along
            out[u_axis] = q[0]
            out[v_axis] = q[1]
            return (out[0], out[1], out[2])
        p = _add(self.origin, _add(_mul(self.u, q[0]), _mul(self.v, q[1])))
        return _add(p, _mul(self.normal, along))

    def scaled(self, factor: float) -> "Plane":
        """El mismo plano con el origen escalado (p. ej. de unidades de Blender a mm)."""
        return Plane(_mul(self.origin, factor), self.normal, self.u, self.v, self.axis)

    def label(self) -> str:
        if self.axis is not None:
            return f"{'XYZ'[self.axis]} = {self.origin[self.axis]:.0f}"
        return "línea"

    # ------------------------------------------------------------------ guardar
    def serialize(self) -> str:
        if self.axis is not None:
            return f"{self.axis},{self.origin[self.axis]}"
        o, n = self.origin, self.normal
        return "P," + ",".join(f"{c:.6f}" for c in (*o, *n))

    @staticmethod
    def parse(line: str) -> "Plane":
        parts = line.strip().split(",")
        if parts[0] == "P":
            vals = [float(x) for x in parts[1:7]]
            return Plane.from_normal(vals[:3], vals[3:6])
        return Plane.from_axis(int(parts[0]), float(parts[1]))


# --------------------------------------------------------------------------- ajuste
def _jacobi_eigen(m: List[List[float]], sweeps: int = 50):
    """Autovalores y autovectores de una matriz simétrica 3×3 (Jacobi)."""
    a = [row[:] for row in m]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(sweeps):
        off = abs(a[0][1]) + abs(a[0][2]) + abs(a[1][2])
        if off < 1e-15:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if abs(a[p][q]) < 1e-18:
                continue
            theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
            t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
            c = 1.0 / math.sqrt(t * t + 1.0)
            s = t * c
            for k in range(3):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = c * akp - s * akq
                a[k][q] = s * akp + c * akq
            for k in range(3):
                apk, aqk = a[p][k], a[q][k]
                a[p][k] = c * apk - s * aqk
                a[q][k] = s * apk + c * aqk
            for k in range(3):
                vkp, vkq = v[k][p], v[k][q]
                v[k][p] = c * vkp - s * vkq
                v[k][q] = s * vkp + c * vkq
    values = [a[i][i] for i in range(3)]
    vectors = [(v[0][i], v[1][i], v[2][i]) for i in range(3)]
    return values, vectors


def fit_plane(points: Sequence[Sequence[float]]):
    """Plano que mejor pasa por los puntos de la línea dibujada.

    Devuelve (plano, desviación máxima en las mismas unidades que los puntos).
    La normal es la dirección en la que los puntos varían menos (PCA).
    """
    pts = [tuple(float(c) for c in p) for p in points]
    if len(pts) < 3:
        raise ValueError("Hacen falta al menos tres puntos para la línea de corte")
    n = len(pts)
    c = (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)
    cov = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        d = _sub(p, c)
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    values, vectors = _jacobi_eigen(cov)
    order = sorted(range(3), key=lambda i: values[i])
    if values[order[1]] < 1e-12 * max(values[order[2]], 1e-12):
        raise ValueError("Los puntos están en línea recta: rodea la pieza con la línea")
    normal = _norm(vectors[order[0]])
    # Normal hacia el lado positivo del eje dominante: así «lado alto» sigue
    # significando arriba / derecha / detrás como en los cortes de eje.
    dom = max(range(3), key=lambda i: abs(normal[i]))
    if normal[dom] < 0:
        normal = _mul(normal, -1.0)
    plane = Plane.from_normal(c, normal)
    dev = max(abs(plane.distance(p)) for p in pts)
    return plane, dev


def snap_to_axis(plane: "Plane", max_degrees: float = 3.0) -> "Plane":
    """Si el plano está casi recto (a menos de `max_degrees` de un eje), lo
    endereza: una línea dibujada a mano nunca sale perfecta y un corte recto
    deja caras más limpias y conectores mejor alineados."""
    limite = math.cos(math.radians(max_degrees))
    for axis, e in enumerate(_AXES):
        if abs(_dot(plane.normal, e)) >= limite:
            return Plane.from_axis(axis, _dot(plane.origin, e))
    return plane


def tilt_degrees(plane: "Plane") -> float:
    """Ángulo entre el plano y el plano de eje más cercano (0 = recto)."""
    mejor = max(abs(_dot(plane.normal, e)) for e in _AXES)
    return math.degrees(math.acos(min(1.0, mejor)))
