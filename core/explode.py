"""Vista explotada: separar las piezas para verlas todas a la vez.

Cada pieza se aleja del centro del conjunto en la dirección en la que ya está,
proporcionalmente a lo lejos que esté. Así el despiece conserva la disposición
del montaje: lo que estaba arriba sigue arriba, y se ve de un vistazo qué cara
encaja con cuál.

No se toca ninguna malla: esto son solo desplazamientos.
"""

from typing import List, Sequence, Tuple

Vec3 = Tuple[float, float, float]

#: Por debajo de esto, la pieza está prácticamente en el centro y no tiene
#: una dirección clara hacia donde salir.
CENTER_EPSILON = 1e-6


def assembly_center(centers: Sequence[Vec3]) -> Vec3:
    """Centro del conjunto, como media de los centros de las piezas.

    Se usa la media y no el centro de la caja envolvente para que una pieza
    grande no arrastre el centro hacia su lado.
    """
    if not centers:
        return (0.0, 0.0, 0.0)
    n = float(len(centers))
    return (
        sum(c[0] for c in centers) / n,
        sum(c[1] for c in centers) / n,
        sum(c[2] for c in centers) / n,
    )


def explode_offsets(centers: Sequence[Vec3], factor: float = 0.5) -> List[Vec3]:
    """Desplazamiento de cada pieza para el factor dado.

    Con factor 0 nada se mueve (montado); con 1 cada pieza dobla su distancia
    al centro.
    """
    centro = assembly_center(centers)
    salida: List[Vec3] = []

    for indice, punto in enumerate(centers):
        direccion = (
            punto[0] - centro[0],
            punto[1] - centro[1],
            punto[2] - centro[2],
        )
        largo = (direccion[0] ** 2 + direccion[1] ** 2 + direccion[2] ** 2) ** 0.5
        if largo < CENTER_EPSILON:
            # Una pieza justo en el centro no sabría hacia dónde salir: se
            # reparten en vertical por orden para que no queden solapadas.
            salida.append((0.0, 0.0, indice * factor * 10.0))
            continue
        salida.append(
            (direccion[0] * factor, direccion[1] * factor, direccion[2] * factor)
        )

    return salida
