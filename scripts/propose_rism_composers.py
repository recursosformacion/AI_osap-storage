"""Dry-run: propuesta de compositor para obras sin compositor usando el corpus RISM (read-only).

Guardas:
  G1. Coincidencia por título **uniforme `240`** (no por `245` transcrito).
  G2. **Un solo** compositor RISM para ese título (varios ⇒ tradicional/ambiguo ⇒ bloqueo).
  G3. La persona RISM debe estar marcada como **Composer**.
  G4. Fiabilidad `Verified` (resolved) o `Ascertained` (inferred); el resto ⇒ bloqueo.
  G5. Título sin marcadores de tradición/anónimo.

No escribe en `works` ni `persons`: produce CSV y un informe.

    .venv\\Scripts\\python.exe scripts/propose_rism_composers.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

ANON_RE = re.compile(
    r"trad|anon|unknown|unbekannt|anonym|desconocid|sin autor|vvaa|varios|various", re.I
)
RANK_SQL = ("MIN(CASE s.rism_reliability WHEN 'Verified' THEN 1 WHEN 'Ascertained' THEN 2 "
            "WHEN 'Conjectural' THEN 3 WHEN 'Doubtful' THEN 4 WHEN 'Alleged' THEN 5 ELSE 9 END)")
CHUNK = 400


def run(proposals_path: Path, report_path: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT w.id, w.works_title t, w.works_song_name sn FROM works w "
            "WHERE NOT EXISTS (SELECT 1 FROM works_person_roles r "
            "  WHERE r.works_person_roles_work_id=w.id AND r.works_person_roles_role_id=1)"
        )
        missing = cur.fetchall()

    by_key: dict[str, set[int]] = defaultdict(set)
    for w in missing:
        for value in (w["t"], w["sn"]):
            key = norm(value)
            if key:
                by_key[key].add(int(w["id"]))
    keys = sorted(by_key)

    rism: dict[str, list[dict]] = defaultdict(list)
    keys_list = list(keys)
    with conn.cursor() as cur:
        for i in range(0, len(keys_list), CHUNK):
            part = keys_list[i:i + CHUNK]
            ph = ", ".join(["%s"] * len(part))
            cur.execute(
                "SELECT s.rism_uniform_title_norm t, "
                "       COALESCE(p.rism_canonical_id, s.rism_composer_person_id) pid, "
                "       MIN(s.rism_composer_name) pname, "
                f"      {RANK_SQL} rank, "
                "       COALESCE(MAX(p.rism_is_composer), 0) is_comp "
                "FROM rism_sources s "
                "LEFT JOIN rism_persons p ON p.rism_person_id = s.rism_composer_person_id "
                "WHERE s.rism_uniform_title_norm IN (" + ph + ") "
                "  AND s.rism_is_anonymous = 0 AND s.rism_composer_person_id IS NOT NULL "
                "GROUP BY 1, 2",
                part,
            )
            for row in cur.fetchall():
                rism[row["t"]].append(row)
    conn.close()

    STATS = Counter()
    proposals: list[list] = []
    samples: dict[str, list[str]] = defaultdict(list)
    for key, work_ids in by_key.items():
        candidates = rism.get(key)
        if not candidates:
            STATS["sin_fuente_rism"] += 1
            continue
        people = {c["pid"] for c in candidates}
        if len(people) > 1:
            STATS["bloqueo_varios_compositores"] += 1
            if len(samples["bloqueo_varios_compositores"]) < 12:
                samples["bloqueo_varios_compositores"].append(
                    f"{key} → {sorted({c['pname'] for c in candidates})[:4]}"
                )
            continue
        chosen = min(candidates, key=lambda c: c["rank"])
        if not chosen["is_comp"]:
            STATS["bloqueo_no_composer"] += 1
            continue
        if chosen["rank"] >= 3:
            STATS["bloqueo_baja_fiabilidad"] += 1
            continue
        if ANON_RE.search(key):
            STATS["bloqueo_tradicional"] += 1
            continue
        state = "resolved" if chosen["rank"] == 1 else "inferred"
        STATS[f"propuesta_{state}"] += 1
        for wid in sorted(work_ids):
            proposals.append([wid, key, chosen["pid"], chosen["pname"], state, chosen["rank"]])
        if len(samples[f"propuesta_{state}"]) < 12:
            samples[f"propuesta_{state}"].append(f"{key} → {chosen['pname']}")

    with open(proposals_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["work_id", "title_key", "rism_person_id", "composer_name",
                         "state", "rank"])
        writer.writerows(proposals)

    distinct_proposals = len({p[0] for p in proposals})
    lines = [
        "# Dry-run: asignación de compositor desde RISM (con guardas)\n",
        "Generado por `scripts/propose_rism_composers.py` (read-only). NO escribe en `works`.\n",
        f"- Obras sin compositor: **{len(missing)}**",
        f"- Títulos distintos (works_title/song_name): {len(keys)}",
        f"- **Propuestas sobre obras: {distinct_proposals}**\n",
        "## Guardas\n",
        "G1 `240` uniforme · G2 un solo compositor · G3 persona «Composer» · "
        "G4 `Verified`/`Ascertained` · G5 sin marcador tradicional.\n",
        "## Resultado\n",
        "| Resultado | Títulos |",
        "|---|---|",
    ]
    for k, v in STATS.most_common():
        lines.append(f"| {k} | {v} |")
    lines.append("\n## Muestras\n")
    for k in ("propuesta_resolved", "propuesta_inferred", "bloqueo_varios_compositores"):
        lines.append(f"\n**{k}**\n")
        lines.append("\n".join(f"- {s}" for s in samples.get(k, [])) or "(sin muestras)")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"obras sin compositor: {len(missing)} | títulos: {len(keys)}")
    print(f"propuestas (obras): {distinct_proposals}")
    print("stats:", dict(STATS))
    print("csv:", proposals_path)
    print("informe:", report_path)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--proposals", type=Path, default=Path(r"G:\rism\rism_composer_proposals.csv"))
    ap.add_argument("--report", type=Path, default=ROOT / "docsNew" / "dry-run-rism-compositores.md")
    args = ap.parse_args()
    run(args.proposals, args.report)


if __name__ == "__main__":
    main()
