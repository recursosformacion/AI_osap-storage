"""Diagnóstico read-only de `works_person_import` ↔ `persons` (semántica y enlace).

No escribe nada. Determina: qué significa cada rol y el flag `resolved`, qué correspondencias a
`persons` existen, duplicados/ambigüedades, y qué relación debería acabar en `works_person_roles`.

    .venv\\Scripts\\python.exe scripts/diagnose_works_person_import.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from domain.services.composer_quality import validar_nombre_compositor  # noqa: E402


def _mk(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def run(out_csv: Path, out_md: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SELECT works_person_import_name n, works_person_import_role r, "
                    "works_person_import_source s, works_person_import_resolved res, "
                    "COUNT(DISTINCT works_id) obras, COUNT(*) filas "
                    "FROM works_person_import GROUP BY 1,2,3,4")
        groups = cur.fetchall()
        cur.execute("SELECT persons_id, persons_name FROM persons")
        by_key: dict[str, set[str]] = defaultdict(set)
        for row in cur.fetchall():
            by_key[_mk(row["persons_name"])].add(row["persons_id"])
        cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        for row in cur.fetchall():
            if row["a"]:
                by_key[_mk(row["a"])].add(row["person_id"])
        cur.execute("SELECT works_person_roles_work_id w, works_person_roles_role_id r "
                    "FROM works_person_roles WHERE works_person_roles_role_id IN (1,10)")
        existing: dict[int, set[int]] = defaultdict(set)
        for row in cur.fetchall():
            existing[row["w"]].add(row["r"])
    conn.close()

    stats = Counter()
    detail = []
    for g in groups:
        key = _mk(g["n"])
        matches = by_key.get(key, set())
        valid = bool(validar_nombre_compositor(g["n"])[0]) if g["n"] else False
        kind = ("unico" if len(matches) == 1 else "multiple" if matches else "sin_match")
        stats[f"{g['r']}:{g['res']}:{kind}"] += 1
        stats[f"filas:{g['r']}:{g['res']}"] += g["filas"]
        detail.append({
            "name": g["n"], "role": g["r"], "source": g["s"], "resolved": g["res"],
            "obras": g["obras"], "filas": g["filas"], "match": kind,
            "n_personas": len(matches), "persona": next(iter(matches)) if len(matches) == 1 else "",
            "nombre_valido": valid,
        })

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(detail[0].keys()))
        writer.writeheader()
        writer.writerows(detail)

    lines = ["# Diagnóstico `works_person_import` ↔ `persons` (read-only)\n",
             f"- Obras con rol 1/10 en `works_person_roles`: **{len(existing)}**\n",
             "## Distribución (combinaciones nombre/rol/source/resolved)\n"]
    for role in ("composer", "artist"):
        lines.append(f"\n### rol `{role}`\n")
        lines.append("| resolved | únicos | múltiples | sin match |")
        lines.append("|---|---|---|---|")
        for res in sorted({d["resolved"] for d in detail if d["role"] == role}):
            lines.append(f"| {res} | {stats.get(f'{role}:{res}:unico', 0)} | "
                         f"{stats.get(f'{role}:{res}:multiple', 0)} | {stats.get(f'{role}:{res}:sin_match', 0)} |")
    lines += ["\n## Filas por rol/resolved\n", "| clave | filas |", "|---|---|"]
    for k, v in sorted(stats.items()):
        if k.startswith("filas:"):
            lines.append(f"| {k} | {v} |")
    lines += ["\n## Muestra\n", "| nombre | rol | resolved | obras | match | persona |",
              "|---|---|---|---|---|---|"]
    for d in sorted(detail, key=lambda x: -x["obras"])[:40]:
        persona = d["persona"] or "—"
        lines.append(f"| {d['name']} | {d['role']} | {d['resolved']} | {d['obras']} | "
                     f"{d['match']} | {persona} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("grupos:", len(groups))
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\wpi_diagnostico.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "wpi-diagnostico.md")
    args = ap.parse_args()
    run(args.csv, args.md)


if __name__ == "__main__":
    main()
