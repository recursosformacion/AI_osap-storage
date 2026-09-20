"""Refinado read-only de los `sin_destino` del mapa de identidad.

Clasifica en: persona_real_sin_destino / posible_duplicado_fuzzy / ambigua / no_persona /
descartado_no_resoluble. No escribe nada.

    .venv\\Scripts\\python.exe scripts/refine_sin_destino.py
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

TRAILING = re.compile(r"\s*(\((?:[^()]*\d{4}[^()]*)\)|\bop\.?\s*\d+.*|\bopus\s+\d+.*)\s*$", re.I)
NO_PERSONA = re.compile(
    r"psalter|orchesographie|orchésographie|collection|anonymous|anonymus|tradicional|traditional|"
    r"various|varios|chorale|hymnal|melody|tune|album|edition|verlag|publisher|press|"
    r"orchestra|choir|ensemble|band|school|conservatory|opera|mass\b|motet|symphony|sonata|"
    r"suite|prelude|waltz|polka|march\b|score|parts?\b",
    re.I,
)


def _mk(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def _tokens(value: str | None) -> list[str]:
    return norm(value).split()


def _fuzzy_equal(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    if abs(len(a) - len(b)) > 2:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= 2


def run(identity_csv: Path, out_csv: Path, out_md: Path) -> None:
    with open(identity_csv, encoding="utf-8") as fh:
        targets = [r for r in csv.DictReader(fh) if r["tipo_destino"] == "sin_destino"]
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    prefixed_ids = set()
    with conn.cursor() as cur:
        cur.execute("SELECT persons_id FROM persons WHERE persons_name REGEXP "
                    "'^(Arranged from|Arranged by|Arr from|Arr |Attr|Attributed to|from |From |"
                    "Edited by|Transcribed by|Transcr)'")
        prefixed_ids = {r["persons_id"] for r in cur.fetchall()}
        cur.execute("SELECT persons_id, persons_name FROM persons")
        clean = [r for r in cur.fetchall() if r["persons_id"] not in prefixed_ids]
    conn.close()

    by_surname: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for p in clean:
        tokens = _tokens(p["persons_name"])
        if tokens:
            by_surname[tokens[-1]].append((p["persons_id"], tokens))

    rows, counts = [], Counter()
    for t in targets:
        clean_name = t["nombre_limpio"]
        tokens = _tokens(clean_name)
        if not tokens or NO_PERSONA.search(clean_name) or ":" in clean_name:
            kind, candidates = "no_persona", []
        else:
            surname = tokens[-1]
            first = tokens[0]
            candidates = []
            for pid, ptokens in by_surname.get(surname, []):
                if set(tokens) <= set(ptokens) or ptokens and _fuzzy_equal(first, ptokens[0]):
                    candidates.append(pid)
            if len(candidates) == 1:
                kind = "posible_duplicado_fuzzy"
            elif len(candidates) > 1:
                kind = "ambigua"
            elif len(tokens) >= 2:
                kind = "persona_real_sin_destino"
            else:
                kind = "descartado_no_resoluble"
        rows.append({"person_id": t["person_id"], "nombre_actual": t["nombre_actual"],
                     "nombre_limpio": clean_name, "rol1": t["rol1"],
                     "clasificacion": kind, "destino_fuzzy": candidates[0] if len(candidates) == 1 else "",
                     "n_candidatos": len(candidates)})
        counts[kind] += 1

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    spotlight = ["Franz Josef Haydn", "John French", "Arbeau Orchesographie",
                 "Genevan Psalter", "Nathan S"]
    lines = ["# Refinado de `sin_destino` (read-only)\n",
             f"- Personas: **{len(rows)}**\n", "| clasificación | Personas |", "|---|---|"]
    for k, v in counts.most_common():
        lines.append(f"| {k} | {v} |")
    lines += ["\n## Casos destacados\n", "| nombre limpio | clasificación | destino |",
              "|---|---|---|"]
    for s in spotlight:
        hit = next((r for r in rows if s.lower() in (r["nombre_limpio"] or "").lower()), None)
        if hit:
            lines.append(f"| {hit['nombre_limpio']} | {hit['clasificacion']} | {hit['destino_fuzzy'] or '—'} |")
    lines += ["\n## Detalle (muestra)\n", "| nombre limpio | rol1 | clasificación | destino |",
              "|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: -int(x["rol1"] or 0))[:40]:
        lines.append(f"| {r['nombre_limpio']} | {r['rol1']} | {r['clasificacion']} | {r['destino_fuzzy'] or '—'} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("sin_destino:", len(rows), "| clasificación:", dict(counts))
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", type=Path, default=Path(r"G:\rism\identity_map_prefixed.csv"))
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\sin_destino_refinado.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "refinado-sin-destino.md")
    args = ap.parse_args()
    run(args.identity, args.csv, args.md)


if __name__ == "__main__":
    main()
