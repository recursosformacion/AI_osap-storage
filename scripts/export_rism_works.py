"""Exporta las "obras" RISM con identidad estricta y mide cuántas son nuevas (read-only).

Identidad estricta: título uniforme (`240`) + persona canónica, excluyendo anónimos y títulos
genéricos (Mass, Sonata, Aria…). Deja la fuente completa en CSV y resume nuevas vs ya existentes.

    .venv\\Scripts\\python.exe scripts/export_rism_works.py
    .venv\\Scripts\\python.exe scripts/export_rism_works.py --out G:\\rism\\rism_works_strict.csv
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from domain.services.title_evidence import significant_tokens  # noqa: E402

ANON = {"anonymus", "anonym", "anon", "anonymous", "unknown", "unbekannt", "desconocido"}

GROUP_SQL = """
SELECT COALESCE(p.rism_canonical_id, s.rism_composer_person_id) pid,
       MIN(s.rism_composer_name) pname,
       MIN(s.rism_uniform_title) raw_title,
       s.rism_uniform_title_norm t,
       COUNT(*) n_sources,
       MIN(CASE s.rism_reliability
             WHEN 'Verified' THEN 1 WHEN 'Ascertained' THEN 2 WHEN 'Conjectural' THEN 3
             WHEN 'Doubtful' THEN 4 WHEN 'Alleged' THEN 5 ELSE 9 END) rel_rank,
       MAX(s.rism_has_incipit) has_inc
FROM rism_sources s
LEFT JOIN rism_persons p ON p.rism_person_id = s.rism_composer_person_id
WHERE s.rism_uniform_title_norm <> ''
  AND s.rism_is_anonymous = 0
  AND s.rism_composer_person_id IS NOT NULL
GROUP BY pid, s.rism_uniform_title_norm
"""

REL_NAME = {1: "Verified", 2: "Ascertained", 3: "Conjectural", 4: "Doubtful", 5: "Alleged", 9: ""}


def run(out_path: Path, new_only_path: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4")
    with conn.cursor() as cur:
        cur.execute("SELECT works_title, works_song_name FROM works")
        our_titles = set()
        for title, song in cur:
            if title:
                our_titles.add(norm(title))
            if song:
                our_titles.add(norm(song))

    header = ["rism_work_key", "composer_person_id", "composer_name", "uniform_title",
              "in_our_catalogue", "n_sources", "best_reliability", "has_incipit"]
    strict = existing = new = 0
    with open(out_path, "w", newline="", encoding="utf-8") as out, \
            open(new_only_path, "w", newline="", encoding="utf-8") as out_new:
        writer = csv.writer(out)
        writer_new = csv.writer(out_new)
        writer.writerow(header)
        writer_new.writerow(header)
        cur = conn.cursor(pymysql.cursors.SSCursor)
        cur.execute(GROUP_SQL)
        for pid, pname, raw_title, t, n_sources, rel_rank, has_inc in cur:
            if len(significant_tokens(t)) < 2:
                continue  # genérico o de un solo token
            if norm(pname) in ANON:
                continue
            strict += 1
            in_our = 1 if t in our_titles else 0
            existing += in_our
            new += 0 if in_our else 1
            row = [f"{pid}|{t}", pid, pname, raw_title, in_our, n_sources,
                   REL_NAME.get(rel_rank, ""), has_inc]
            writer.writerow(row)
            if not in_our:
                writer_new.writerow(row)
        cur.close()
    conn.close()
    print(f"obras RISM estrictas: {strict} | ya en nuestro catálogo: {existing} | nuevas: {new}")
    print(f"fichero completo: {out_path}")
    print(f"solo nuevas:     {new_only_path}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path(r"G:\rism\rism_works_strict.csv"))
    ap.add_argument("--new-only", type=Path, default=Path(r"G:\rism\rism_works_strict_new.csv"))
    args = ap.parse_args()
    run(args.out, args.new_only)


if __name__ == "__main__":
    main()
