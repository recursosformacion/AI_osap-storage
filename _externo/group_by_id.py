"""
Agrupa los ensembles_code por ID_Canonico.

Entrada : _externo/auditoria_detalle.csv (salida del analisis, sin tocar la BD)
Salidas : _externo/agrupacion_id_canonico.md   (tabla Markdown pedida)
          _externo/agrupacion_id_canonico.csv  (misma informacion, delimitada por ;)
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
INVALID = "INVALID_OR_INSTRUMENTAL"
SOURCE = BASE / "auditoria_detalle.csv"


def escape(text: str) -> str:
    """Escapa los caracteres que romperian una celda Markdown."""
    return text.replace("|", "\\|").replace("\n", " ")


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))

    grupos: dict[str, list[str]] = defaultdict(list)
    existe: dict[str, str] = {}
    familia: dict[str, str] = {}
    for row in rows:
        canonico = row["ID_Canonico"]
        grupos[canonico].append(row["ensembles_code"])
        existe[canonico] = row["Existe_en_Tabla"]
        familia[canonico] = row["etiqueta_familia"]

    # primero los grupos mas poblados; a igualdad, orden alfabetico del ID
    orden = sorted(grupos, key=lambda k: (-len(grupos[k]), k))

    lineas = [
        "| id_canonico | existe_en_tabla | n_ensembles_codes | ensembles_codes |",
        "|---|---|---|---|",
    ]
    for canonico in orden:
        codigos = grupos[canonico]
        lineas.append(
            f"| {escape(canonico)} | {existe[canonico]} | {len(codigos)} | "
            f"{escape(', '.join(codigos))} |"
        )
    (BASE / "agrupacion_id_canonico.md").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8")

    with (BASE / "agrupacion_id_canonico.csv").open(
            "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["id_canonico", "existe_en_tabla", "n_ensembles_codes",
                         "etiqueta_familia", "ensembles_codes"])
        for canonico in orden:
            writer.writerow([
                canonico, existe[canonico], len(grupos[canonico]),
                familia[canonico], ", ".join(grupos[canonico]),
            ])

    print(f"grupos (ID canonicos distintos): {len(orden)}")
    print(f"codigos folding agrupados       : {len(rows)}")
    print(f"INVALID_or_instrumental         : "
          f"{len(grupos.get(INVALID, []))} codigos en un unico grupo")
    print("\n15 grupos mas poblados:")
    for canonico in orden[:15]:
        print(f"  {len(grupos[canonico]):5d}  {canonico}")
    print("\n15 grupos de un solo ensembles_code (codigos canonicos ya "
          "normalizados):")
    singleton = [c for c in orden if len(grupos[c]) == 1]
    for canonico in singleton[:15]:
        print(f"  {canonico:<22} {grupos[canonico][0]}")
    print(f"  ... total singletons: {len(singleton)}")


if __name__ == "__main__":
    main()