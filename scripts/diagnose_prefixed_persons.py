"""Diagnóstico read-only de personas con nombre contaminado por el import
(`Arranged from …`, `from …`, `Arr …`, `Attr …`…).

No escribe nada. Propone normalización/merge (renombrar o fusionar) sin ejecutarla.

    .venv\\Scripts\\python.exe scripts/diagnose_prefixed_persons.py
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

PREFIX = re.compile(
    r"^\s*(arranged\s+from|arranged\s+by|arr\s+from|arr\.?\s+|attr\.?\s+|attributed\s+to|"
    r"from|edited\s+by|transcribed\s+by|transcr\.?\s+)\s*",
    re.I,
)
TRAILING = re.compile(r"\s*(\((?:[^()]*\d{4}[^()]*)\)|\bop\.?\s*\d+.*|\bopus\s+\d+.*)\s*$", re.I)


def _matchkey(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def _clean(name: str) -> str:
    text = PREFIX.sub("", name or "")
    text = TRAILING.sub("", text).strip(" .,-")
    return text


def run(out_path: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SELECT persons_id, persons_name, persons_source_system FROM persons "
                    "WHERE persons_name REGEXP '^(Arranged from|Arranged by|Arr from|Arr |Attr|"
                    "Attributed to|from |Edited by|Transcribed by|Transcr)'")
        rows = cur.fetchall()
        cur.execute("SELECT works_person_roles_person_id pid, works_person_roles_role_id role, "
                    "COUNT(DISTINCT works_person_roles_work_id) n FROM works_person_roles "
                    "WHERE works_person_roles_role_id IN (1,3) GROUP BY 1,2")
        roles: dict[str, dict[int, int]] = defaultdict(dict)
        for r in cur.fetchall():
            roles[r["pid"]][r["role"]] = r["n"]
        cur.execute("SELECT persons_id, persons_name FROM persons")
        by_key: dict[str, list[str]] = defaultdict(list)
        for r in cur.fetchall():
            by_key[_matchkey(r["persons_name"])].append(r["persons_id"])
    conn.close()

    counts = Counter()
    detail = []
    for row in rows:
        clean = _clean(row["persons_name"])
        key = _matchkey(clean)
        candidates = [pid for pid in by_key.get(key, []) if pid != row["persons_id"]]
        composer_works = roles.get(row["persons_id"], {}).get(1, 0)
        arranger_works = roles.get(row["persons_id"], {}).get(3, 0)
        if len(candidates) == 1:
            category = "merge_candidate"
        elif len(candidates) > 1:
            category = "ambigua"
        else:
            category = "rename_candidate"
        counts[category] += 1
        counts["con_atribuciones"] += 1 if composer_works else 0
        detail.append({
            "persons_id": row["persons_id"], "name": row["persons_name"], "clean": clean,
            "source": row["persons_source_system"], "category": category,
            "candidates": candidates, "composer_works": composer_works,
            "arranger_works": arranger_works,
        })

    lines = [
        "# Diagnóstico: personas con prefijo del import (`from…`/`Arranged from…`)\n",
        "Read-only. No escribe nada.\n",
        f"- Personas con prefijo: **{len(rows)}**",
        f"- Con atribuciones de compositor (rol 1): **{counts['con_atribuciones']}**\n",
        "## Clasificación\n",
        "| Categoría | Personas |",
        "|---|---|",
    ]
    for k in ("merge_candidate", "rename_candidate", "ambigua"):
        lines.append(f"| {k} | {counts.get(k, 0)} |")
    lines.append("\n## Fuentes del import\n")
    for src, n in Counter(r["persons_source_system"] for r in rows).most_common():
        lines.append(f"- {src}: {n}")
    lines.append("\n## Detalle (muestra)\n")
    lines.append("| persons_id | nombre | nombre limpio | categoría | obras(rol1) | candidato merge |")
    lines.append("|---|---|---|---|---|---|")
    for d in sorted(detail, key=lambda x: -x["composer_works"])[:60]:
        lines.append(f"| {d['persons_id']} | {d['name']} | {d['clean']} | {d['category']} | "
                     f"{d['composer_works']} | {d['candidates'][0] if d['candidates'] else '—'} |")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("personas con prefijo:", len(rows), "| clasificación:", dict(counts))
    print("informe:", out_path)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "docsNew" / "diagnostico-prefijos-import.md")
    args = ap.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
