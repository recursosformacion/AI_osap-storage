"""Dry-run read-only: rellenar `works_song_name` vacío a partir de `works_title`.

Propone `song_name` cuando `works_title` contiene ' - ' y el sufijo es el compositor (rol 1) o un
nombre de persona plausible. No escribe nada.

    .venv\\Scripts\\python.exe scripts/propose_song_name.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from domain.services.composer_quality import validar_nombre_compositor  # noqa: E402


def _valid(text: str | None) -> bool:
    return bool(text) and bool(validar_nombre_compositor(text)[0])


def run(out_csv: Path, out_md: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT w.id, w.works_title t, w.works_origin o, "
            " (SELECT p.persons_name FROM works_person_roles r JOIN persons p "
            "    ON p.persons_id=r.works_person_roles_person_id "
            "   WHERE r.works_person_roles_work_id=w.id AND r.works_person_roles_role_id=1 LIMIT 1) composer "
            "FROM works w WHERE w.works_song_name IS NULL OR w.works_song_name=''")
        rows = cur.fetchall()
    conn.close()

    proposals, counts = [], Counter()
    for r in rows:
        title = r["t"] or ""
        counts["vacios"] += 1
        composer = r["composer"]
        song = title
        if " - " in title:
            prefix, suffix = (p.strip() for p in title.rsplit(" - ", 1))
            if composer and norm(suffix) == norm(composer):
                counts["sufijo_igual_compositor"] += 1
                song = prefix
            elif _valid(suffix):
                counts["sufijo_persona"] += 1
                song = prefix
            else:
                counts["sufijo_no_persona"] += 1
        else:
            counts["sin_separador"] += 1
        proposals.append([r["id"], title, composer or "", song])
        counts["propuestas"] += 1

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["work_id", "works_title", "composer", "song_name_propuesto"])
        writer.writerows(proposals)
    lines = ["# Dry-run: relleno de `works_song_name` (read-only)\n",
             f"- Vacíos: **{len(rows)}**",
             f"- **Propuestas: {counts['propuestas']}**",
             f"- Sin separador ' - ': {counts['sin_separador']}",
             f"- Sufijo = compositor: {counts['sufijo_igual_compositor']} · sufijo persona: {counts['sufijo_persona']}",
             f"- Sufijo no-persona (descartado): {counts['sufijo_no_persona']}\n",
             "## Muestras\n",
             "| work_id | works_title | propuesto |", "|---|---|---|"]
    for p in proposals[:25]:
        lines.append(f"| {p[0]} | {p[1]} | {p[3]} |")
    lines += ["\n## Revert\n", "`UPDATE works SET works_song_name=NULL WHERE id IN (...)` sobre el CSV."]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("vacíos:", len(rows), "| propuestas:", len(proposals), "| conteos:", dict(counts))
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\song_name_proposals.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "dry-run-song-name.md")
    args = ap.parse_args()
    run(args.csv, args.md)


if __name__ == "__main__":
    main()
