"""Fase 2B — Evidencia de autoridad RISM para nuestras personas (read-only).

Mide qué aportaría enriquecer nuestra autoridad de personas con RISM en los matches **únicos**
(fase 1): GND, VIAF, fechas y variantes de nombre. NO modifica `persons` ni `persons_aliases`:
solo lee y produce un informe.

    .venv\\Scripts\\python.exe scripts/analyze_rism_person_matches.py
    .venv\\Scripts\\python.exe scripts/analyze_rism_person_matches.py --out docsNew/analisis-rism-2b-autoridad.md
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

_YEAR = re.compile(r"(1[0-9]{3}|20[0-9]{2})")


def _matchkey(name: str | None) -> str:
    return " ".join(sorted(norm(name).split()))


def _years(text: str | None) -> list[int]:
    return [int(y) for y in _YEAR.findall(text or "")]


def run(out_path: Path | None) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SELECT rism_person_id, rism_person_names_matchkey k FROM rism_person_names")
        rism_by_key: dict[str, set[str]] = defaultdict(set)
        for r in cur.fetchall():
            if r["k"]:
                rism_by_key[r["k"]].add(r["rism_person_id"])

        cur.execute(
            "SELECT DISTINCT r.works_person_roles_person_id pid FROM works_person_roles r "
            "WHERE r.works_person_roles_role_id=1"
        )
        composer_ids = {r["pid"] for r in cur.fetchall()}

        cur.execute(
            "SELECT persons_id, persons_name, persons_birth_year, persons_death_year "
            "FROM persons"
        )
        persons = {r["persons_id"]: r for r in cur.fetchall()}

        cur.execute(
            "SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases"
        )
        our_aliases: dict[str, set[str]] = defaultdict(set)
        for r in cur.fetchall():
            if r["a"]:
                our_aliases[r["person_id"]].add(r["a"])

    # matches de nuestras personas-compositor
    unique: dict[str, str] = {}
    multiple = 0
    sin_match = 0
    for pid in composer_ids:
        person = persons.get(pid)
        if not person:
            continue
        ids = rism_by_key.get(_matchkey(person["persons_name"]), set())
        if not ids:
            sin_match += 1
        elif len(ids) == 1:
            unique[pid] = next(iter(ids))
        else:
            multiple += 1

    matched_rism_ids = sorted(set(unique.values()))
    conn2 = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                            password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                            cursorclass=pymysql.cursors.DictCursor)
    with conn2.cursor() as cur:
        details: dict[str, dict] = {}
        if matched_rism_ids:
            ph = ", ".join(["%s"] * len(matched_rism_ids))
            cur.execute(
                f"SELECT rism_person_id, rism_name, rism_dates, rism_gnd, rism_viaf, "
                f"rism_is_composer, rism_n_variants FROM rism_persons "
                f"WHERE rism_person_id IN ({ph})",
                matched_rism_ids,
            )
            details = {r["rism_person_id"]: r for r in cur.fetchall()}
            cur.execute(
                f"SELECT rism_person_id, rism_person_names_name, rism_person_names_matchkey k "
                f"FROM rism_person_names WHERE rism_person_id IN ({ph})",
                matched_rism_ids,
            )
            rism_forms: dict[str, set[tuple[str, str]]] = defaultdict(set)
            for r in cur.fetchall():
                rism_forms[r["rism_person_id"]].add((r["k"], r["rism_person_names_name"]))
    conn.close()
    conn2.close()

    stats = Counter()
    year_stats = Counter()
    name_stats = Counter()
    new_alias_persons = 0
    new_aliases_total = 0
    examples: dict[str, list[str]] = defaultdict(list)
    for pid, rid in unique.items():
        person = persons[pid]
        det = details.get(rid, {})
        if det.get("rism_gnd"):
            stats["con_gnd"] += 1
        if det.get("rism_viaf"):
            stats["con_viaf"] += 1
        if det.get("rism_dates"):
            stats["con_fechas"] += 1
        if not det.get("rism_is_composer"):
            stats["rismo_no_composer"] += 1

        rism_years = _years(det.get("rism_dates"))
        if rism_years:
            rb, rd = rism_years[0], rism_years[-1] if len(rism_years) > 1 else None
            ob, od = person["persons_birth_year"], person["persons_death_year"]
            if ob and rb and int(ob) != rb:
                year_stats["conflicto_nacimiento"] += 1
            elif not ob and rb:
                year_stats["rellenable_nacimiento"] += 1
            if od and rd and int(od) != rd:
                year_stats["conflicto_muerte"] += 1
            elif not od and rd:
                year_stats["rellenable_muerte"] += 1
            if ob and od and rb and rd and int(ob) == rb and int(od) == rd:
                year_stats["coincide"] += 1

        our_keys = {_matchkey(person["persons_name"])}
        our_keys |= {_matchkey(a) for a in our_aliases.get(pid, set())}
        new_here = 0
        for key, raw in rism_forms.get(rid, set()):
            if key and key not in our_keys:
                new_here += 1
                if len(examples["alias_nuevo"]) < 15:
                    examples["alias_nuevo"].append(f"{person['persons_name']} += {raw}")
        if new_here:
            new_alias_persons += 1
            new_aliases_total += new_here

        rism_key = _matchkey(det.get("rism_name"))
        if rism_key == _matchkey(person["persons_name"]):
            name_stats["concordante"] += 1
        elif rism_key and set(rism_key.split()) == set(_matchkey(person["persons_name"]).split()):
            name_stats["solo_orden"] += 1
        else:
            name_stats["difiere"] += 1
            if len(examples["nombre_difiere"]) < 15:
                examples["nombre_difiere"].append(
                    f"{person['persons_name']} <> {det.get('rism_name')}"
                )

    lines: list[str] = []
    add = lines.append
    add("# Fase 2B — Evidencia de autoridad RISM para nuestras personas\n")
    add("Generado por `scripts/analyze_rism_person_matches.py` (read-only). NO modifica `persons`.")
    add("Fuente RISM: CC-BY-3.0.\n")
    add(f"- Personas nuestras con rol 1 (compositor): **{len(composer_ids)}**")
    add(f"- Match **único** en RISM: **{len(unique)}** | múltiple: {multiple} | sin match: {sin_match}\n")
    add("## Qué aporta RISM a esos matches únicos\n")
    add("| Dato | Personas |")
    add("|---|---|")
    add(f"| con GND | {stats['con_gnd']} |")
    add(f"| con VIAF | {stats['con_viaf']} |")
    add(f"| con fechas | {stats['con_fechas']} |")
    add(f"| RISM no lo marca «Composer» | {stats['rismo_no_composer']} |")
    add("\n## Fechas\n")
    add("| Resultado | Personas |")
    add("|---|---|")
    for key in ("coincide", "rellenable_nacimiento", "rellenable_muerte",
                "conflicto_nacimiento", "conflicto_muerte"):
        add(f"| {key} | {year_stats.get(key, 0)} |")
    add("\n## Nombre canónico (nuestro vs RISM)\n")
    add("| Resultado | Personas |")
    add("|---|---|")
    for key in ("concordante", "solo_orden", "difiere"):
        add(f"| {key} | {name_stats.get(key, 0)} |")
    add("\n## Variantes de nombre\n")
    add(f"- Personas que ganarían alias: **{new_alias_persons}**")
    add(f"- Total de alias nuevos: **{new_aliases_total}**")
    add("\n## Ejemplos\n")
    add("\n**alias_nuevo**\n")
    add("\n".join(f"- {e}" for e in examples.get("alias_nuevo", [])) or "(sin ejemplos)")
    add("\n**nombre_difiere**\n")
    add("\n".join(f"- {e}" for e in examples.get("nombre_difiere", [])) or "(sin ejemplos)")
    add("\n> Riesgo: el match es por nombre normalizado; en nombres comunes puede haber falso")
    add("> positivo. Antes de escribir en `persons`, validar con GND/VIAF/fechas y revisión.")

    report = "\n".join(lines) + "\n"
    if out_path is not None:
        out_path.write_text(report, encoding="utf-8")
        print(f"informe: {out_path}")
    print("compositor:", len(composer_ids), "unico:", len(unique), "multiple:", multiple,
          "sin_match:", sin_match)
    print("stats:", dict(stats), "años:", dict(year_stats), "nombres:", dict(name_stats))
    print("alias: personas", new_alias_persons, "total", new_aliases_total)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
