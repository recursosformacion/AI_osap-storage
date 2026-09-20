"""Dry-run (read-only) de materialización `works_person_import` → `works_person_roles`.

Semántica observada: `resolved=1` ya materializado; `resolved=2` pendiente; `0` ruido.
Mapeo canónico: composer→rol 1, artist→rol 10.

Solo propone cuando el nombre casa con **una** persona (persons/persons_aliases) y es un nombre
válido. No escribe nada.

    .venv\\Scripts\\python.exe scripts/plan_wpi_materialization.py
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

ROLE_TARGET = {"composer": 1, "artist": 10}


def _mk(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def run(out_csv: Path, out_md: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    by_key: dict[str, set[str]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute("SELECT persons_id, persons_name FROM persons")
        for r in cur.fetchall():
            by_key[_mk(r["persons_name"])].add(r["persons_id"])
        cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        for r in cur.fetchall():
            if r["a"]:
                by_key[_mk(r["a"])].add(r["person_id"])
        cur.execute("SELECT works_id, works_person_import_name n, works_person_import_role role "
                    "FROM works_person_import WHERE works_person_import_role IN ('composer','artist')")
        rows = cur.fetchall()
        cur.execute("SELECT works_person_roles_work_id w, works_person_roles_role_id r "
                    "FROM works_person_roles WHERE works_person_roles_role_id IN (1,10)")
        have: dict[int, set[int]] = defaultdict(set)
        for r in cur.fetchall():
            have[r["w"]].add(r["r"])
    conn.close()

    stats = Counter()
    proposals: list[list] = []
    for r in rows:
        target = ROLE_TARGET[r["role"]]
        if target in have.get(r["works_id"], set()):
            stats[f"{r['role']}:ya_tiene"] += 1
            continue
        key = _mk(r["n"])
        matches = by_key.get(key, set())
        if not matches:
            stats[f"{r['role']}:sin_match"] += 1
            continue
        if len(matches) > 1:
            stats[f"{r['role']}:multiple"] += 1
            continue
        if not validar_nombre_compositor(r["n"])[0]:
            stats[f"{r['role']}:nombre_invalido"] += 1
            continue
        stats[f"{r['role']}:propuesta"] += 1
        proposals.append([r["works_id"], r["n"], r["role"], target, next(iter(matches))])

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["work_id", "import_name", "import_role", "target_role", "person_id"])
        writer.writerows(proposals)

    lines = ["# Dry-run: materializar `works_person_import` → `works_person_roles` (read-only)\n",
             "Mapeo: `composer`→rol 1, `artist`→rol 10. Solo nombre único y válido.\n",
             "| resultado | composer | artist |", "|---|---|---|"]
    for k in ("ya_tiene", "propuesta", "sin_match", "multiple", "nombre_invalido"):
        lines.append(f"| {k} | {stats.get(f'composer:{k}', 0)} | {stats.get(f'artist:{k}', 0)} |")
    lines += ["\n## Muestras\n", "| work_id | nombre | rol import → destino | persona |", "|---|---|---|---|"]
    for p in proposals[:30]:
        lines.append(f"| {p[0]} | {p[1]} | {p[2]}→{p[3]} | {p[4]} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("propuestas:", len(proposals), "| stats:", dict(stats))
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\wpi_materializacion.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "dry-run-wpi.md")
    args = ap.parse_args()
    run(args.csv, args.md)


if __name__ == "__main__":
    main()
