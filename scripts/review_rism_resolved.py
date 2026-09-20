"""Revisión manual del lote `resolved` de RISM (read-only).

Lee las propuestas (`rism_composer_proposals.csv`), filtra `resolved` y produce, por obra:
work_id, título, compositor actual, propuesto, persona RISM, fuente(s), `240`, `$j`,
evidencia de persona (GND/VIAF/fechas/profesiones) y señales de arreglista/editor/copista.

    .venv\\Scripts\\python.exe scripts/review_rism_resolved.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

ARRANGER_RELATORS = {"arr", "cop", "edt", "dub", "adp", "oth"}
ARRANGER_WORDS = ("arrang", "copyist", "adapt", "transcri", "bearbeit", "schreiber", "kopei")


def run(csv_path: Path, out_md: Path, out_csv: Path) -> None:
    proposals = []
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["state"] == "resolved":
                proposals.append(row)
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)

    rows = []
    for p in proposals:
        wid = int(p["work_id"])
        with conn.cursor() as cur:
            cur.execute(
                "SELECT works_title, works_song_name, works_origin, works_catalogue FROM works "
                "WHERE id=%s", (wid,))
            work = cur.fetchone() or {}
            cur.execute(
                "SELECT p.persons_name, r.works_person_roles_role_id role FROM works_person_roles r "
                "JOIN persons p ON p.persons_id=r.works_person_roles_person_id "
                "WHERE r.works_person_roles_work_id=%s", (wid,))
            current = cur.fetchall()
            cur.execute(
                "SELECT rism_name, rism_dates, rism_gnd, rism_viaf, rism_professions, "
                "       rism_is_composer FROM rism_persons "
                "WHERE COALESCE(rism_canonical_id, rism_person_id)=%s LIMIT 1",
                (p["rism_person_id"],))
            person = cur.fetchone() or {}
            cur.execute(
                "SELECT s.rism_source_id, s.rism_reliability, s.rism_source_type, "
                "       s.rism_other_persons, s.rism_shelfmark, s.rism_uniform_title, "
                "       s.rism_composer_name, "
                "       (SELECT COUNT(*) FROM rism_source_links l "
                "        WHERE l.rism_source_id=s.rism_source_id) n_links "
                "FROM rism_sources s "
                "LEFT JOIN rism_persons rp ON rp.rism_person_id=s.rism_composer_person_id "
                "WHERE s.rism_uniform_title_norm=%s "
                "  AND COALESCE(rp.rism_canonical_id, s.rism_composer_person_id)=%s LIMIT 3",
                (p["title_key"], p["rism_person_id"]))
            sources = cur.fetchall()

        others = "; ".join(sorted({s["rism_other_persons"] for s in sources if s["rism_other_persons"]}))
        roles = "; ".join(
            f"{c['persons_name']} (rol {c['role']})" for c in current) or "—"
        signals = []
        for s in sources:
            text = (s["rism_other_persons"] or "").lower()
            signals.extend(r for r in ARRANGER_RELATORS if f"({r})" in text)
        prof = (person.get("rism_professions") or "").lower()
        if any(w in prof for w in ARRANGER_WORDS):
            signals.append("profesión no-compositor")
        rows.append({
            "work_id": wid,
            "title_key": p["title_key"],
            "title": work.get("works_song_name") or work.get("works_title"),
            "current_composer": roles,
            "proposed_composer": p["composer_name"],
            "rism_person_id": p["rism_person_id"],
            "rism_source_id": "; ".join(s["rism_source_id"] for s in sources),
            "uniform_title_240": "; ".join(sorted({s["rism_uniform_title"] or "" for s in sources})),
            "reliability": "; ".join(sorted({s["rism_reliability"] or "—" for s in sources})),
            "person_evidence": (f"GND {person.get('rism_gnd') or '—'} · "
                                f"VIAF {person.get('rism_viaf') or '—'} · "
                                f"fechas {person.get('rism_dates') or '—'}"),
            "other_persons": others or "—",
            "arranger_signal": ", ".join(sorted(set(signals))) or "—",
            "n_links": sum(s["n_links"] for s in sources),
            "decision": "",
        })
    conn.close()

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["work_id"])
        writer.writeheader()
        writer.writerows(rows)

    by_title: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_title[r["title_key"]].append(r)

    lines = [
        "# Revisión manual — lote `resolved` de RISM\n",
        f"Propuestas `resolved`: **{len(by_title)} títulos → {len(rows)} obras**. "
        "Marca `decision` (accept/reject/review) por título.\n",
        "## Por título (52)\n",
        "| título | propuesto | rism_person_id | $j | 240 | evidencia persona | señal arreglista | obras | decisión |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, group in sorted(by_title.items()):
        g = group[0]
        lines.append(
            f"| {key} | {g['proposed_composer']} | {g['rism_person_id']} | {g['reliability']} | "
            f"{g['uniform_title_240']} | {g['person_evidence']} | {g['arranger_signal']} | "
            f"{len(group)} | {g['decision'] or '—'} |"
        )
    lines += [
        "\n## Por obra (detalle)\n",
        "| work_id | título | compositor actual | propuesto | rism_person_id | fuente RISM | 240 | $j | "
        "evidencia persona | otras personas | señal arreglista | enlaces | decisión |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['work_id']} | {r['title']} | {r['current_composer']} | {r['proposed_composer']} | "
            f"{r['rism_person_id']} | {r['rism_source_id']} | {r['uniform_title_240']} | "
            f"{r['reliability']} | {r['person_evidence']} | {r['other_persons']} | "
            f"{r['arranger_signal']} | {r['n_links']} | {r['decision'] or '—'} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    flagged = sum(1 for r in rows if r["arranger_signal"] != "—")
    print(f"resolved: {len(rows)} obras | con señal arreglista/editor/copista: {flagged}")
    print("csv:", out_csv)
    print("informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\rism_composer_proposals.csv"))
    ap.add_argument("--out-md", type=Path, default=ROOT / "docsNew" / "revision-rism-resolved.md")
    ap.add_argument("--out-csv", type=Path, default=Path(r"G:\rism\rism_review_resolved.csv"))
    args = ap.parse_args()
    run(args.csv, args.out_md, args.out_csv)


if __name__ == "__main__":
    main()
