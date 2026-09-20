"""Dry-run (read-only) del subconjunto B de `works_song_name` (1.448).

Clasifica cada caso en A (recorte seguro), B (mantener título completo) o C (revisión), sin asumir
que el sufijo-persona deba recortarse. No escribe nada.

    .venv\\Scripts\\python.exe scripts/diagnose_song_name_b.py
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

KEEP_MARKERS = ("dedicated", "dedicad", "in the style", "after ", "based on", "hommage", "tribute",
                "variations on", "theme by", "a la manera")


def run(out_csv: Path, out_md: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT w.id, w.works_title t, "
            " (SELECT p.persons_name FROM works_person_roles r JOIN persons p "
            "   ON p.persons_id=r.works_person_roles_person_id "
            "  WHERE r.works_person_roles_work_id=w.id AND r.works_person_roles_role_id=1 LIMIT 1) composer, "
            " (SELECT r.works_person_roles_person_id FROM works_person_roles r "
            "  WHERE r.works_person_roles_work_id=w.id AND r.works_person_roles_role_id=1 LIMIT 1) composer_id "
            "FROM works w WHERE (w.works_song_name IS NULL OR w.works_song_name='') "
            "AND w.works_title LIKE '% - %'")
        rows = cur.fetchall()
        cur.execute("SELECT works_title t, works_song_name s FROM works")
        known_titles = set()
        for r in cur.fetchall():
            for v in (r["t"], r["s"]):
                if v:
                    known_titles.add(norm(v))
        cur.execute("SELECT persons_name FROM persons")
        person_keys = {norm(r["persons_name"]) for r in cur.fetchall()}
        cur.execute("SELECT person_aliases_normalized_alias a FROM persons_aliases")
        person_keys |= {r["a"] for r in cur.fetchall() if r["a"]}
    conn.close()

    def is_person(text: str | None) -> bool:
        return bool(text) and norm(text) in person_keys

    counts = Counter()
    out = []
    for r in rows:
        title = r["t"] or ""
        prefix, suffix = (x.strip() for x in title.rsplit(" - ", 1))
        composer = r["composer"]
        notes = []
        lower = title.lower()
        if any(m in lower for m in KEEP_MARKERS):
            classification = "B"
            reason = "marcador de dedicatoria/estilo en el título"
        elif is_person(prefix):
            classification = "B"
            reason = "prefijo es persona conocida (patrón 'compositor - título')"
        elif composer and norm(suffix) == norm(composer):
            classification = "A"
            reason = "sufijo == compositor (rol 1)"
            notes.append("sufijo_igual_compositor")
        elif is_person(suffix) and norm(prefix) in known_titles:
            classification = "A"
            reason = "sufijo persona conocida y el prefijo ya existe como título en el corpus"
            notes.append("prefijo_en_corpus")
        elif is_person(suffix):
            classification = "C"
            reason = "sufijo es persona conocida (posible arreglista/intérprete) sin corroboración"
        else:
            classification = "C"
            reason = "sufijo no es persona conocida: revisar si es metadato o parte del título"
        counts[classification] += 1
        out.append({
            "work_id": r["id"], "song_name_original": "", "works_title": title,
            "candidate_suffix": suffix, "person_id": r["composer_id"] or "",
            "person_name": composer or "", "evidence": ";".join(notes) or reason,
            "classification": classification, "proposed_song_name": prefix if classification == "A" else "",
            "reason": reason,
        })

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out[0].keys()) if out else ["work_id"])
        writer.writeheader()
        writer.writerows(out)
    lines = ["# Dry-run `works_song_name` B (read-only)\n",
             f"- Casos: **{len(out)}**\n", "| clasificación | casos |", "|---|---|"]
    for k in ("A", "B", "C"):
        lines.append(f"| {k} | {counts.get(k, 0)} |")
    lines += ["\n## Ejemplos por clase\n"]
    for k in ("A", "B", "C"):
        lines.append(f"\n**{k}**\n")
        for d in [x for x in out if x["classification"] == k][:12]:
            lines.append(f"- `{d['works_title']}` → propuesto `{d['proposed_song_name'] or '—'}` · {d['reason']}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("casos:", len(out), "| clases:", dict(counts))
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\works_song_name_B_dry_run.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "dry-run-works-song-name-B.md")
    args = ap.parse_args()
    run(args.csv, args.md)


if __name__ == "__main__":
    main()
