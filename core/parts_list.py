"""Lista de piezas: la hoja que acompaña a los STL.

Sirve para saber qué hay que imprimir, en qué orden montarlo y cuánto material
hace falta, sin tener que abrir los ficheros uno a uno.
"""

import csv
import io
from dataclasses import dataclass
from typing import List, Sequence

COLUMNS = (
    "pieza",
    "fichero",
    "ancho_mm",
    "fondo_mm",
    "alto_mm",
    "volumen_cm3",
    "cerrada",
    "cabe",
    "conectores",
)


@dataclass
class PartRow:
    index: int
    name: str
    filename: str
    dimensions_mm: Sequence[float]
    volume_cm3: float
    watertight: bool
    fits: bool
    connectors: int = 0

    def as_row(self) -> List[str]:
        dx, dy, dz = self.dimensions_mm
        return [
            str(self.index),
            self.filename,
            f"{dx:.2f}",
            f"{dy:.2f}",
            f"{dz:.2f}",
            f"{self.volume_cm3:.2f}",
            "sí" if self.watertight else "no",
            "sí" if self.fits else "no",
            str(self.connectors),
        ]


def csv_text(rows: Sequence[PartRow], delimiter: str = ";") -> str:
    """CSV con punto y coma, que es lo que abre bien Excel en español."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=delimiter, lineterminator="\n")
    escritor.writerow(COLUMNS)
    for fila in rows:
        escritor.writerow(fila.as_row())
    return salida.getvalue()


def total_volume_cm3(rows: Sequence[PartRow]) -> float:
    return sum(fila.volume_cm3 for fila in rows)


def summary(rows: Sequence[PartRow]) -> str:
    if not rows:
        return "Sin piezas"
    sin_cerrar = sum(1 for f in rows if not f.watertight)
    sin_caber = sum(1 for f in rows if not f.fits)
    texto = f"{len(rows)} piezas, {total_volume_cm3(rows):.1f} cm³ de material"
    if sin_cerrar:
        texto += f", {sin_cerrar} sin cerrar"
    if sin_caber:
        texto += f", {sin_caber} que no caben"
    return texto
