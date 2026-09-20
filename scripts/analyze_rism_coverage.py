"""Mide la cobertura del índice RISM de personas frente a nuestro catálogo (read-only).

Responde a:
1. Nuestras personas con compositor (rol 1) → matching RISM: únicos / múltiples / sin match.
2. Obras sin compositor → candidatos (título/hermana) → ¿cuántas recupera RISM?

NO modifica `persons` ni `persons_aliases`; solo lee `rism_persons`/`rism_person_names`.

    .venv\\Scripts\\python.exe scripts/analyze_rism_coverage.py
    .venv\\Scripts\\python.exe scripts/analyze_rism_coverage.py --out docsNew/analisis-cobertura-rism.md
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from domain.services.composer_quality import validar_nombre_compositor  # noqa: E402


def _matchkey(name: str | None) -> str:
    return " ".join(sorted(norm(name).split()))


def _valid_person(text: str | None) -> bool:
    return bool(text) and bool(validar_nombre_compositor(text)[0])


def run(out_path: Path | None) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SELECT rism_person_id, rism_person_names_matchkey k FROM rism_person_names")
        rism_by_key: dict[str, set[str]] = defaultdict(set)
        n_names = 0
        for r in cur.fetchall():
            n_names += 1
            if r["k"]:
                rism_by_key[r["k"]].add(r["rism_person_id"])
        cur.execute("SELECT rism_person_id, rism_is_composer FROM rism_persons")
        is_composer = {r["rism_person_id"]: bool(r["rism_is_composer"]) for r in cur.fetchall()}

        cur.execute(
            "SELECT DISTINCT r.works_person_roles_person_id pid, p.persons_name name "
            "FROM works_person_roles r JOIN persons p ON p.persons_id=r.works_person_roles_person_id "
            "WHERE r.works_person_roles_role_id=1"
        )
        our_composers = cur.fetchall()

        cur.execute("SELECT id, works_title, works_catalogue, works_attribution_note FROM works")
        works = cur.fetchall()
        cur.execute(
            "SELECT r.works_person_roles_work_id wid, p.persons_name name FROM works_person_roles r "
            "JOIN persons p ON p.persons_id=r.works_person_roles_person_id "
            "WHERE r.works_person_roles_role_id=1"
        )
        composer_by_work = {r["wid"]: r["name"] for r in cur.fetchall()}
    conn.close()

    # --- 1. Nuestras personas con compositor ---
    coverage = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for person in our_composers:
        ids = rism_by_key.get(_matchkey(person["name"]), set())
        if not ids:
            coverage["sin_match"] += 1
            if len(examples["sin_match"]) < 12:
                examples["sin_match"].append(person["name"])
        elif len(ids) == 1:
            rid = next(iter(ids))
            bucket = "unico_composer" if is_composer.get(rid) else "unico_no_composer"
            coverage[bucket] += 1
            if len(examples[bucket]) < 12:
                examples[bucket].append(f"{person['name']} -> {rid}")
        else:
            coverage["multiple"] += 1
            if len(examples["multiple"]) < 12:
                examples["multiple"].append(f"{person['name']} -> {len(ids)} candidatos")

    # --- 2. Obras sin compositor: candidatos por título/hermana ---
    titles_with_composer: dict[str, set[str]] = defaultdict(set)
    for w in works:
        name = composer_by_work.get(w["id"])
        if name:
            titles_with_composer[norm(w["works_title"])].add(name)

    missing = [w for w in works if not composer_by_work.get(w["id"])]
    recovery = Counter()
    rec_examples: dict[str, list[str]] = defaultdict(list)
    for w in missing:
        candidates: set[str] = set()
        title = w["works_title"] or ""
        if " - " in title:
            suffix = title.rsplit(" - ", 1)[-1].strip()
            if _valid_person(suffix):
                candidates.add(suffix)
        elif _valid_person(w["works_attribution_note"]):
            candidates.add(w["works_attribution_note"])
        candidates |= titles_with_composer.get(norm(title), set())

        matched: set[str] = set()
        for candidate in candidates:
            matched |= rism_by_key.get(_matchkey(candidate), set())
        if not candidates:
            continue
        if not matched:
            recovery["con_candidato_sin_rism"] += 1
        elif len(matched) == 1:
            rid = next(iter(matched))
            recovery["recuperada_rism"] += 1
            if is_composer.get(rid):
                recovery["recuperada_rism_composer"] += 1
            if len(rec_examples["recuperada_rism"]) < 12:
                rec_examples["recuperada_rism"].append(
                    f"{title} (id {w['id']}) -> {rid} [{'composer' if is_composer.get(rid) else 'no'}]"
                )
        else:
            recovery["candidato_ambiguo"] += 1
            if len(rec_examples["candidato_ambiguo"]) < 12:
                rec_examples["candidato_ambiguo"].append(
                    f"{title} (id {w['id']}) -> {len(matched)} candidatos"
                )

    lines: list[str] = []
    add = lines.append
    add("# Cobertura del índice RISM de personas\n")
    add("Generado por `scripts/analyze_rism_coverage.py` (read-only). Fuente RISM: CC-BY-3.0.\n")
    add(f"- Personas RISM indexadas: **{len(is_composer)}** "
        f"(compositores: **{sum(is_composer.values())}**)")
    add(f"- Formas de nombre indexadas: **{n_names}**\n")
    add("## 1. Nuestras personas con compositor → RISM\n")
    add(f"- Personas nuestras con rol 1: **{len(our_composers)}**")
    add("| Resultado | Personas |")
    add("|---|---|")
    for key in ("unico_composer", "unico_no_composer", "multiple", "sin_match"):
        add(f"| {key} | {coverage.get(key, 0)} |")
    add("\n### Ejemplos\n")
    for key in ("unico_composer", "multiple", "sin_match"):
        add(f"\n**{key}**\n")
        add("\n".join(f"- {e}" for e in examples.get(key, [])) or "(sin ejemplos)")
    add("\n## 2. Obras sin compositor → recuperación vía RISM\n")
    add(f"- Obras sin compositor: **{len(missing)}**")
    add(f"- Con candidato (título/hermana) y match **único** en RISM: "
        f"**{recovery.get('recuperada_rism', 0)}** "
        f"(de las cuales el match es compositor RISM: {recovery.get('recuperada_rism_composer', 0)})")
    add(f"- Con candidato pero **sin** match RISM: {recovery.get('con_candidato_sin_rism', 0)}")
    add(f"- Con candidato y match **múltiple** (ambiguo): {recovery.get('candidato_ambiguo', 0)}")
    add("\n### Ejemplos de recuperación\n")
    add("\n".join(f"- {e}" for e in rec_examples.get("recuperada_rism", [])) or "(sin ejemplos)")

    report = "\n".join(lines) + "\n"
    if out_path is not None:
        out_path.write_text(report, encoding="utf-8")
        print(f"informe: {out_path}")
    print("personas nuestras (rol1):", len(our_composers), dict(coverage))
    print("obras sin compositor:", len(missing), dict(recovery))


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
